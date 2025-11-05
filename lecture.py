# lecture.py
from flask import Blueprint, render_template, request, jsonify, session, abort, redirect, url_for
from sqlalchemy import desc, text
from extensions import db
from models_lecture import LectureChallenge, LectureSubmission
import json, re
from flask import session as flask_session
from flask import current_app
import csv, os
from functools import lru_cache
from datetime import datetime
from extensions import socketio
from lecture_utils import is_open_now

lecture_bp = Blueprint('lecture', __name__)

# === Helpers ===
ADMIN_NETIDS = { 'nh385' }

import csv, os, time
from functools import lru_cache

ROSTER_CSV = os.environ.get(
    "ROSTER_CSV",
    os.path.join(os.path.dirname(__file__), "data", "github_roster.csv")
)

# ---------- Feedback pickers (student-visible & per-submission) ----------
def _pick_feedback(sub):
    """Return the first non-empty text from common feedback/comment fields on a single submission."""
    for attr in ('feedback', 'comment', 'feedback_text', 'notes'):
        if hasattr(sub, attr):
            val = getattr(sub, attr) or ''
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ''

def _latest_student_feedback(challenge_id: int, netid: str):
    """Return the newest non-empty feedback across *all* of this student's submissions for the challenge."""
    from models_lecture import LectureSubmission  # avoid cycle if you have blueprints split
    subs = (LectureSubmission.query
            .filter_by(challenge_id=challenge_id, netid=netid)
            .order_by(LectureSubmission.created_at.desc())
            .all())
    for s in subs:
        f = _pick_feedback(s)
        if f:
            return f
    return ''

def _extract_feedback(sub):
    """Return the first non-empty text from common feedback/comment fields."""
    for attr in ('feedback', 'comment', 'feedback_text', 'notes'):
        if hasattr(sub, attr):
            val = getattr(sub, attr) or ''
            if val.strip():
                return val
    return None

def _viewer_section():
    sec = session.get("section")
    if session.get("is_admin"):
        sec = session.get("admin_view_section", sec)
    return sec

def _can_view_public_replay(ch, sub):
    if not (getattr(sub, "public_replay", False) and getattr(sub, "status", "") == "approved"):
        return False
    if not getattr(ch, "replays_same_section_only", False):
        return True
    return sub.section == _viewer_section()

def _normalize_full_name(full: str) -> str:
    """Convert 'Last, First [Middle]' -> 'First [Middle] Last' and tidy spaces."""
    if not full:
        return ""
    full = full.strip()
    # Handle "Last, First Middle"
    if "," in full:
        last, rest = full.split(",", 1)
        parts = [p for p in rest.strip().split() if p]
        if parts:
            return " ".join(parts + [last.strip()])
        return last.strip()
    # Already "First Last" style
    return " ".join(full.split())

def _header_map(headers):
    # normalize headers: lowercase, remove spaces/underscores
    return { (h or "").lower().replace(" ", "").replace("_",""): h for h in (headers or []) }

@lru_cache(maxsize=1)
def _roster_map():
    """
    Returns { netid_lower: {'name': 'First Last', 'section': '1'} }
    Compatible with headers: Section, Full Name, NetID, GitHub Username
    (case/whitespace-insensitive).
    """
    m = {}
    try:
        path = current_app.config.get("ROSTER_FILE")
    except RuntimeError:
        path = None
    path = path or ROSTER_CSV
    if not os.path.exists(path):
        return m
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        H = _header_map(reader.fieldnames)
        for row in reader:
            netid = (row.get(H.get("netid",""), "") or "").strip().split("@")[0].lower()
            if not netid:
                continue
            full = (row.get(H.get("fullname",""), "") or row.get(H.get("name",""), "") or "").strip()
            section = (row.get(H.get("section",""), "") or "").strip()
            name = _normalize_full_name(full) or f"Student {netid[:2]}…"
            m[netid] = {"name": name, "section": section}
    return m

