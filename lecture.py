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


lecture_bp = Blueprint('lecture', __name__)

# === Helpers ===
ADMIN_NETIDS = { 'nh385' }

import csv, os, time
from functools import lru_cache

ROSTER_CSV = os.environ.get(
    "ROSTER_CSV",
    os.path.join(os.path.dirname(__file__), "data", "github_roster.csv")
)

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
    if not os.path.exists(ROSTER_CSV):
        return m
    with open(ROSTER_CSV, newline="", encoding="utf-8") as f:
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

def refresh_roster_cache():
    """Call this if you replace the CSV at runtime (optional admin hook)."""
    _roster_map.cache_clear()
    _roster_map()


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
    netid = session['netid']
    display = lookup_display_name(netid)
    return render_template('lecture_challenge.html', ch=ch, netid=netid, display_name=display)

@lecture_bp.post('/api/lecture/<slug>/submit')
@require_login
def submit_lecture(slug):
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()
    if not ch.is_open:
        return jsonify({"ok": False, "error": "Submissions are closed."}), 403
    try:
        data = request.get_json(force=True) or {}
        code = data.get('code', '')
        if not code.strip():
            return jsonify({"ok": False, "error": "Empty submission."}), 400

        sub = LectureSubmission(
            challenge_id=ch.id,
            netid=session['netid'],
            display_name=lookup_display_name(session['netid']),
            code=code,
            keystrokes_json=data.get('keystrokes'),
            run_output=data.get('run_output'),
            runtime_ms=data.get('runtime_ms')
        )
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
        {"display_name": public_display_name(r.netid, include_section=False), "points": r.points, "submitted_at": r.created_at.isoformat(), "submission_id": r.id}
        for r in rows
    ]})

@lecture_bp.get('/api/lecture/<slug>/my_status')
@require_login
def my_status(slug):
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()
    me = session['netid']
    sub = (LectureSubmission.query
           .filter_by(challenge_id=ch.id, netid=me)
           .order_by(LectureSubmission.created_at.desc())
           .first())
    if not sub:
        return jsonify({"ok": True, "status": None})
    return jsonify({
        "ok": True,
        "status": getattr(sub, 'status', 'approved' if sub.approved else 'pending'),
        "points": sub.points,
        "feedback": getattr(sub, 'feedback', None),
        "submitted_at": sub.created_at.isoformat(),
        "updated_at": sub.created_at.isoformat(),
    })


@lecture_bp.get('/api/lecture/<slug>/replays')
@require_login
def lecture_replays(slug):
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()
    q = LectureSubmission.query.filter_by(challenge_id=ch.id, public_replay=True)
    # honor status column if present, else fall back to approved flag
    if hasattr(LectureSubmission, 'status'):
        q = q.filter(LectureSubmission.status == 'approved')
    else:
        q = q.filter(LectureSubmission.approved.is_(True))
    rows = q.order_by(LectureSubmission.created_at.asc()).all()
    return jsonify({"ok": True, "items": [
        {"submission_id": r.id, "display_name": public_display_name(r.netid, include_section=False), "submitted_at": r.created_at.isoformat()}
        for r in rows
    ]})


@lecture_bp.get('/api/lecture/submission/<int:sid>/replay')
@require_login
def get_replay(sid):
    sub = LectureSubmission.query.get_or_404(sid)
    owner = (session.get('netid') == sub.netid)
    if not (owner or sub.public_replay or is_admin_current_user()):
        abort(403)
    return jsonify({
        "ok": True,
        "code": sub.code,
        "keystrokes": sub.keystrokes_json,
        "run_output": sub.run_output,
        "meta": {"display_name": sub.display_name, "submitted_at": sub.created_at.isoformat(), "language": sub.language}
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


@lecture_bp.patch('/api/admin/lecture/submission/<int:sid>')
def admin_update_submission(sid):
    if not is_admin_current_user():
        abort(403)
    sub = LectureSubmission.query.get_or_404(sid)
    data = request.get_json(force=True) or {}

    if 'points' in data:
        sub.points = int(data['points'])

    if 'status' in data:
        s = data['status']
        if s not in ('pending','approved','rejected'):
            return jsonify({"ok": False, "error": "invalid status"}), 400
        # write to DB if column exists
        if hasattr(sub, 'status'):
            sub.status = s
        sub.approved = (s == 'approved')  # keep legacy flag consistent

    if 'feedback' in data and hasattr(sub, 'feedback'):
        sub.feedback = data['feedback']

    if 'public_replay' in data:
        sub.public_replay = bool(data['public_replay'])

    db.session.commit()

    # Mirror to Redis (best-effort, so student polls see it even before a reload)
    try:
        from extensions_redis import r as redis_client
        k = f"lecture:submissions:{sub.challenge.slug}"
        lst = redis_client.lrange(k, 0, -1)
        for idx, raw in enumerate(lst):
            sdoc = json.loads(raw)
            if str(sdoc.get('id')) == str(sub.id):
                sdoc['points'] = sub.points
                sdoc['approved'] = sub.approved
                sdoc['public_replay'] = sub.public_replay
                sdoc['status'] = getattr(sub, 'status', 'approved' if sub.approved else 'pending')
                sdoc['feedback'] = getattr(sub, 'feedback', None)
                redis_client.lset(k, idx, json.dumps(sdoc))
                break
    except Exception as e:
        current_app.logger.warning("Redis mirror failed (admin update %s): %s", sid, e)

    return jsonify({"ok": True})


# lecture.py

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
    return render_template('admin_lecture.html', ch=ch, subs=subs)

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
    data = request.get_json(force=True) or {}
    for key in ('is_open', 'show_leaderboard'):
        if key in data:
            setattr(ch, key, bool(data[key]))
    db.session.commit()
    return jsonify({"ok": True})
