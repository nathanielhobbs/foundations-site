# practice.py
from flask import Blueprint, render_template, abort, request, jsonify, session
from practice_bank_loader import load_practice_bank, index_by_slug
from datetime import datetime
from extensions import db
from models_practice import PracticeProgress

bp = Blueprint("practice", __name__, url_prefix="/practice")
api_bp = Blueprint("practice_api", __name__, url_prefix="/api/practice")


def record_practice_attempt(netid: str, slug: str, section: int | None, passed: bool):
    now = datetime.utcnow()
    row = PracticeProgress.query.filter_by(netid=netid, slug=slug).first()
    if not row:
        row = PracticeProgress(netid=netid, slug=slug, section=section, attempts=0)
        db.session.add(row)

    row.attempts = int(row.attempts or 0) + 1
    row.last_attempt_at = now
    if section is not None:
        row.section = section
    if passed and row.completed_at is None:
        row.completed_at = now

    db.session.commit()
    return row

@bp.get("/")
def practice_index():
    all_problems = load_practice_bank()

    def val(p, name, default=""):
        if isinstance(p, dict):
            v = p.get(name, default)
        else:
            v = getattr(p, name, default)
        return default if v is None else v

    # build topic list for filters/quick links (always from ALL problems)
    topics = sorted({val(p, "topic", "") for p in all_problems if val(p, "topic", "")})

    # query params = "topic pages"
    topic_q = (request.args.get("topic") or "").strip()
    diff_q  = (request.args.get("difficulty") or "").strip()
    q       = (request.args.get("q") or "").strip().lower()
    sort    = (request.args.get("sort") or "").strip()

    problems = all_problems

    # filter
    if topic_q:
        problems = [p for p in problems if val(p, "topic", "") == topic_q]
    if diff_q:
        problems = [p for p in problems if val(p, "difficulty", "") == diff_q]
    if q:
        problems = [p for p in problems if q in val(p, "title", "").lower()]

    # sort
    rank = {"easy": 1, "medium": 2, "hard": 3}

    def key_topic_then_diff(p):
        return (val(p, "topic", ""), rank.get(val(p, "difficulty", ""), 99), val(p, "title", "").lower())

    def key_diff_then_title(p):
        return (rank.get(val(p, "difficulty", ""), 99), val(p, "title", "").lower())

    if sort == "title":
        problems.sort(key=lambda p: val(p, "title", "").lower())
    elif sort == "difficulty":
        problems.sort(key=key_diff_then_title)
    elif sort == "topic":
        problems.sort(key=key_topic_then_diff)
    else:
        # default behavior:
        # - if you're on a topic page: easy -> hard
        # - otherwise: topic -> (easy->hard)
        problems.sort(key=key_diff_then_title if topic_q else key_topic_then_diff)

    return render_template("practice/index.html", problems=problems, topics=topics)


@bp.get("/<path:slug>")
def practice_problem(slug: str):
    problems = load_practice_bank()
    by_slug = index_by_slug(problems)
    p = by_slug.get(slug)
    if not p:
        abort(404)
    return render_template("practice/problem.html", p=p)

@api_bp.post("/attempt")
def practice_attempt():
    netid = session.get("netid")
    if not netid:
        return jsonify({"ok": False, "error": "not_logged_in"}), 401

    j = request.get_json(force=True) or {}
    slug = (j.get("slug") or "").strip()
    passed = bool(j.get("passed"))

    if not slug:
        return jsonify({"ok": False, "error": "missing_slug"}), 400

    row = record_practice_attempt(netid, slug, session.get("section"), passed)

    return jsonify({
        "ok": True,
        "attempts": row.attempts,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    })


@api_bp.get("/progress")
def practice_progress():
    netid = session.get("netid")
    if not netid:
        return jsonify({"ok": False, "error": "not_logged_in"}), 401

    rows = PracticeProgress.query.filter_by(netid=netid).all()
    prog = {
        r.slug: {
            "attempts": int(r.attempts or 0),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None
        }
        for r in rows
    }
    return jsonify({"ok": True, "progress": prog})