def _parse_dt(s):
    s = (s or '').strip()
    if not s:
        return None
    # Accept ISO or HTML datetime-local (no tz)
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None

def _rooms_for(ch):
    scope = (ch.section_scope or "").strip().upper()
    if not scope or scope in {"ALL","*"}:
        return [f"section:{s}" for s in (1,2,5,6)]  # list your real sections here
    rooms = []
    for tok in scope.split(","):
        tok = tok.strip()
        if tok.isdigit():
            rooms.append(f"section:{int(tok)}")
    return rooms or ["section:none"]

def _payload_for(ch):
    # Only send payload if it should show right now; otherwise send None to hide
    if is_open_now(ch):
        return {"slug": ch.slug, "title": ch.title}
    return None

def _get_replays_scope(ch) -> bool:
    """
    Return True => same-section only, False => cross-section allowed.
    Works even if the DB column doesn't exist by reading a Redis mirror.
    Defaults to True (lockdown) if nothing is stored.
    """
    # 1) If the model has the column, use it
    if hasattr(ch, 'replays_same_section_only'):
        val = getattr(ch, 'replays_same_section_only')
        if val is not None:
            return bool(val)

    # 2) Fall back to Redis mirror
    try:
        from extensions_redis import r as redis_client
        raw = redis_client.get(f"lecture:flags:{ch.slug}")
        if raw:
            import json as _json
            doc = _json.loads(raw)
            if "replays_same_section_only" in doc:
                return bool(doc["replays_same_section_only"])
    except Exception:
        pass

    # 3) Safe default (locked to same section)
    return True


def _set_replays_scope(slug: str, value: bool) -> None:
    """Mirror the scope flag in Redis so readers can see it even without a DB column."""
    try:
        from extensions_redis import r as redis_client
        import json as _json
        k = f"lecture:flags:{slug}"
        # merge if an object already exists
        doc = {}
        raw = redis_client.get(k)
        if raw:
            try:
                doc = _json.loads(raw)
            except Exception:
                doc = {}
        doc["replays_same_section_only"] = bool(value)
        redis_client.set(k, _json.dumps(doc))
    except Exception:
        # best-effort mirror
        pass

def _submission_section(sub):
    """Return the section for a submission, even if there's no DB column."""
    # prefer the DB column if present
    val = getattr(sub, 'section', None)
    if val is not None and str(val).strip():
        return str(val).strip()
    # fall back to roster-derived section from the submitter's netid
    return section_for_netid(getattr(sub, 'netid', '')).strip()

def lookup_display_name(netid: str) -> str:
    """Canonical human name (admin or internal use)."""
    info = _roster_map().get((netid or "").lower())
    if info and info.get("name"):
        return info["name"]
    # Try any app-level helper you already have:
    try:
        from app import get_display_name as app_get_display_name
        alt = app_get_display_name(netid)
        if alt and alt.strip():
            return alt
    except Exception:
        pass
    return f"Student {netid[:2]}…" if netid else "Student"

def public_display_name(netid: str, include_section: bool = False) -> str:
    """Name shown to students; never reveals raw NetID."""
    info = _roster_map().get((netid or "").lower()) or {}
    name = info.get("name") or lookup_display_name(netid)
    if include_section and info.get("section"):
        return f"{name} (Sec {info['section']})"
    return name

def student_section() -> str:
    # Admins: use the chosen section (from dropdown)
    if session.get('is_admin'):
        sec = session.get('admin_view_section') or session.get('section')
        return (str(sec).strip() if sec is not None else "")
    # Students: map from roster
    netid = session.get('netid')
    if not netid:
        return ""
    row = _roster_map().get(netid.lower()) or {}
    return str(row.get('section', '')).strip()


def student_can_view(ch: LectureChallenge) -> bool:
    sec = student_section()
    if ch.is_open and ch.is_visible_to_section(sec):
        return True
    if ch.history_enabled and ch.is_visible_to_section(sec):
        return True
    # participated?
    has_sub = LectureSubmission.query.filter_by(challenge_id=ch.id, netid=session.get('netid')).first()
    return bool(ch.history_enabled and has_sub)

def all_sections():
    """Unique, sorted section labels from the roster cache."""
    secs = set()
    for info in _roster_map().values():
        s = (info.get('section') or '').strip()
        if s:
            secs.add(s)
    # natural sort: numbers before strings, 1,2,10
    def k(x):
        return (0, int(x)) if str(x).isdigit() else (1, str(x).lower())
    return sorted(secs, key=k)


def refresh_roster_cache():
    """Call this if you replace the CSV at runtime (optional admin hook)."""
    _roster_map.cache_clear()
    _roster_map()

def section_for_netid(netid: str) -> str:
    info = _roster_map().get((netid or "").lower()) or {}
    return (info.get("section") or "").strip()


def require_login(func):
    from functools import wraps
    @wraps(func)
    def _inner(*args, **kwargs):
        if 'netid' not in session:
            # /login_netid is POST-only in app.py; redirect to /assignments instead
            return redirect(url_for('assignments', next=request.path))
            # your repo already has /login_netid; use it
            # return redirect(url_for('login_netid', next=request.path))
        return func(*args, **kwargs)
    return _inner


def is_admin_current_user() -> bool:
    n = session.get('netid')
    cfg_admin = current_app.config.get('ADMIN_NETID')
    return bool(n and (n in ADMIN_NETIDS or n == cfg_admin)) or bool(session.get('is_admin'))

# === Student views/APIs ===
@lecture_bp.get('/lecture/<slug>')
@require_login
def view_lecture(slug):
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()
    if not student_can_view(ch):
        abort(403)
        
    netid = session['netid']
    # display = lookup_display_name(netid)
    # Seed the editor with the student's last submission (for past challenges)
    seed_code = ""
    last = (LectureSubmission.query
            .filter_by(challenge_id=ch.id, netid=netid)
            .order_by(LectureSubmission.created_at.desc())
            .first())
    if last:
        seed_code = last.code or ""

    # can submit only if challenge is open AND this section is allowed
    can_submit = bool(ch.is_open and ch.is_visible_to_section(student_section()))

    return render_template('lecture_challenge.html', ch=ch, netid=netid, display_name=netid,seed_code=seed_code,can_submit=can_submit)

@lecture_bp.get('/lecture/browse')
@require_login
def browse_challenges_page():
    return render_template('lecture_browse.html')  # small page with a list; see below

def available_time(ch):
    # pick best available timestamp for ordering
    for attr in ('opened_at', 'open_start', 'created_at'):
        val = getattr(ch, attr, None)
        if val:
            return val
    # fallback – make it sortable
    try:
        return datetime.fromtimestamp(0)
    except Exception:
        return datetime.min

@lecture_bp.get('/api/lecture/browse')
@require_login
def browse_challenges_api():
    netid = session['netid']
    sec = student_section()

    # open + allowed
    # open_q = LectureChallenge.query.filter_by(is_open=True).all()
    qs = LectureChallenge.query.filter_by(is_open=True).all()
    # history-enabled (closed but viewable)
    past_q = LectureChallenge.query.filter_by(is_open=False, history_enabled=True).all()

    # participation set
    sub_cids = {cid for (cid,) in
        db.session.query(LectureSubmission.challenge_id)
                  .filter_by(netid=netid).distinct().all()
    }

    def allowed(ch): return ch.is_visible_to_section(sec)

    # Build typed lists (keep the objects for sorting)
    # open_allowed = [ch for ch in open_q if allowed(ch)]
    open_allowed = [ch for ch in qs if is_open_now(ch) and allowed(ch)]
    past_participated = [ch for ch in past_q if ch.id in sub_cids]
    past_global = [ch for ch in past_q if allowed(ch) and ch.id not in sub_cids]

    # Sort by when they were made available (desc = newest first)
    open_allowed.sort(key=available_time, reverse=True)
    past_participated.sort(key=available_time, reverse=True)
    past_global.sort(key=available_time, reverse=True)

    def entry(ch):
        return {"slug": ch.slug, "title": ch.title, "open": bool(ch.is_open),
                "available_at": (getattr(ch, 'opened_at', None) or
                                 getattr(ch, 'open_start', None) or
                                 getattr(ch, 'created_at', None))}
    return jsonify({
        "ok": True,
        "open": [entry(c) for c in open_allowed],
        "past_participated": [entry(c) for c in past_participated],
        "past_global": [entry(c) for c in past_global],
    })

@lecture_bp.post('/api/lecture/<slug>/submit')
@require_login
def submit_lecture(slug):
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()
     # HARD GUARD: closed or not for this section -> 403
    if not (ch.is_open and ch.is_visible_to_section(student_section())):
        return jsonify(ok=False, error="Submissions are closed for your section."), 403

    if not ch.is_open:
        return jsonify({"ok": False, "error": "Submissions are closed."}), 403
    try:
        data = request.get_json(force=True) or {}
        code = data.get('code', '')
        if not code.strip():
            return jsonify({"ok": False, "error": "Empty submission."}), 400
        code = (data.get('code', '') or '').replace('\t', '    ')


        sub = LectureSubmission(
            challenge_id=ch.id,
            netid=session['netid'],
            display_name=session['netid'],#lookup_display_name(session['netid']),
            code=code,
            keystrokes_json=data.get('keystrokes'),
            run_output=data.get('run_output'),
            runtime_ms=data.get('runtime_ms')
        )
        sub.section = str(student_section())  # <-- make replays scope-able by section
        db.session.add(sub); db.session.commit()
        return jsonify({"ok": True, "submission_id": sub.id})
    except Exception as e:
        current_app.logger.exception("Submit failed for %s", slug)
        return jsonify({"ok": False, "error": str(e)}), 500

@lecture_bp.get('/api/lecture/<slug>/leaderboard')
@require_login
def lecture_leaderboard(slug):
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()
    if not ch.show_leaderboard:
        return jsonify({"ok": True, "entries": []})

    rows = (LectureSubmission.query
        .filter_by(challenge_id=ch.id)
        .filter(getattr(LectureSubmission, 'status', None) == 'approved'
                if hasattr(LectureSubmission, 'status')
                else LectureSubmission.approved.is_(True))
        .order_by(desc(LectureSubmission.points), LectureSubmission.created_at.asc())
        .limit(100).all())

#    rows = (LectureSubmission.query
#            #.filter_by(challenge_id=ch.id, approved=True)
#             .filter_by(challenge_id=ch.id, status='approved')
#            .order_by(desc(LectureSubmission.points), LectureSubmission.created_at.asc())
#            .limit(100).all())

    return jsonify({"ok": True, "entries": [
        {"display_name": r.netid, "submitted_at": r.created_at.isoformat(), "submission_id": r.id}
        for r in rows
    ]})

@lecture_bp.get('/api/lecture/<slug>/my_status')
@require_login
def my_status(slug):
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()
    me = session['netid']

    latest = (LectureSubmission.query
              .filter_by(challenge_id=ch.id, netid=me)
              .order_by(LectureSubmission.created_at.desc())
              .first())

    if not latest:
        return jsonify({"ok": True, "status": None})

    # what students should see as feedback (newest non-empty across all attempts)
    student_visible_feedback = _latest_student_feedback(ch.id, me) or None

    return jsonify({
        "ok": True,
        "status": getattr(latest, 'status', 'approved' if getattr(latest, 'approved', False) else 'pending'),
        "points": getattr(latest, 'points', None),
        "feedback": student_visible_feedback,
        "comment": student_visible_feedback,  # mirror for any old UI that reads "comment"
        "submitted_at": latest.created_at.isoformat(),
        "updated_at": latest.created_at.isoformat(),
    })

@lecture_bp.get('/api/lecture/<slug>/replays')
@require_login
def list_public_replays(slug):
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()

    # fetch first; we’ll do Python-side filtering so it works with/without a .section column
    rows_all = (LectureSubmission.query
                .filter_by(challenge_id=ch.id, public_replay=True, status='approved')
                .order_by(LectureSubmission.created_at.asc())
                .all())

    if _get_replays_scope(ch):
        viewer_section = student_section()
        if not viewer_section:
            return jsonify({"ok": True, "items": []})
        rows = [s for s in rows_all if _submission_section(s) == str(viewer_section)]
    else:
        rows = rows_all

    return jsonify({
        "ok": True,
        "items": [
            {"submission_id": s.id, "netid": s.netid, "submitted_at": s.created_at.isoformat()}
            for s in rows
        ]
    })


@lecture_bp.get('/lecture/submission/<int:sid>')
@require_login
def view_public_replay(sid):
    sub = LectureSubmission.query.get_or_404(sid)

    # Only show if it’s actually published (and approved if you require that)
    if hasattr(sub, 'public_replay') and not sub.public_replay:
        abort(404)
    if hasattr(sub, 'status') and sub.status != 'approved':
        abort(404)
    if hasattr(sub, 'approved') and not sub.approved:
        abort(404)

    # Enforce section scope when enabled
    ch = sub.challenge  # relationship is already used later for slug
    if _get_replays_scope(ch):
        viewer_section = student_section()
        if viewer_section and str(_submission_section(sub)) != str(viewer_section):
            abort(403)

    return render_template(
        'lecture_replay.html',
        sub=sub,                      # has .netid, .code, .run_output, .created_at
        slug=sub.challenge.slug if hasattr(sub, 'challenge') else None
    )


#@lecture_bp.get('/api/lecture/<slug>/replays')
#@require_login
#def lecture_replays(slug):
#    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()
#    q = LectureSubmission.query.filter_by(challenge_id=ch.id, public_replay=True)
#    # honor status column if present, else fall back to approved flag
#    if hasattr(LectureSubmission, 'status'):
#        q = q.filter(LectureSubmission.status == 'approved')
#    else:
#        q = q.filter(LectureSubmission.approved.is_(True))
#    rows = q.order_by(LectureSubmission.created_at.asc()).all()
#    return jsonify({"ok": True, "items": [
#        {"submission_id": r.id, "display_name": r.netid, "submitted_at": r.created_at.isoformat()}
#        for r in rows
#    ]})


@lecture_bp.get('/api/lecture/submission/<int:sid>/replay')
@require_login
def get_replay(sid):
    sub = LectureSubmission.query.get_or_404(sid)
    owner = (session.get('netid') == sub.netid)
    admin = is_admin_current_user()

    # If not owner/admin, the replay must be actually public *and* approved
    if not owner and not admin:
        is_public = bool(getattr(sub, 'public_replay', False))
        is_approved = (
            (hasattr(sub, 'status') and getattr(sub, 'status') == 'approved') or
            (hasattr(sub, 'approved') and getattr(sub, 'approved') is True)
        )
        if not (is_public and is_approved):
            abort(403)

        # Enforce same-section scoping when the challenge requires it
        ch = sub.challenge
        if _get_replays_scope(ch):
            vsec = student_section()
            if not vsec or str(_submission_section(sub)) != str(vsec):
                abort(403)

    return jsonify({
        "ok": True,
        "code": sub.code,
        "keystrokes": sub.keystrokes_json,
        "run_output": sub.run_output,
        "meta": {
            "display_name": sub.netid,
            "submitted_at": sub.created_at.isoformat(),
            "language": sub.language
        }
    })


# === Admin views/APIs ===
SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9\-]{1,62}[a-z0-9]$')

#@lecture_bp.get("/admin/lecture/new")
#def admin_lecture_new():
    #return session.get("netid"), 200  # <-- TEMP
    #print("lecture.py /admin/lecture/new page netid:", session.get("netid"))
    #if not is_admin_current_user():
        #abort(403)
    #recent = LectureChallenge.query.order_by(LectureChallenge.created_at.desc()).limit(25).all()
    #return render_template("admin_lecture_new.html", recent=recent)

#from flask import current_app
#from sqlalchemy import text

@lecture_bp.get('/admin/lecture/new')
def admin_lecture_new():
    if not is_admin_current_user():
        abort(403)

    # 1) quick DB health check (doesn't create tables)
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        current_app.logger.error("DB healthcheck failed: %s", e)
        recent = []   # keep the form usable
    else:
        # 2) safe recent list (handle empty or missing table gracefully)
        try:
            recent = (LectureChallenge.query
                      .order_by(LectureChallenge.created_at.desc())
                      .limit(25).all())
        except Exception as e:
            current_app.logger.error("Recent query failed: %s", e)
            recent = []

    return render_template('admin_lecture_new.html', recent=recent)

# lecture.py
@lecture_bp.post('/api/admin/lecture')
def admin_create_lecture():
    if not is_admin_current_user():
        abort(403)
    try:
        data = request.get_json(force=True) or {}
        slug = (data.get('slug') or '').strip().lower()
        title = (data.get('title') or '').strip()
        prompt_md = data.get('prompt_md') or ''
        is_open = bool(data.get('is_open', True))
        show_lb = bool(data.get('show_leaderboard', True))

        if not SLUG_RE.match(slug):
            return jsonify({"ok": False, "error": "Invalid slug (lowercase letters, digits, dashes; 2–64 chars)."}), 400
        if not title:
            return jsonify({"ok": False, "error": "Title required."}), 400
        if LectureChallenge.query.filter_by(slug=slug).first():
            return jsonify({"ok": False, "error": "Slug already exists."}), 409

        ch = LectureChallenge(slug=slug, title=title, prompt_md=prompt_md,
                              is_open=is_open, show_leaderboard=show_lb)
        db.session.add(ch); db.session.commit()

        try:
            from extensions_redis import r as redis_client
            doc = {"slug": slug, "title": title, "prompt_md": prompt_md,
                   "is_open": is_open, "show_leaderboard": show_lb}
            redis_client.set(f"lecture:challenge:{slug}", json.dumps(doc))
            redis_client.lrem("lecture:list", 0, slug)
            redis_client.lpush("lecture:list", slug)
        except Exception as e:
            current_app.logger.warning("Redis mirror failed (create %s): %s", slug, e)

        return jsonify({"ok": True, "redirect": url_for('lecture.admin_lecture', slug=slug)})
    except Exception as e:
        current_app.logger.exception("Create lecture failed")
        return jsonify({"ok": False, "error": str(e)}), 500


#@lecture_bp.patch('/api/admin/lecture/submission/<int:sid>')
#def admin_update_submission(sid):
#    if not is_admin_current_user():
#        abort(403)
#    sub = LectureSubmission.query.get_or_404(sid)
#    data = request.get_json(force=True) or {}
#
#    if 'points' in data:
#        sub.points = int(data['points'])
#
#    if 'status' in data:
#        s = data['status']
#        if s not in ('pending','approved','rejected'):
#            return jsonify({"ok": False, "error": "invalid status"}), 400
#        # write to DB if column exists
#        if hasattr(sub, 'status'):
#            sub.status = s
#        sub.approved = (s == 'approved')  # keep legacy flag consistent
#
#    if 'feedback' in data and hasattr(sub, 'feedback'):
#        sub.feedback = data['feedback']
#
#    if 'public_replay' in data:
#        sub.public_replay = bool(data['public_replay'])
#
#    db.session.commit()
#
#    # Mirror to Redis (best-effort, so student polls see it even before a reload)
#    try:
#        from extensions_redis import r as redis_client
#        k = f"lecture:submissions:{sub.challenge.slug}"
#        lst = redis_client.lrange(k, 0, -1)
#        for idx, raw in enumerate(lst):
#            sdoc = json.loads(raw)
#            if str(sdoc.get('id')) == str(sub.id):
#                sdoc['points'] = sub.points
#                sdoc['approved'] = sub.approved
#                sdoc['public_replay'] = sub.public_replay
#                sdoc['status'] = getattr(sub, 'status', 'approved' if sub.approved else 'pending')
#                sdoc['feedback'] = getattr(sub, 'feedback', None)
#                redis_client.lset(k, idx, json.dumps(sdoc))
#                break
#    except Exception as e:
#        current_app.logger.warning("Redis mirror failed (admin update %s): %s", sid, e)
#
#    return jsonify({"ok": True})


@lecture_bp.get('/admin/lecture/<slug>')
def admin_lecture(slug):
    if not is_admin_current_user():
        abort(403)
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()
    subs = (LectureSubmission.query
            .filter_by(challenge_id=ch.id)
            .order_by(LectureSubmission.created_at.desc()).all())
    if request.args.get('partial') == '1':
        return render_template('admin_lecture_rows.html', subs=subs)
    return render_template('admin_lecture.html', ch=ch, subs=subs, sections=all_sections())

@lecture_bp.get('/api/admin/lecture/<slug>/submissions')
def admin_list_submissions(slug):
    if not is_admin_current_user():
        abort(403)
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()

    q = (LectureSubmission.query
         .filter_by(challenge_id=ch.id)
         .order_by(LectureSubmission.created_at.asc()))

    status = request.args.get('status')
    if status == 'replay':
        q = q.filter(LectureSubmission.public_replay.is_(True))
    if status in ('pending', 'approved', 'rejected'):
        if hasattr(LectureSubmission, 'status'):
            q = q.filter(LectureSubmission.status == status)
        else:
            if status == 'pending':
                q = q.filter(LectureSubmission.approved.is_(False))
            elif status == 'approved':
                q = q.filter(LectureSubmission.approved.is_(True))
            else:
                q = q.filter(LectureSubmission.approved.is_(False))

    rows = q.all()
    def _pick_feedback(sub):
        for attr in ('feedback', 'comment', 'feedback_text', 'notes'):
            if hasattr(sub, attr):
                val = getattr(sub, attr) or ''
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return ''

    def _latest_student_feedback(challenge_id, netid):
        subs = (LectureSubmission.query
                .filter_by(challenge_id=challenge_id, netid=netid)
                .order_by(LectureSubmission.created_at.desc())
                .all())
        for s in subs:
            f = _pick_feedback(s)
            if f:
                return f
        return ''

    def row_status(s):
        if hasattr(s, 'status'):
            return s.status or 'pending'
        return 'approved' if s.approved else 'pending'

    rows_out = []
    for s in rows:
        rows_out.append({
            "id": s.id,
            "netid": s.netid,
            "section": section_for_netid(s.netid),
            "status": row_status(s),
            "public_replay": bool(getattr(s, 'public_replay', False)),
            "created_at": s.created_at.isoformat(),
            # NEW: per-submission preview (what’s on THIS row)
            "feedback_display": _pick_feedback(s) or None,
            # NEW: exactly what the student will see (newest non-empty across attempts)
            "student_visible_feedback": _latest_student_feedback(s.challenge_id, s.netid) or None,
        })

    return jsonify({"ok": True, "items": rows_out})


@lecture_bp.patch('/api/admin/lecture/submission/<int:sid>')
def admin_patch_submission(sid):
    if not is_admin_current_user():
        abort(403)
    sub = LectureSubmission.query.get_or_404(sid)
    data = request.get_json(force=True) or {}

    # status → approved/rejected/pending mapping
    if 'status' in data:
        s = (data['status'] or '').lower()
        if hasattr(sub, 'status'):
            if s in ('approved','rejected','pending'):
                sub.status = s
        else:
            if s == 'approved':
                sub.approved = True
            elif s == 'rejected':
                sub.approved = False
            elif s == 'pending':
                sub.approved = False

        # optional: auto toggle public_replay on approve
        if s == 'approved' and hasattr(sub, 'public_replay'):
            sub.public_replay = True

    if 'public_replay' in data and hasattr(sub, 'public_replay'):
        sub.public_replay = bool(data['public_replay'])

    # comment/feedback/notes (write to whichever field exists)
    if 'comment' in data:
        val = (data['comment'] or '').strip()
        written = False
        for attr in ('comment', 'feedback', 'feedback_text', 'notes'):
            if hasattr(sub, attr):
                setattr(sub, attr, val)
                written = True
                break
        if not written:
            # fall back to run_output suffix (last resort; remove if undesired)
            if hasattr(sub, 'run_output'):
                sub.run_output = (sub.run_output or '') + f"\n\n[ADMIN COMMENT]\n{val}"

    db.session.commit()
    return jsonify({"ok": True})

#@lecture_bp.patch('/api/admin/lecture/submission/<int:sid>')
#def admin_update_submission(sid):
#    if not is_admin_current_user():
#        abort(403)
#    sub = LectureSubmission.query.get_or_404(sid)
#    data = request.get_json(force=True) or {}
#    if 'approved' in data: sub.approved = bool(data['approved'])
#    if 'public_replay' in data: sub.public_replay = bool(data['public_replay'])
#    if 'points' in data: sub.points = int(data['points'])
#    db.session.commit()
#    return jsonify({"ok": True})

@lecture_bp.delete('/api/admin/lecture/<slug>')
def admin_delete_lecture(slug):
    if not is_admin_current_user():
        abort(403)
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()

    # Delete submissions first (FK integrity)
    LectureSubmission.query.filter_by(challenge_id=ch.id).delete()
    db.session.delete(ch)
    db.session.commit()

    for room in _rooms_for(ch):
        socketio.emit("active_lecture_changed", None, to=room)

    # Redis cleanup (best-effort)
    try:
        from extensions_redis import r as redis_client
        redis_client.delete(f"lecture:challenge:{slug}")
        redis_client.delete(f"lecture:submissions:{slug}")
        redis_client.lrem("lecture:list", 0, slug)
    except Exception as e:
        current_app.logger.warning("Redis mirror failed (delete %s): %s", slug, e)

    return jsonify({"ok": True})


@lecture_bp.patch('/api/admin/lecture/<slug>/settings')
def admin_update_challenge(slug):
    if not is_admin_current_user():
        abort(403)
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()

    # --- capture old rooms BEFORE changes ---
    old_rooms = set(_rooms_for(ch))

    data = request.get_json(force=True) or {}
    for key in ('is_open', 'show_leaderboard'):
        if key in data:
            setattr(ch, key, bool(data[key]))

    if 'history_enabled' in data: ch.history_enabled = bool(data['history_enabled'])
    if 'replays_same_section_only' in data:
        val = bool(data['replays_same_section_only'])
        # write to DB if the model has the column
        if hasattr(ch, 'replays_same_section_only'):
            ch.replays_same_section_only = val
        # always mirror to Redis so readers can see it
        _set_replays_scope(ch.slug, val)
    if 'section_scope' in data:
        val = data['section_scope']
        if isinstance(val, list):
            ch.section_scope = 'ALL' if not val or val == ['ALL'] else ','.join(str(v).strip() for v in val)
        else:
            ch.section_scope = (val or '').strip() or None
    if 'open_at' in data:
        ch.open_at = _parse_dt(data['open_at'])
    if 'close_at' in data:
        ch.close_at = _parse_dt(data['close_at'])
    db.session.commit()

     # --- compute new rooms AFTER changes ---
    new_rooms = set(_rooms_for(ch))

    # send fresh payload to new/kept rooms
    payload = _payload_for(ch)
    for room in new_rooms:
        socketio.emit("active_lecture_changed", payload, to=room)

    # send CLEAR to rooms that lost access
    for room in (old_rooms - new_rooms):
        socketio.emit("active_lecture_changed", None, to=room)

    return jsonify({"ok": True})
