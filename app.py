import os
from pathlib import Path
import glob
import shlex
import difflib
from markupsafe import Markup, escape
import requests
import traceback
from dotenv import load_dotenv
from flask import Flask, render_template, request, Response, abort, redirect, url_for, session, make_response, g
import pandas as pd
from flask_socketio import emit, join_room, disconnect
from extensions import socketio
from lecture_utils import is_open_now, current_active_lecture_for, student_can_access
import redis
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math
import json
import re
from flask import session as flask_session
import pytz
from flask import jsonify
from uuid import uuid4
import io
import contextlib
from extensions import db
import base64
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from flask import flash, abort  
from autograde_lib import run_autograde, ASSIGNMENTS
from models_homework import HomeworkSubmission
from docker_grader import run_pytest_in_docker,run_python_in_docker
from homework_defs import HOMEWORKS

BASE_DIR = Path(__file__).resolve().parent

TZ_NAME = "America/New_York"  # or "UTC" if you prefer comparing in UTC
TZ = ZoneInfo(TZ_NAME)

LATE_PENALTY_PER_DAY = 0.05   # 5% per day late
MAX_LATE_PENALTY = 1.0        # cap at 100% off

load_dotenv()

SECTION_REPOS = {
  #  "1": "foundations-f25-sec1",
  #  "2": "foundations-f25-sec2",
  #  "5": "foundations-f25-sec5",
  #  "6": "foundations-f25-sec6",
  "42": "foundations-s26-sec42",
}

app = Flask(__name__)
# Bump cookie name so old cookies get ignored by the browser:
app.config["SESSION_COOKIE_NAME"] = "foundations_sess_v2"
app.config['SESSION_COOKIE_DOMAIN'] = os.environ.get('SESSION_COOKIE_DOMAIN') 
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = True   # keep True if you serve HTTPS
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=14)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config['ADMIN_NETID'] = os.environ.get('ADMIN_NETID') 
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD') 
app.config['ROSTER_FILE'] = os.environ.get('ROSTER_FILE') 

#CURRENT_LOGIN_VERSION = "2025-09-24-username-reset"
CURRENT_LOGIN_VERSION = "2026-spring"


#app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://foundations:foundation$P4ss;@localhost/foundations_site"
# Initialize SQLAlchemy (uses app.config['SQLALCHEMY_DATABASE_URI'])
#db.init_app(app)


# --- DB config ---
#app.config.setdefault(
#    "SQLALCHEMY_DATABASE_URI",
#    os.environ.get("DATABASE_URL", "sqlite:///site.db")
#)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI') 
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,  # avoid stale connections
    "pool_recycle": 1800,
    "pool_timeout": 10,     # fail fast instead of hanging forever
}

socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")
db.init_app(app)

from lecture import lecture_bp
app.register_blueprint(lecture_bp)

from practice import bp as practice_bp, api_bp as practice_api_bp
app.register_blueprint(practice_bp)
app.register_blueprint(practice_api_bp)

# Make sure models are imported before create_all()
from models_lecture import LectureChallenge, LectureSubmission
from models_practice import PracticeProgress


class TutorialState(db.Model):
    __tablename__ = "tutorial_state"
    id = db.Column(db.Integer, primary_key=True)
    netid = db.Column(db.String(64), nullable=False, index=True)
    course = db.Column(db.String(64), nullable=False)
    lesson = db.Column(db.String(128), nullable=False)
    code = db.Column(db.Text, nullable=False, default="")
    progress_json = db.Column(db.Text, nullable=False, default="{}")
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("netid", "course", "lesson", name="uq_tutorial_state"),)

def _score_effective(sub: HomeworkSubmission):
    return sub.score_final_after_reopen if sub.score_final_after_reopen is not None else sub.score_final


def _aware_local(dt):
    if dt is None: return None
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)

# NOTE: Flask 3.x removed before_first_request. Just do this once at import time.
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        app.logger.warning(f"db.create_all() skipped/failed: {e}")

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

# >>> Minimal fix: use configured roster path if provided
ROSTER_FILE = app.config.get('ROSTER_FILE') or 'data/github_roster.csv'
# <<<

# EST timezone
est = pytz.timezone('US/Eastern')

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_ORG = os.environ.get("GITHUB_ORG")
GITHUB_NOTES_ORG = os.environ.get("GITHUB_NOTES_ORG")

# List of your GitHub Classroom assignments
assignments = [
    {
        "name": "HW1: Functions and Loops",
        "slug": "hw1-functions-and-loops",
        "invite_url": "https://classroom.github.com/a/xyz123"
    },
    {
        "name": "HW2: File I/O",
        "slug": "hw2-file-io",
        "invite_url": "https://classroom.github.com/a/abc789"
    }
]

# Track socket id to netid/section
socket_to_user = {}

def load_roster():
    """
    Read the roster CSV and normalize to columns:
      - netid (str)
      - first (str or '')
      - last  (str or '')
      - section (int/str or None)
    Accepts a variety of header names: NetID, net_id, username, Full Name, First Name, Last Name, Section, etc.
    """
    import pandas as _pd

    df = _pd.read_csv(ROSTER_FILE)

    # Build a case-insensitive map of existing columns
    cmap = {c.lower().strip(): c for c in df.columns}

    github_col = None
    for cand in ["github username", "github", "github_user", "github_username"]:
        if cand in cmap:
            github_col = cmap[cand]
            break

    def col(*names):
        for n in names:
            if n in cmap:
                return cmap[n]
        return None

    # Likely headers for netid/username
    net_col = col("netid", "net_id", "username", "user", "login", "canvas_id", "id")
    full_col = col("full name", "name")
    first_col = col("first name", "first")
    last_col = col("last name", "last", "surname", "family name")
    sect_col = col("section", "sec")

    # Create normalized columns
    out = _pd.DataFrame()
    if net_col is None:
        # If absolutely no netid-like column, synthesize from something stable
        # (keeps function safe; display_name will just echo input when no match)
        out["netid"] = _pd.Series([], dtype=str)
    else:
        out["netid"] = df[net_col].astype(str).str.strip()

    # Names: prefer explicit first/last; else parse "Last, First ..." from Full Name
    first = _pd.Series([""] * len(df), dtype=str)
    last  = _pd.Series([""] * len(df), dtype=str)

    if first_col is not None:
        first = df[first_col].fillna("").astype(str).str.strip()
    if last_col is not None:
        last = df[last_col].fillna("").astype(str).str.strip()

    if (first_col is None or last_col is None) and full_col is not None:
        # Try to parse "Last, First Middle"
        full = df[full_col].fillna("").astype(str).str.strip()
        # If we already have first/last, only fill missing parts
        need_first = (first_col is None)
        need_last  = (last_col is None)

        def parse_full(x):
            # Accept "Last, First M." or "First Last"
            x = x.strip()
            if "," in x:
                lastp, firstp = x.split(",", 1)
                return firstp.strip(), lastp.strip()
            parts = x.split()
            if len(parts) >= 2:
                return " ".join(parts[:-1]).strip(), parts[-1].strip()  # first, last
            return "", x

        parsed = full.apply(parse_full).tolist()
        pf = [p[0] for p in parsed]
        pl = [p[1] for p in parsed]
        if need_first:
            first = _pd.Series(pf, dtype=str)
        if need_last:
            last = _pd.Series(pl, dtype=str)

    out["first"] = first.fillna("").astype(str).str.strip()
    out["last"]  = last.fillna("").astype(str).str.strip()

    if sect_col is not None:
        out["section"] = df[sect_col]
    else:
        out["section"] = None
    #if github_col is not None:
    #    out["github"] = df[github_col].astype(str).str.strip()
    #else:
    #    out["github"] = ""

    if github_col is not None:
        # Preserve real missing values; only strip strings
        gh = df[github_col]
        out["github"] = gh.apply(lambda x: x.strip() if isinstance(x, str) else x)
    else:
        # Keep as missing (same length as df)
        out["github"] = pd.Series([pd.NA] * len(df))

    # Lowercase index for fast lookups
    out["netid_lc"] = out["netid"].str.lower()
    return out

def load_roster_raw():
    return pd.read_csv(ROSTER_FILE)

def save_roster_raw(df):
    df.to_csv(ROSTER_FILE, index=False)

def roster_row_for_netid(netid: str):
    """Return (roster_df, row_df) using normalized headers."""
    roster = load_roster()
    row = roster.loc[roster["netid_lc"] == (netid or "").lower()]
    return roster, row

@app.template_filter("due_et")
def due_et(val: str):
    if not val:
        return "—"
    dt = None
    # Try ISO first (e.g., 2025-10-28T23:59:00-04:00)
    try:
        dt = datetime.fromisoformat(val)
    except Exception:
        pass
    # Fallback to "Oct 8, 2025 03:59" style (assume ET)
    if dt is None:
        try:
            dt = datetime.strptime(val, "%b %d, %Y %H:%M")
            dt = est.localize(dt)
        except Exception:
            return val  # show raw if unparseable

    dt_et = dt.astimezone(est)
    # portable day/month formatting (no %-d portability issues)
    return dt_et.strftime("%a, %b ") + str(int(dt_et.strftime("%d"))) + dt_et.strftime(", %Y %I:%M %p ET")


def section_from_row(row):
    """Extract int section from a single-row DataFrame; return None if missing."""
    if row.empty:
        return None
    sect = row.iloc[0].get("section")
    try:
        return int(sect)
    except Exception:
        return None

def get_display_name(netid):
    """
    Return 'netid' (and Section if available), else fallback to netid.
    """
    try:
        roster, row = roster_row_for_netid(netid)
        if row.empty:
            return netid

        sect  = row.iloc[0].get("section")

        # Build base name
        name = netid

        # Append section if present
        if pd.notna(sect) and str(sect).strip() != "":
            try:
                return f"{name} (Section {int(sect)})"
            except Exception:
                return f"{name} (Section {sect})"

        return name
    except Exception as e:
        print(f"Roster lookup failed for {netid}: {e}")
        return netid


def save_roster(df):
    df.to_csv(ROSTER_FILE, index=False)

def _parse_due_at(hw: dict):
    """
    Accepts HOMEWORKS[slug]["due_at"] as either:
      - ISO string (preferred), or
      - "YYYY-MM-DD HH:MM" (assumed TZ local)
    Returns aware datetime in TZ or None.
    """
    s = (hw or {}).get("due_at")
    if not s:
        return None
    s = str(s).strip()

    # ISO first
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)
    except Exception:
        pass

    # "YYYY-MM-DD HH:MM"
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        return dt
    except Exception:
        return None


def _late_info(due_at: datetime | None, submitted_at: datetime):
    if not due_at:
        return (0, 0)
    sec = int(max(0, (submitted_at - due_at).total_seconds()))
    days = int(math.ceil(sec / 86400)) if sec > 0 else 0
    return (sec, days)


def _score_from_pytest_result(result: dict):
    passed = int(result.get("passed") or 0)
    failed = int(result.get("failed") or 0)
    denom = passed + failed
    if denom <= 0:
        return None
    return 100.0 * (passed / denom)

def _passed_failed_from_submission(sub: HomeworkSubmission):
    """
    Return (passed, failed) from stored result_json.
    Handles missing/old rows safely.
    """
    try:
        j = json.loads(sub.result_json or "{}")
        passed = int(j.get("passed") or 0)
        failed = int(j.get("failed") or 0)
        return passed, failed
    except Exception:
        return 0, 0


def _penalty_frac_for_late_days(late_days: int):
    return min(MAX_LATE_PENALTY, max(0.0, late_days * LATE_PENALTY_PER_DAY))


def _aware(dt, tz: ZoneInfo):
    """
    Return a timezone-aware datetime in tz.
    - If dt is None -> None
    - If dt is naive -> attach tz (treat stored value as tz-local wall time)
    - If dt is aware -> convert to tz
    """
    if dt is None:
        return None
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)

def _is_open_now(ch, *, now: datetime | None = None, tz: ZoneInfo | None = None) -> bool:
    tz = tz or ZoneInfo(TZ_NAME)
    now = now or datetime.now(tz)

    open_at  = _aware(ch.open_at, tz)
    close_at = _aware(ch.close_at, tz)

    if open_at and now < open_at:
        return False
    if close_at and now > close_at:
        return False
    # gate by the manual toggle as well
    return bool(getattr(ch, "is_open", False))

# This just set a redis key, it doesn't touch the DB
@app.post("/admin/lecture/<slug>/activate")
def activate_lecture(slug):
    # Require admin
    if not session.get("is_admin"):
        abort(403)
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()
    r.set("lecture_challenge:active_slug", ch.slug)

    try:
        socketio.emit(
            "active_lecture_changed",
            {"slug": ch.slug, "title": ch.title},
            broadcast=True,
        )
    except Exception as e:
        app.logger.warning(f"socketio emit failed: {e}")

    # Optional: UX nicety if you use flashes; if not, harmless.
    try:
        flash(f'"{ch.title}" is now the active lecture challenge.', "success")
    except Exception:
        pass

    # Redirect back to that challenge’s admin page if it exists
    return redirect(f"/admin/lecture/{ch.slug}")

# This just set a redis key, it doesn't touch the DB
@app.post("/admin/lecture/clear-active")
def clear_active_lecture():
    if not session.get("is_admin"):
        abort(403)
    r.delete("lecture_challenge:active_slug")
    try:
        socketio.emit("active_lecture_changed", None, broadcast=True)
    except Exception as e:
        app.logger.warning(f"socketio emit failed: {e}")
    try:
        flash("Cleared active lecture challenge.", "info")
    except Exception:
        pass
    return redirect("/admin/lecture/new")

#@app.get("/time/")
#def get_time():
#    return render_template("time.html")
@app.route("/time")
def time_page():
    now = datetime.now(ZoneInfo("America/New_York"))
    return render_template("time.html", now=now)

@app.route("/repl")
def repl():
    return render_template("repl.html")

@app.get("/grades")
def my_grades_page():
    if not session.get("netid"):
        return redirect(url_for("login"))  # or your login route

    netid = session["netid"]

    finals = (HomeworkSubmission.query
        .filter_by(netid=netid, is_final=1)
        .order_by(HomeworkSubmission.slug.asc(), HomeworkSubmission.created_at.desc())
        .all())

    # keep only latest final per slug
    latest = {}
    for s in finals:
        if s.slug not in latest:
            latest[s.slug] = s

    rows = []
    for slug, s in sorted(latest.items(), key=lambda kv: kv[0]):
        rows.append({
            "slug": slug,
            "title": HOMEWORKS.get(slug, {}).get("title", slug),
            "submitted_at": s.submitted_at or (s.created_at.isoformat() if s.created_at else None),
            "due_at": s.due_at,
            "late_days": s.late_days,
            "score_raw": s.score_raw,
            "penalty_frac": s.penalty_frac,
            "reopen_penalty_frac": s.reopen_penalty_frac,
            "score_final": s.score_final,
            "score_effective": _score_effective(s),
        })

    return render_template("my_grades.html", rows=rows)

@app.get("/admin/grades")
def admin_grades_page():
    if not (session.get("netid") and session.get("is_admin")):
        return "Forbidden", 403

    slug = (request.args.get("slug") or "").strip()
    section = (request.args.get("section") or "").strip()

    q = HomeworkSubmission.query   # <-- remove .filter_by(is_final=1)

    if slug:
        q = q.filter_by(slug=slug)
    if section:
        try:
            q = q.filter_by(section=int(section))
        except Exception:
            pass

    subs = q.order_by(
        HomeworkSubmission.slug.asc(),
        HomeworkSubmission.section.asc(),
        HomeworkSubmission.netid.asc(),
        HomeworkSubmission.created_at.desc()
    ).all()

    # latest submit per (slug, netid)
    latest = {}
    for s in subs:
        k = (s.slug, s.netid)
        if k not in latest:
            latest[k] = s

    rows = []
    for (slug2, netid2), s in sorted(latest.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        rows.append({
            "id": s.id,
            "slug": slug2,
            "title": HOMEWORKS.get(slug2, {}).get("title", slug2),
            "netid": netid2,
            "section": s.section,
            "submitted_at": s.submitted_at or (s.created_at.isoformat() if s.created_at else None),
            "due_at": s.due_at,
            "late_days": s.late_days,
            "score_raw": s.score_raw,
            "penalty_frac": s.penalty_frac,
            "reopen_penalty_frac": s.reopen_penalty_frac,
            "score_final": s.score_final,
            "score_effective": _score_effective(s),

            # add a simple status for the table
            "status": ("FINAL" if s.is_final == 1 else ("REOPENED" if s.reopened_at else "OLD")),
            "reopened_at": s.reopened_at,
        })

    return render_template("admin_grades.html", rows=rows, slug=slug, section=section, homeworks=HOMEWORKS)

@app.get("/admin/lecture/")
def admin_lecture_index():
    if not session.get("is_admin"):
        abort(403)

    # Fetch all, newest first
    challenges = (LectureChallenge.query
                  .order_by(LectureChallenge.created_at.desc())
                  .all())

    active_slug = None
    try:
        val = r.get("lecture_challenge:active_slug")
        if val:
            active_slug = val.decode("utf-8") if isinstance(val, (bytes, bytearray)) else str(val)
    except Exception:
        active_slug = None

    # If you already defined _is_open_now elsewhere, reuse it.
    #def _open_now(ch):
    #    return _is_open_now(ch) if "_is_open_now" in globals() else (
    #        ch.is_open and
    #        (ch.open_at is None or datetime.now(est) >= (ch.open_at.astimezone(est) if ch.open_at.tzinfo else ch.open_at)) and
    #        (ch.close_at is None or datetime.now(est) <= (ch.close_at.astimezone(est) if ch.close_at.tzinfo else ch.close_at))
    #    )

    # Jinja helper (used in admin_lecture_index.html)
    def _open_now(ch):
        return _is_open_now(ch)

    return render_template("admin_lecture_index.html",
                           challenges=challenges,
                           active_slug=active_slug,
                           open_now_fn=_open_now)

# --- Admin: toggle a challenge's is_open flag ---
@app.post("/admin/lecture/<slug>/toggle-open")
def toggle_open_lecture(slug):
    if not session.get("is_admin"):
        abort(403)
    ch = LectureChallenge.query.filter_by(slug=slug).first_or_404()
    ch.is_open = not bool(ch.is_open)
    db.session.commit()
    try:
        flash(f'{"Opened" if ch.is_open else "Closed"} "{ch.title}".', "success")
    except Exception:
        pass
    return redirect("/admin/lecture/")


def list_notebooks_from_github(repo, folder="notebooks"):
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}

    # contents endpoint (avoid trailing slash when folder == "")
    url = f"https://api.github.com/repos/{GITHUB_NOTES_ORG}/{repo}/contents" + (f"/{folder}" if folder else "")
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code != 200:
        app.logger.warning(
            "GitHub notebooks failed: org=%s repo=%s folder=%s status=%s body=%s",
            GITHUB_NOTES_ORG, repo, folder, resp.status_code, resp.text[:200]
        )
        return []

    items = []
    allowed = {".ipynb", ".py", ".zip"}
    for file in resp.json():
        name = file["name"]
        ext = next((e for e in allowed if name.lower().endswith(e)), None)
        if not ext:
            continue

        # unified path
        path = f"{folder + '/' if folder else ''}{name}"

        # last-commit time for this file
        commits_url = f"https://api.github.com/repos/{GITHUB_NOTES_ORG}/{repo}/commits"
        params = {"path": path, "per_page": 1}
        c_resp = requests.get(commits_url, headers=headers, params=params)
        commit_date = c_resp.json()[0]["commit"]["committer"]["date"] if (c_resp.status_code == 200 and c_resp.json()) else None

        raw_url = f"https://raw.githubusercontent.com/{GITHUB_NOTES_ORG}/{repo}/main/{path}"
        base = name[: -len(ext)] if ext != ".zip" else name

        items.append({
            "title": base,
            "filename": name,
            "ext": ext,
            "kind": {".ipynb": "Notebook", ".py": "Python file", ".zip": "Zip"}[ext],
            "github_path": f"{GITHUB_NOTES_ORG}/{repo}/blob/main/{path}",
            "download_url": raw_url,
            "date": commit_date
        })

    items.sort(key=lambda x: x["date"] or "", reverse=True)
    return items

@app.route("/download_notebook/<section>/<filename>")
def download_notebook(section, filename):
    repo = SECTION_REPOS.get(section)
    if not repo:
        abort(404)

    raw_url = f"https://raw.githubusercontent.com/{GITHUB_NOTES_ORG}/{repo}/main/notebooks/{filename}"
    resp = requests.get(raw_url)
    if resp.status_code != 200:
        abort(404)

    return Response(
        resp.content,
        mimetype="application/x-ipynb+json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

def github_user_exists(username):
    r = requests.get(f"https://api.github.com/users/{username}")
    return r.status_code == 200

def check_admin_auth(netid, password):
    """Check if user is admin with correct credentials"""
    return netid == app.config['ADMIN_NETID'] and password == app.config['ADMIN_PASSWORD']

def get_est_timestamp():
    """Get current timestamp in EST with date"""
    now = datetime.now(est)
    return now.strftime("%m/%d %H:%M")

def format_timestamp_for_display(timestamp_str):
    """Format timestamp for display, showing date if not today"""
    try:
        # Parse the timestamp (assuming it's in MM/DD HH:MM format)
        if ' ' in timestamp_str and timestamp_str != "[old]" and timestamp_str != "[unknown]":
            date_part, time_part = timestamp_str.split(' ', 1)
            month, day = date_part.split('/')
            hour, minute = time_part.split(':')
            
            # Create datetime object
            timestamp_dt = datetime.now(est).replace(
                month=int(month), 
                day=int(day), 
                hour=int(hour), 
                minute=int(minute),
                second=0, 
                microsecond=0
            )
            
            # Compare with today
            today = datetime.now(est).date()
            if timestamp_dt.date() == today:
                return time_part  # Just show time if today
            else:
                return timestamp_str  # Show full date/time if different day
        else:
            # For old messages or unknown timestamps, return as is
            return timestamp_str
    except:
        # If parsing fails, return original
        return timestamp_str

@app.template_filter("display_name")
def jinja_display_name(netid):
    return get_display_name(netid)


@app.template_filter("first10")
def first10(s):
    return (s or "")[:10]

@app.before_request
def enforce_canonical_host():
    # Only enforce in production; relax for localhost and static/health
    if app.debug or request.host.startswith("localhost") or request.path.startswith(("/healthz", "/static/")):
        return
    canonical = "foundations.hobbsresearch.com"
    host = request.headers.get("X-Forwarded-Host") or request.host
    if host != canonical:
        url = request.url.replace(host, canonical, 1)
        return redirect(url, code=301)


@app.before_request
def force_https_for_cookies():
    # allow health checks and local dev to pass
    if app.debug or request.host.startswith("localhost") or request.path.startswith(("/healthz", "/static/")):
        return
    # Honor proxy header (Nginx/ALB should set this)
    proto = request.headers.get("X-Forwarded-Proto", "http")
    if proto != "https":
        url = request.url.replace("http://", "https://", 1)
        return redirect(url, code=301)


# clear stale sessions if login epoch changed ---
@app.before_request
def enforce_login_version():
    if request.path.startswith(("/static/", "/favicon", "/healthz")):
        return
    if request.endpoint in {"login"}:
        return
    if session.get("netid") and session.get("login_version") != CURRENT_LOGIN_VERSION:
        session.clear()
        # route-specific auth checks will handle redirect/render

@app.context_processor
def inject_admin_netid():
    return dict(ADMIN_NETID=app.config.get("ADMIN_NETID", "admin"))

# app.py
@app.context_processor
def inject_active_lecture():
    # Only for logged-in users
    if not session.get("netid"):
        return {"active_lecture": None}

    sec = session.get("section")
    if session.get("is_admin"):
        sec = session.get("admin_view_section", sec)
    ch = None

    # If an admin has pinned an active slug in Redis, honor it
    try:
        pinned = r.get("lecture_challenge:active_slug")
        if pinned:
            cand = LectureChallenge.query.filter_by(slug=str(pinned)).first()
            if cand and student_can_access(cand, sec):
                ch = cand
    except Exception:
        pass

    # Otherwise fall back to “best open for this section right now”
    if ch is None:
        ch = current_active_lecture_for(sec)

    # Return only a minimal dict (what the header needs)
    return {"active_lecture": ({"slug": ch.slug, "title": ch.title} if ch else None)}

@app.after_request
def _no_cache_for_admin_and_lecture(resp):
    if request.path.startswith(("/lecture", "/admin")):
        resp.headers["Cache-Control"] = "no-store, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


@app.get("/_debug/lecture/<slug>/eligibility")
def debug_challenge_eligibility(slug):
    from flask import jsonify, session, abort
    chal = LectureChallenge.query.filter_by(slug=slug).first_or_404()
    slist_public_replaystudent_section = session.get("section")  # int or None
    ok, reasons = challenge_eligibility(chal, student_section)
    return jsonify({
        "slug": chal.slug,
        "eligible": ok,
        "reasons": reasons,
        "session": {
            "netid": session.get("netid"),
            "section": student_section
        },
        "chal": {
            "published": chal.published,
            "opens_at": chal.opens_at.isoformat() if chal.opens_at else None,
            "closes_at": chal.closes_at.isoformat() if chal.closes_at else None,
            "allow_submissions": getattr(chal, "allow_submissions", True),
            "sections": chal.sections,
        }
    })

@app.get("/_debug/roster_lookup")
def _debug_roster_lookup():
    if not session.get("is_admin"):
        abort(403)
    q = (request.args.get("netid") or "").strip().lower()
    if not q:
        return jsonify(error="Provide ?netid=..."), 400

    roster = load_roster()
    _, row = roster_row_for_netid(q)
    if row.empty:
        return jsonify(found=False, columns=list(roster.columns))

    rec = row.iloc[0].to_dict()
    return jsonify(found=True, record=rec, parsed_section=section_from_row(row))


@app.get("/_debug/session")
def debug_session():
    if not session.get("is_admin"):
        abort(403)
    return jsonify(dict(
        netid=session.get("netid"),
        section=session.get("section"),
        login_version=session.get("login_version"),
        cookie_secure=app.config.get("SESSION_COOKIE_SECURE"),
        samesite=app.config.get("SESSION_COOKIE_SAMESITE"),
    ))


@app.route("/login", methods=["POST"])
def login():
    netid = request.form["netid"].strip().lower()
    password = request.form.get("password", "").strip()

    # Reset session
    session.clear()
    session["netid"] = netid

    # Admin login
    if netid == app.config.get("ADMIN_NETID", "").lower():
        if password == app.config.get("ADMIN_PASSWORD", ""):
            session["is_admin"] = True
            session["section"] = None
            session["admin_view_section"] = int(next(iter(SECTION_REPOS.keys())))
            # --- stamp current login version ---
            session["login_version"] = CURRENT_LOGIN_VERSION
            return redirect(url_for("index"))
        else:
            return render_template("index.html", login_error="Invalid admin password")

    # Student login
    roster = load_roster()
    #row = roster.loc[roster["NetID"].str.lower() == netid.lower()]
    _, row = roster_row_for_netid(netid) 
    app.logger.info("LOGIN netid=%s row=%s", netid, ({} if row.empty else row.iloc[0].to_dict()))
    if not row.empty:
        section = section_from_row(row) 
        session["is_admin"] = False
        session["section"] = section
        # --- stamp current login version ---
        session["login_version"] = CURRENT_LOGIN_VERSION
        return redirect(url_for("index"))

    return render_template("index.html", login_error="NetID not found in roster")

@app.get("/course/<course>/<lesson>")
def course_lesson(course, lesson):
    if not session.get("netid"):
        return redirect(url_for("index"))

    root = (BASE_DIR / "courses" / course / lesson).resolve()
    meta = json.loads((root / "lesson.json").read_text(encoding="utf-8"))
    if not meta.get("is_open", True) and not session.get("is_admin"):
        abort(404)
    steps = meta.get("steps", [])
    for s in steps:
        pf = s.get("prompt_file")
        if pf:
            try:
                s["prompt_md"] = (root / pf).read_text(encoding="utf-8")
            except FileNotFoundError:
                s["prompt_md"] = f"# Missing file\n\nCould not find `{pf}`."
        sc = s.get("starter_file")
        if sc:
            try:
                s["starter_code"] = (root / sc).read_text(encoding="utf-8")
            except FileNotFoundError:
                s["starter_code"] = ""
    try:
        prompt_md = (root / "prompt.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        prompt_md = "# Lesson\n\nMissing `prompt.md`."

    try:
        starter = (root / "starter.py").read_text(encoding="utf-8")
    except FileNotFoundError:
        starter = ""


    st = TutorialState.query.filter_by(netid=session["netid"], course=course, lesson=lesson).first()
    if not st:
        st = TutorialState(netid=session["netid"], course=course, lesson=lesson, code=starter, progress_json="{}")
        db.session.add(st)
        db.session.commit()

    progress = json.loads(st.progress_json or "{}")


    # Build enriched steps (each step can have its own prompt + starter)
    steps = []
    for ss in meta.get("steps", []):
        sss = dict(ss)
        pf = sss.get("prompt_file")
        sf = sss.get("starter_file")

        # prompt per-step (fallback to lesson prompt.md)
        if pf:
            try:
                sss["prompt_md"] = (root / pf).read_text(encoding="utf-8")
            except FileNotFoundError:
                sss["prompt_md"] = prompt_md
        else:
            sss["prompt_md"] = prompt_md

        # starter per-step (fallback to starter.py)
        if sf:
            try:
                sss["starter_code"] = (root / sf).read_text(encoding="utf-8")
            except FileNotFoundError:
                sss["starter_code"] = starter
        else:
            sss["starter_code"] = starter

        steps.append(sss)

    return render_template(
        "course_lesson.html",
        course=course,
        lesson=lesson,
        meta=meta,
        steps=steps,
        prompt_md=prompt_md,
        initial_code=st.code,
        progress=progress,
    )

# --- Simple message relay (Redis Streams) ---
RELAY_MAX_PAYLOAD = 20_000  # chars

@app.post("/api/relay/<room>/send")
def api_relay_send(room):
    if not session.get("netid"):
        return jsonify({"error": "not_logged_in"}), 401

    data = request.get_json(force=True) or {}
    sender = (data.get("sender") or "").strip()[:64]
    to     = (data.get("to") or "").strip()[:64]
    payload = data.get("payload")

    if not room or len(room) > 64:
        return jsonify({"error": "bad_room"}), 400
    if not sender or not to:
        return jsonify({"error": "missing_sender_or_to"}), 400
    if payload is None:
        return jsonify({"error": "missing_payload"}), 400

    payload = str(payload)
    if len(payload) > RELAY_MAX_PAYLOAD:
        return jsonify({"error": "payload_too_large"}), 413

    key = f"relay:{room}"
    ts = int(datetime.now(timezone.utc).timestamp() * 1000)

    msg_id = r.xadd(key, {"sender": sender, "to": to, "payload": payload, "ts": str(ts)})
    # Optional trim so rooms don't grow forever
    r.xtrim(key, maxlen=500, approximate=True)

    return jsonify({"id": msg_id})


@app.get("/api/relay/<room>/recv")
def api_relay_recv(room):
    if not session.get("netid"):
        return jsonify({"error": "not_logged_in"}), 401

    after = (request.args.get("after") or "0-0").strip()
    want_to = (request.args.get("to") or "").strip()[:64]

    if not room or len(room) > 64:
        return jsonify({"error": "bad_room"}), 400
    if not want_to:
        return jsonify({"error": "missing_to"}), 400

    key = f"relay:{room}"

    # read up to N new messages after `after`
    resp = r.xread({key: after}, count=50, block=0)  # non-blocking (poll from client)
    if not resp:
        return jsonify({"msg": None, "cursor": after})

    _stream_key, entries = resp[0]
    cursor = after
    found = None

    for msg_id, fields in entries:
        cursor = msg_id  # advance cursor even if not for us
        if (fields.get("to") or "") == want_to:
            found = {
                "id": msg_id,
                "sender": fields.get("sender"),
                "to": fields.get("to"),
                "payload": fields.get("payload"),
                "ts": fields.get("ts"),
            }
            break

    return jsonify({"msg": found, "cursor": cursor})

@app.route("/crypto/relay")
def crypto_relay():
    if not session.get("netid"):
        return redirect(url_for("login"))

    room = (request.args.get("room") or uuid4().hex[:8]).strip()
    who  = (request.args.get("who") or "Alice").strip()
    if who not in ("Alice", "Bob"):
        who = "Alice"

    other = "Bob" if who == "Alice" else "Alice"
    base = request.host_url.rstrip("/")

    initial_code = f'''\
# Open two tabs:
#  /crypto/relay?room={room}&who=Alice
#  /crypto/relay?room={room}&who=Bob

from js import fetch, JSON
#from pyodide.ffi import to_js, run_sync
from pyodide.ffi import to_js
import time, urllib.parse, asyncio

ROOM = {room!r}
ME   = {who!r}
THEM = {"Bob" if who=="Alice" else "Alice"!r}

def _url(path, params=None):
    if not params:
        return path
    return path + "?" + urllib.parse.urlencode(params)

async def _get(path, params=None):
    resp = await fetch(_url(path, params))
    if not resp.ok:
        raise Exception(f"HTTP {{resp.status}}: " + await resp.text())
    return await resp.json()

async def _post(path, obj):
    resp = await fetch(path, method="POST",
                       headers=to_js({{"Content-Type":"application/json"}}),
                       body=JSON.stringify(to_js(obj)))
    if not resp.ok:
        raise Exception(f"HTTP {{resp.status}}: " + await resp.text())
    return await resp.json()

_cursor = "0-0"


async def send(payload, to=THEM):
    return await _post(f"/api/relay/{{ROOM}}/send",
           {{"sender": ME, "to": to, "payload": str(payload)}})


async def recv(timeout_s=0):
    global _cursor
    end = time.time() + float(timeout_s)
    while True:
        j = await _get(f"/api/relay/{{ROOM}}/recv", {{"after": _cursor, "to": ME}})
        _cursor = j.get("cursor", _cursor)
        if j.get("msg") is not None:
            return j["msg"]
        if timeout_s <= 0 or time.time() >= end:
            return None
        await asyncio.sleep(0.25)
#def send(payload, to=THEM):
#    return run_sync(_post(f"/api/relay/{{ROOM}}/send",
#                          {{"sender": ME, "to": to, "payload": str(payload)}}))

#def recv(timeout_s=0):
#    global _cursor
#    end = time.time() + float(timeout_s)
#    while True:
#        j = run_sync(_get(f"/api/relay/{{ROOM}}/recv", {{"after": _cursor, "to": ME}}))
#        _cursor = j.get("cursor", _cursor)
#        if j.get("msg") is not None:
#            return j["msg"]
#        if timeout_s <= 0 or time.time() >= end:
#            return None
#        time.sleep(0.25)

print("Ready:", ME, "room", ROOM)
# try:
# send("ciphertext: 12345")
# print(recv(10))
'''

    return render_template(
        "sandbox.html",
        body_class="sandbox",
        course="crypto",
        lesson="relay",
        prompt_md="",
        initial_code=initial_code,
        default_args="",
    )

@app.post("/api/course/<course>/<lesson>/check")
def api_course_check(course, lesson):
    if not session.get("netid"):
        return jsonify({"error":"not_logged_in"}), 401

    root = (BASE_DIR / "courses" / course / lesson).resolve()
    meta = json.loads((root / "lesson.json").read_text(encoding="utf-8"))

    data = request.get_json(force=True) or {}
    step_id = int(data.get("step_id"))
    code = data.get("code") or ""

    step = next((s for s in meta["steps"] if int(s["id"]) == step_id), None)
    if not step:
        return jsonify({"error":"bad_step"}), 400

    # build docker file map
    files = {"student.py": code}
    test_glob = step.get("test_glob")
    if test_glob:
        for p in sorted(glob.glob(str(root / test_glob))):
            files[Path(p).name] = Path(p).read_text(encoding="utf-8")
        res = run_pytest_in_docker(files, timeout_s=10)
        passed = (res["failed"] == 0)
    else:
        # info-only step: "checking" just marks complete
        res = {"passed": 1, "failed": 0, "output": "Marked complete."}
        passed = True

    st = TutorialState.query.filter_by(netid=session["netid"], course=course, lesson=lesson).first()
    progress = json.loads(st.progress_json or "{}")
    progress[str(step_id)] = passed 
    st.code = code
    st.progress_json = json.dumps(progress)
    st.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(res | {"progress": progress})


@app.post("/api/course/<course>/<lesson>/progress")
def api_course_progress(course, lesson):
    if not session.get("netid"):
        return jsonify({"error":"not_logged_in"}), 401

    data = request.get_json(force=True) or {}
    step_id = int(data.get("step_id"))
    done = bool(data.get("done"))

    st = TutorialState.query.filter_by(netid=session["netid"], course=course, lesson=lesson).first()
    if not st:
        return jsonify({"error":"no_state"}), 404

    progress = json.loads(st.progress_json or "{}")
    progress[str(step_id)] = done
    st.progress_json = json.dumps(progress)
    st.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"progress": progress})


@app.post("/api/course/<course>/<lesson>/run")
def api_course_run(course, lesson):
    if not session.get("netid"):
        return jsonify({"error":"not_logged_in"}), 401

    data = request.get_json(force=True) or {}
    code = data.get("code") or ""
    args = data.get("args") or ""

    # reuse your docker python runner (it already works)
    try:

        res = run_python_in_docker(code, timeout_s=3, args=shlex.split(args)[:20])

    except Exception as e:

        app.logger.exception("api_course_run failed")

        res = {

            "stdout": "",

            "stderr": f"Server error (run): {e}",

            "cmd_display": "$ python main.py",

            "timeout": False,

            "error": str(e),

        }

    # save code draft
    st = TutorialState.query.filter_by(netid=session["netid"], course=course, lesson=lesson).first()
    if st:
        st.code = code
        st.updated_at = datetime.now(timezone.utc)
        db.session.commit()

    return jsonify(res)

def list_lessons(course: str):
    course_dir = (BASE_DIR / "courses" / course).resolve()
    lessons = []
    if not course_dir.exists():
        return lessons

    for p in sorted(course_dir.iterdir()):
        if not (p.is_dir() and (p / "lesson.json").exists()):
            continue
        try:
            meta = json.loads((p / "lesson.json").read_text(encoding="utf-8"))
        except Exception:
            try:
                app.logger.exception("Bad lesson.json in %s", p)
            except Exception:
                pass
            continue

        lessons.append({
            "slug": p.name,
            "title": meta.get("title", p.name),
            "is_open": bool(meta.get("is_open", True)),
        })

    return lessons


def _pretty_title(slug: str) -> str:
    return slug.replace("_", " ").replace("-", " ").strip().title()

def _done_steps(progress_json):
    import json as _json
    try:
        d = _json.loads(progress_json or "{}")
        return sum(1 for v in d.values() if v)
    except Exception:
        return 0

def _steps_count_for_lesson(course: str, lesson: str) -> int:
    import json as _json
    from pathlib import Path as _Path
    root = (_Path(BASE_DIR) / "courses" / course / lesson).resolve()
    try:
        meta = _json.loads((root / "lesson.json").read_text(encoding="utf-8"))
        return len(meta.get("steps", []))
    except Exception:
        return 0

@app.template_filter("human_dt")
def human_dt(s):
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s)
        # Example: Jan 21, 2026 4:06 PM
        return dt.strftime("%b %d, %Y %-I:%M %p")
    except Exception:
        return str(s)

@app.get("/course")
@app.get("/course/")
def course_root():
    if not session.get("netid"):
        return redirect(url_for("index"))

    courses_dir = (BASE_DIR / "courses").resolve()
    if not courses_dir.exists():
        abort(404)

    netid = session["netid"]
    topics = []

    for p in sorted(courses_dir.iterdir()):
        if not p.is_dir():
            continue

        lessons = list_lessons(p.name)
        if not lessons:
            continue

        states = TutorialState.query.filter_by(netid=netid, course=p.name).all()
        by_lesson = {s.lesson: s for s in states}

        total_steps = 0
        done_steps = 0
        for l in lessons:
            total = _steps_count_for_lesson(p.name, l["slug"])
            total_steps += total
            st = by_lesson.get(l["slug"])
            done_steps += _done_steps(getattr(st, "progress_json", None)) if st else 0

        pct = int(round(100 * done_steps / total_steps)) if total_steps else 0
        topics.append({
            "slug": p.name,
            "title": _pretty_title(p.name),
            "lessons_count": len(lessons),
            "done_steps": done_steps,
            "total_steps": total_steps,
            "pct": pct,
        })

    if not topics:
        abort(404)

    return render_template("courses_index.html", topics=topics)


@app.get("/course/<course>")
def course_index(course):
    if not session.get("netid"):
        return redirect(url_for("index"))

    canonical = course.replace("-", "_")
    if canonical != course:
        return redirect(url_for("course_index", course=canonical), code=301)
    course = canonical

    lessons = list_lessons(course)
    if not lessons:
        abort(404)

    netid = session["netid"]
    states = TutorialState.query.filter_by(netid=netid, course=course).all()
    by_lesson = {s.lesson: s for s in states}

    course_total = 0
    course_done = 0

    for l in lessons:
        total = _steps_count_for_lesson(course, l["slug"])
        st = by_lesson.get(l["slug"])
        done = _done_steps(getattr(st, "progress_json", None)) if st else 0

        l["total_steps"] = total
        l["done_steps"] = min(done, total) if total else done
        l["pct"] = int(round(100 * l["done_steps"] / total)) if total else 0

        course_total += total
        course_done += l["done_steps"]

    course_pct = int(round(100 * course_done / course_total)) if course_total else 0
    topic_title = _pretty_title(course)

    return render_template(
        "course_index.html",
        course=course,
        topic_title=topic_title,
        lessons=lessons,
        course_total=course_total,
        course_done=course_done,
        course_pct=course_pct,
    )


@app.get("/hw")
def hw_index():
    if not session.get("netid"):
        return redirect(url_for("index"))

    netid = session["netid"]
    items = []

    submitted_count = 0
    total_count = len(HOMEWORKS)

    grade_sum = 0.0
    grade_n = 0

    for slug, hw in HOMEWORKS.items():
        latest = (HomeworkSubmission.query
                  .filter_by(slug=slug, netid=netid)
                  .order_by(HomeworkSubmission.created_at.desc())
                  .first())

        status = None
        if latest:
            # final score preference
            final_score = latest.score_final_after_reopen if getattr(latest, "score_final_after_reopen", None) is not None else latest.score_final

            passed, failed = _passed_failed_from_submission(latest)
            denom = passed + failed
            t_pct = (100.0 * passed / denom) if denom else 0.0
            ok = (latest.is_final == 1)


            if latest.is_final == 1:
                state = "submitted"
                submitted_count += 1
                if final_score is not None:
                    grade_sum += float(final_score)
                    grade_n += 1
            elif getattr(latest, "reopened_at", None):
                state = "reopened"  # needs resubmit
            else:
                state = "draft"

            status = {
                "state": state,
                "ok": ok,                 # used for “submitted vs not”
                "passed": passed,         # template expects these
                "failed": failed,
                "pct": t_pct,             # for progress bar per HW
                "submitted_at": latest.submitted_at or (latest.created_at.isoformat() if latest.created_at else None),
                "raw": latest.score_raw,
                "final": final_score,
                "late_days": latest.late_days,
                "penalty_frac": latest.penalty_frac,
                "reopen_penalty_frac": getattr(latest, "reopen_penalty_frac", 0.0),
            }
 

        items.append({
            "slug": slug,
            "title": hw["title"],
            "due_at": hw.get("due_at"),
            "status": status,
        })

    submitted_pct = (submitted_count / total_count * 100.0) if total_count else 0.0
    avg_score = (grade_sum / grade_n) if grade_n else None

    return render_template(
        "hw_index.html",
        items=items,
        submitted_count=submitted_count,
        total_count=total_count,
        submitted_pct=submitted_pct,
        avg_score=avg_score,
    )



@app.get("/hw/<slug>")
def hw_page(slug):
    if not session.get("netid"):
        return redirect(url_for("index"))

    hw = HOMEWORKS.get(slug)
    if not hw:
        abort(404)

    netid = session["netid"]

    latest_any = (HomeworkSubmission.query
        .filter_by(slug=slug, netid=netid)
        .order_by(HomeworkSubmission.created_at.desc())
        .first())

    latest_final = (HomeworkSubmission.query
        .filter_by(slug=slug, netid=netid, is_final=1)
        .order_by(HomeworkSubmission.created_at.desc())
        .first())

    root = (BASE_DIR / hw["root"]).resolve()
    starter_path = root / "starter.py"
    prompt_path  = root / "prompt.md"
    starter = starter_path.read_text(encoding="utf-8") if starter_path.exists() else ""
    prompt_md = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

    initial_code = (latest_any.code if latest_any else starter)

    # LOCK only if there is a final
    submitted_at = None
    if latest_final:
        submitted_at = latest_final.submitted_at or latest_final.created_at.isoformat()

    reopened_at = latest_any.reopened_at if (latest_any and latest_any.reopened_at) else None

    return render_template(
        "homework.html",
        hw=hw,
        slug=slug,
        initial_code=initial_code,
        submitted_at=submitted_at,
        reopened_at=reopened_at,      # optional: show banner
        prompt_md=prompt_md,
    )


@app.get("/admin/hw/<slug>/diff")
def admin_hw_diff(slug):
    if not (session.get("netid") and session.get("is_admin")):
        return "Forbidden", 403
    if slug not in HOMEWORKS:
        return "Unknown homework", 404

    netid = (request.args.get("netid") or "").strip()
    if not netid:
        return "Missing netid", 400

    # latest final (this is what student currently has "on the books")
    latest = (HomeworkSubmission.query
        .filter_by(slug=slug, netid=netid, is_final=1)
        .order_by(HomeworkSubmission.created_at.desc())
        .first())
    if not latest:
        return "No final submission found.", 404

    base = None
    base_code = None

    # if it came from a reopen, this points back to the “reopened” submission row
    if latest.reopened_from_id:
        base = HomeworkSubmission.query.get(int(latest.reopened_from_id))

    # baseline code: prefer saved diff base; fallback to base.code
    if base:
        base_code = base.diff_base_code or base.code

    if not base_code:
        # nothing to diff (either not reopened, or reopen baseline missing)
        return render_template(
            "admin_hw_diff.html",
            slug=slug,
            netid=netid,
            latest=latest,
            base=base,
            diff_html=None,
            note="No reopen baseline found for this latest submission (not reopened or diff_base_code missing)."
        )

    new_code = latest.code or ""

    udiff = list(difflib.unified_diff(
        base_code.splitlines(),
        new_code.splitlines(),
        fromfile=f"{slug}:{netid}:before",
        tofile=f"{slug}:{netid}:after",
        lineterm=""
    ))

    def diff_to_html(lines):
        out = []
        for line in lines:
            cls = "diff-ctx"
            if line.startswith(("---", "+++")):
                cls = "diff-hdr"
            elif line.startswith("@@"):
                cls = "diff-hunk"
            elif line.startswith("+") and not line.startswith("+++"):
                cls = "diff-add"
            elif line.startswith("-") and not line.startswith("---"):
                cls = "diff-del"
            out.append(f'<span class="{cls}">{escape(line)}</span>')
        return Markup("\n".join(out))

    diff_html = diff_to_html(udiff) if udiff else Markup("")

    return render_template(
        "admin_hw_diff.html",
        slug=slug,
        netid=netid,
        latest=latest,
        base=base,
        diff_html=diff_html,
        note=None
    )

@app.post("/api/hw/<slug>/run")
def hw_run(slug):
    if not session.get("netid"):
        return jsonify({"error": "not_logged_in"}), 401
    hw = HOMEWORKS.get(slug)
    if not hw:
        return jsonify({"error": "unknown_homework"}), 404

    data = request.get_json(force=True) or {}
    code = (data.get("code") or "")
    args_str = (data.get("args") or "")

    # basic safety limits
    if len(code) > 100_000 or len(args_str) > 500:
        return jsonify({"error": "too_large"}), 400

    args = shlex.split(args_str)[:20]   # cap number of args
    res = run_python_in_docker(code, timeout_s=3, args=args)
    return jsonify(res)

@app.post("/api/hw/<slug>/submit")
def hw_submit(slug):
    def load_test_files(root: Path, include_hidden: bool) -> dict:
        files = {}
        for p in sorted((root / "tests_public").glob("*.py")):
            files[p.name] = p.read_text(encoding="utf-8")
        if include_hidden and (root / "tests_hidden").exists():
            for p in sorted((root / "tests_hidden").glob("*.py")):
                files[p.name] = p.read_text(encoding="utf-8")
        return files
    
    def load_tests(root: Path, include_hidden: bool, qid: int | None):
        files = {}

        pub = root / "tests_public"
        if qid is None:
            paths = sorted(pub.glob("*.py"))
        else:
            paths = sorted(pub.glob(f"test_q{qid}_*.py")) or sorted(pub.glob(f"test_q{qid}.py"))
            if not paths:
                raise FileNotFoundError(f"no public test for qid={qid}")

        for p in paths:
            files[p.name] = p.read_text(encoding="utf-8")

        if include_hidden and (root / "tests_hidden").exists():
            for p in sorted((root / "tests_hidden").glob("*.py")):
                files[p.name] = p.read_text(encoding="utf-8")

        return files

    if not session.get("netid"):
        return jsonify({"error": "not_logged_in"}), 401
    if slug not in HOMEWORKS:
        return jsonify({"error": "unknown_homework"}), 404
    hw = HOMEWORKS[slug]


    data = request.get_json(force=True) or {}
    code = (data.get("code") or "")
    action = (data.get("action") or "check").lower()
    if action not in ("check", "submit"):
        action = "check"

    netid = session["netid"]
    # defaults so "check" doesn't crash
    reopen_penalty_frac = 0.0
    score_final_after_reopen = None

    # enforce one submit
    if action == "submit":
        existing = (HomeworkSubmission.query
            .filter_by(slug=slug, netid=netid, is_final=1)
            .order_by(HomeworkSubmission.created_at.desc())
            .first())

        if existing:
            return jsonify({
                "error": "already_submitted",
                "submitted_at": existing.created_at.isoformat(),
            }), 409

    #hw = HOMEWORKS[slug]
    #root = Path(HOMEWORKS[slug]["root"])
    #include_hidden = (action == "submit")
    #tests = load_test_files(root, include_hidden)
    #files = {"student.py": code, **tests}
    #result = run_pytest_in_docker(files, timeout_s=10)

    qid = data.get("qid")
    qid = int(qid) if (action == "check" and qid is not None) else None

    root = (BASE_DIR / HOMEWORKS[slug]["root"]).resolve()
    include_hidden = (action == "submit")

    try:
        tests = load_tests(root, include_hidden, qid)
    except FileNotFoundError as e:
        return jsonify({"error": "bad_qid", "detail": str(e)}), 400

    files = {"student.py": code, **tests}
    result = run_pytest_in_docker(files, timeout_s=10)
    result["cmd_display"] = "$ pytest -q"


    #submitted_at = None
    #submission_id = None

    #if action == "submit":
    #    sub = HomeworkSubmission(
    #        slug=slug,
    #        netid=netid,
    #        section=session.get("section"),
    #        code=code,
    #        result_json=json.dumps(result),
    #    )
    #    db.session.add(sub)
    #    db.session.commit()
    #    submitted_at = sub.created_at.isoformat()
    #    submission_id = sub.id

    #return jsonify({
    #    "title": hw["title"],
    #    "passed": result["passed"],
    #    "failed": result["failed"],
    #    "output": result["output"],
    #    "submission_id": submission_id,
    #    "submitted_at": submitted_at,
    #})
    submitted_at = None
    submission_id = None

    submitted_dt = datetime.now(TZ)
    due_dt = _parse_due_at(hw)  # hw = HOMEWORKS[slug]
    late_seconds, late_days = _late_info(due_dt, submitted_dt)

    score_raw = _score_from_pytest_result(result)
    penalty_frac = _penalty_frac_for_late_days(late_days)  # 0.05/day
    score_final = None
    if score_raw is not None:
        score_final = max(0.0, score_raw * (1.0 - penalty_frac))

    if action == "submit":
        reopen_base = (HomeworkSubmission.query
            .filter_by(slug=slug, netid=netid)
            .filter(HomeworkSubmission.reopened_at.isnot(None))
            .order_by(HomeworkSubmission.created_at.desc())
            .first())

        reopen_penalty_frac = float(reopen_base.reopen_penalty_frac or 0.0) if reopen_base else 0.0

        score_final_after_reopen = None
        if score_final is not None:
            score_final_after_reopen = max(0.0, score_final * (1.0 - reopen_penalty_frac))
        sub = HomeworkSubmission(
            slug=slug,
            netid=netid,
            section=session.get("section"),
            code=code,
            result_json=json.dumps(result),

            is_final=1,
            due_at=(due_dt.isoformat() if due_dt else None),
            submitted_at=submitted_dt.isoformat(),
            late_seconds=late_seconds,
            late_days=late_days,
            score_raw=score_raw,
            penalty_frac=penalty_frac,
            score_final=score_final,

            # reopen linkage (optional if no reopen happened)
            reopened_from_id=(reopen_base.id if reopen_base else None),
            score_final_after_reopen=score_final_after_reopen,
        )
        db.session.add(sub)
        db.session.commit()
        submitted_at = sub.submitted_at
        submission_id = sub.id

    return jsonify({
        "title": hw["title"],
        "passed": result["passed"],
        "failed": result["failed"],
        "output": result["output"],
        "submission_id": submission_id,
        "submitted_at": submitted_at,

        "due_at": (due_dt.isoformat() if due_dt else None),
        "late_days": late_days,
        "penalty_frac": penalty_frac,
        "score_raw": score_raw,
        "score_final": score_final,

        "reopen_penalty_frac": reopen_penalty_frac,
        "score_final_after_reopen": score_final_after_reopen,
        "score_effective": (score_final_after_reopen if score_final_after_reopen is not None else score_final),

    })

@app.post("/api/admin/hw/<slug>/rerun")
def api_admin_hw_rerun(slug):
    if not (session.get("netid") and session.get("is_admin")):
        return jsonify({"error": "not_admin"}), 403
    if slug not in HOMEWORKS:
        return jsonify({"error": "unknown_homework"}), 404

    data = request.get_json(force=True) or {}
    netid = (data.get("netid") or "").strip().lower()
    include_hidden = bool(data.get("include_hidden", False))  # admin toggle
    use_final = bool(data.get("use_final", True))             # default: latest final

    if not netid:
        return jsonify({"error": "missing_netid"}), 400

    q = HomeworkSubmission.query.filter_by(slug=slug, netid=netid)
    if use_final:
        q = q.filter_by(is_final=1)
    sub = q.order_by(HomeworkSubmission.created_at.desc()).first()
    if not sub:
        return jsonify({"error": "no_submission"}), 404

    root = (BASE_DIR / HOMEWORKS[slug]["root"]).resolve()

    # Reuse the same loader logic as hw_submit (inline a small copy here)
    files = {"student.py": sub.code or ""}
    for p in sorted((root / "tests_public").glob("*.py")):
        files[p.name] = p.read_text(encoding="utf-8")
    if include_hidden and (root / "tests_hidden").exists():
        for p in sorted((root / "tests_hidden").glob("*.py")):
            files[p.name] = p.read_text(encoding="utf-8")

    result = run_pytest_in_docker(files, timeout_s=15)
    result["cmd_display"] = "$ pytest -q" + (" (with hidden)" if include_hidden else "")

    return jsonify({
        "slug": slug,
        "netid": netid,
        "submission_id": sub.id,
        "is_final": int(sub.is_final or 0),
        "ran_hidden": include_hidden,
        "passed": result.get("passed", 0),
        "failed": result.get("failed", 0),
        "output": result.get("output", ""),
        "result": result,
    })

@app.post("/api/admin/hw/<slug>/regrade")
def api_admin_hw_regrade(slug):
    if not (session.get("netid") and session.get("is_admin")):
        return jsonify({"error": "not_admin"}), 403
    if slug not in HOMEWORKS:
        return jsonify({"error": "unknown_homework"}), 404

    data = request.get_json(force=True) or {}
    include_hidden = bool(data.get("include_hidden", True))

    # fetch all finals for this slug
    subs = (HomeworkSubmission.query
        .filter(HomeworkSubmission.slug == slug)
        .filter(HomeworkSubmission.submitted_at.isnot(None))  # key change
        .order_by(HomeworkSubmission.netid.asc(), HomeworkSubmission.created_at.desc())
        .all())


    # keep latest final per netid
    latest = {}
    for s in subs:
        if s.netid not in latest:
            latest[s.netid] = s

    hw = HOMEWORKS[slug]
    root = (BASE_DIR / hw["root"]).resolve()

    changed = 0
    details = []

    for netid, sub in latest.items():
        files = {"student.py": sub.code or ""}
        for p in sorted((root / "tests_public").glob("*.py")):
            files[p.name] = p.read_text(encoding="utf-8")
        if include_hidden and (root / "tests_hidden").exists():
            for p in sorted((root / "tests_hidden").glob("*.py")):
                files[p.name] = p.read_text(encoding="utf-8")

        result = run_pytest_in_docker(files, timeout_s=15)

        score_raw = _score_from_pytest_result(result)
        # keep the originally stored late penalty fields
        penalty_frac = float(sub.penalty_frac or 0.0)
        score_final = (max(0.0, score_raw * (1.0 - penalty_frac)) if score_raw is not None else None)

        reopen_penalty = float(sub.reopen_penalty_frac or 0.0)
        score_final_after_reopen = (max(0.0, score_final * (1.0 - reopen_penalty)) if score_final is not None else None)

        sub.result_json = json.dumps(result)
        sub.score_raw = score_raw
        sub.score_final = score_final
        sub.score_final_after_reopen = score_final_after_reopen

        changed += 1
        details.append({
            "netid": netid,
            "passed": result.get("passed", 0),
            "failed": result.get("failed", 0),
            "score_effective": (score_final_after_reopen if score_final_after_reopen is not None else score_final),
        })

    db.session.commit()
    return jsonify({"ok": True, "slug": slug, "updated": changed, "details": details})


@app.post("/api/admin/hw/<slug>/reopen")
def admin_hw_reopen(slug):
    if not session.get("netid"):
        return jsonify({"error": "not_logged_in"}), 401

    # adjust to your admin logic
    if not (session.get("is_admin") or session.get("netid") == os.environ.get("ADMIN_NETID")):
        return jsonify({"error": "not_admin"}), 403

    if slug not in HOMEWORKS:
        return jsonify({"error": "unknown_homework"}), 404

    data = request.get_json(force=True) or {}
    netid = (data.get("netid") or "").strip()
    penalty = data.get("penalty", 0.10)
    try:
        penalty = float(penalty)
    except Exception:
        return jsonify({"error": "bad_penalty"}), 400
    penalty = max(0.0, min(1.0, penalty))

    if not netid:
        return jsonify({"error": "missing_netid"}), 400

    final = (HomeworkSubmission.query
        .filter_by(slug=slug, netid=netid, is_final=1)
        .order_by(HomeworkSubmission.created_at.desc())
        .first())

    if not final:
        return jsonify({"error": "no_final_to_reopen"}), 404

    now_iso = datetime.now(TZ).isoformat()

    # De-finalize + mark reopen event on that row
    final.is_final = 0
    final.reopened_at = now_iso
    final.reopen_penalty_frac = penalty
    final.diff_base_code = final.code  # baseline snapshot at reopen time

    db.session.commit()

    return jsonify({
        "ok": True,
        "slug": slug,
        "netid": netid,
        "reopened_at": now_iso,
        "reopen_penalty_frac": penalty,
        "reopened_from_id": final.id,
    })

@app.get("/admin/hw/<slug>/submission")
def admin_hw_submission(slug):
    if not session.get("is_admin"):
        abort(403)

    netid = request.args.get("netid", "").strip()
    if not netid:
        abort(400)

    sub = (HomeworkSubmission.query
           .filter_by(slug=slug, netid=netid)
           .order_by(HomeworkSubmission.created_at.desc())
           .first())

    result_pretty = "{}"
    output_text = ""
    if sub:
        try:
            result_pretty = json.dumps(json.loads(sub.result_json or "{}"), indent=2, sort_keys=True)
        except Exception:
            result_pretty = sub.result_json or "{}"
        output_text = sub.output_text or ""

    return render_template(
        "admin_hw_submission.html",
        slug=slug,
        netid=netid,
        sub=sub,
        result_pretty=result_pretty,
        output_text=output_text,
    )



@app.route("/notebooks")
def notebooks():
    if session.get("is_admin"):
        return render_template("notebooks.html", section=None, is_admin=True)

    netid = session.get("netid")
    if not netid:
        return redirect(url_for("index"))  # open modal on home

    roster = load_roster()  # missing before
    #row = roster.loc[roster["netid_lc"] == netid.lower()]
    #row = roster.loc[roster["NetID"].str.lower() == netid.lower()]
    _, row = roster_row_for_netid(netid)
    if row.empty:
        return "NetID not found in roster", 403
    section = section_from_row(row)
    #section = int(row.iloc[0]["Section"])
    return render_template("notebooks.html", section=section, is_admin=False)

@app.get("/chat")
def chat_redirect():
    # Prefer explicit query (?section=) if provided
    q = request.args.get("section")
    if q and q.isdigit():
        return redirect(url_for("chat", section=int(q)))

    section = session.get("section")
    # Admins: default to section 1 if not set yet
    if session.get("is_admin") and not section:
        return redirect(url_for("chat", section=1))

    if not section:
        return redirect(url_for("index"))

    return redirect(url_for("chat", section=section))

@app.route("/api/chat/<int:section>/send", methods=["POST"])
def api_chat_send(section):
    if not session.get("netid"):
        return jsonify(success=False, error="Not logged in"), 403

    # Enforce student's section unless admin
    if not session.get("is_admin") and session.get("section") != section:
        return jsonify(success=False, error="Unauthorized section"), 403

    data = request.get_json()
    msg_text = (data.get("msg") or "").strip()
    if not msg_text:
        return jsonify(success=False, error="Empty message"), 400

    netid = session["netid"]
    display_name = get_display_name(netid)
    timestamp = datetime.utcnow().isoformat()

    msg_obj = {
        "netid": netid,
        "msg": msg_text,
        "timestamp": timestamp,
        "reply": None,
        "edited": False,
        "admin_flags": {},
        "support_count": 0,
        "support_votes": [],
        "display_name": display_name,
    }

    # Save to Redis
    r.rpush(f"chat:{section}", json.dumps(msg_obj))

    return jsonify(success=True, **msg_obj)

@app.route("/api/chat/<int:section>/messages")
def api_chat_messages(section):
    if not session.get("netid"):
        return jsonify(success=False, error="Not logged in"), 403

    after = int(request.args.get("after", 0))
    raw = r.lrange(f"chat:{section}", after, -1)
    messages = []

    for item in raw:
        try:
            msg_obj = json.loads(item)
            if isinstance(msg_obj, dict):
                msg_obj["timestamp"] = format_timestamp_for_display(msg_obj["timestamp"])
                msg_obj["display_name"] = get_display_name(msg_obj["netid"])
                messages.append(msg_obj)
        except Exception:
            continue

    return jsonify(success=True, messages=messages)

@app.route("/chat/<int:section>")
def chat(section):
    # Require login
    if not session.get("netid"):
        return redirect(url_for("index"))

    # Students can only view their own section; admins can view any
    if not session.get("is_admin") and session.get("section") != section:
        return redirect(url_for("chat", section=session["section"]))

    raw = r.lrange(f"chat:{section}", 0, -1)
    messages = []

    for item in raw:
        try:
            msg_obj = json.loads(item)
            if isinstance(msg_obj, dict):
                msg_obj.setdefault("netid", "unknown")
                msg_obj.setdefault("msg", "")
                msg_obj.setdefault("timestamp", "[unknown]")
                msg_obj.setdefault("reply", None)
                msg_obj.setdefault("edited", False)
                msg_obj.setdefault("message_id", f"{section}:{msg_obj.get('timestamp','[unknown]')}:{hash(msg_obj.get('msg','')) % 1000000}")
                msg_obj.setdefault("admin_flags", {})
                msg_obj.setdefault("support_count", 0)
                msg_obj.setdefault("support_votes", [])
                msg_obj["timestamp"] = format_timestamp_for_display(msg_obj["timestamp"])
                msg_obj["display_name"] = get_display_name(msg_obj["netid"])
                messages.append(msg_obj)
            else:
                messages.append({
                    "netid": "unknown",
                    "msg": str(item),
                    "timestamp": "[old]",
                    "reply": None,
                    "edited": False,
                    "message_id": f"{section}:[old]:{hash(str(item)) % 1000000}",
                    "admin_flags": {},
                    "support_count": 0,
                    "support_votes": [],
                    "display_name": "unknown"
                })
        except json.JSONDecodeError:
            messages.append({
                "netid": "unknown",
                "msg": item,
                "timestamp": "[old]",
                "reply": None,
                "edited": False,
                "message_id": f"{section}:[old]:{hash(item) % 1000000}",
                "admin_flags": {},
                "support_count": []
            })

    netid = session["netid"]
    display_name = get_display_name(netid).split('(')[0]

    return render_template(
        "chat.html",
        section=section,
        messages=messages,
        display_name=display_name,
        netid=netid,
        is_admin=session.get("is_admin", False)
    )


@app.post("/set_section")
def set_section():
    if not session.get("is_admin"):
        return jsonify(success=False, error="Unauthorized"), 403

    new_section = str((request.json or {}).get("section", "")).strip()

    valid_sections = set(SECTION_REPOS.keys())  # e.g. {"1","2","5","6","42"}
    if new_section not in valid_sections:
        return jsonify(success=False, error=f"Invalid section: {new_section}"), 400

    session["section"] = int(new_section)
    session["admin_view_section"] = int(new_section)
    return jsonify(success=True, section=session["section"])



@socketio.on("join_section")
def on_join_section():
    sec = session.get("section")
    room = f"section:{sec}" if sec is not None else "section:none"
    join_room(room)
    
@socketio.on("poll")
def handle_poll(data):
    section = data.get("section")
    question = data.get("question")
    options = data.get("options")
    netid = data.get("netid", "unknown")

    if not section or not question or not options or not isinstance(options, list):
        return

    timestamp = get_est_timestamp()

    poll_id = f"poll:{section}:{len(options)}:{hash(question) % 100000}"
    r.hset(poll_id, mapping={"question": question, "options": "|".join(options)})
    r.sadd(f"{poll_id}:voters", "")  # just to initialize

    msg_obj = {
        "type": "poll",
        "netid": netid,
        "question": question,
        "options": options,
        "timestamp": timestamp,
        "poll_id": poll_id
    }

    r.rpush(f"chat:{section}", json.dumps(msg_obj))
    socketio.emit("message", msg_obj, to=section)

@socketio.on("vote")
def handle_vote(data):
    poll_id = data.get("poll_id")
    option = data.get("option")
    netid = data.get("netid")

    if not poll_id or not option or not netid:
        return

    # Only allow one vote per person per poll
    if r.sismember(f"{poll_id}:voters", netid):
        return

    r.sadd(f"{poll_id}:voters", netid)
    r.hincrby(f"{poll_id}:votes", option, 1)

    # Emit updated results
    results = r.hgetall(f"{poll_id}:votes")
    socketio.emit("poll_results", {
        "poll_id": poll_id,
        "results": results
    })


@socketio.on("join")
def on_join(data):
    # Determine section to join
    desired = str(data.get("section") or "")
    netid = flask_session.get("netid")

    if not netid:
        return  # reject anonymous

    # Students: force their own section. Admins: allow desired override.
    roster = load_roster()
    #row = roster.loc[roster["NetID"].str.lower() == netid.lower()]
    #row = roster.loc[roster["netid_lc"] == netid.lower()]
    #user_section = str(row.iloc[0]["Section"]) if not row.empty else None
    _, row = roster_row_for_netid(netid)
    user_section = str(section_from_row(row)) if not row.empty else None


    if flask_session.get("is_admin"):
        section = desired or user_section or ""
    else:
        section = user_section

    if not section:
        return

    join_room(section)

    # Track presence
    r.sadd(f"chat:participants:{section}", netid)
    socket_to_user[request.sid] = {"netid": netid, "section": section}

    participants = [get_display_name(n) for n in r.smembers(f"chat:participants:{section}")]
    socketio.emit("participants", {"section": section, "participants": participants}, to=section)
    emit("participants", {"section": section, "participants": participants})


@socketio.on("support")
def support_alias(data):
    # Expect: {section, message_id}
    data = data or {}
    data["netid"] = flask_session.get("netid")
    handle_support_message(data)  # reuse existing

@socketio.on("admin_action")
def admin_action_alias(data):
    # Expect: {section, action: 'delete'|'check', message_id}
    if not flask_session.get("is_admin"):
        return
    action = data.get("action")
    if action == "delete":
        # Reuse existing handler; bypass password when session admin
        section = data.get("section")
        message_id = data.get("message_id")
        # Inline delete similar to handle_admin_delete but using session
        messages = r.lrange(f"chat:{section}", 0, -1)
        for i, msg_str in enumerate(messages):
            try:
                msg_obj = json.loads(msg_str)
                if msg_obj.get("message_id") == message_id:
                    r.lrem(f"chat:{section}", 1, msg_str)
                    socketio.emit("message_deleted", {"message_id": message_id}, to=str(section))
                    return
            except:
                continue
    elif action == "check":
        section = data.get("section")
        message_id = data.get("message_id")
        messages = r.lrange(f"chat:{section}", 0, -1)
        for i, msg_str in enumerate(messages):
            try:
                msg_obj = json.loads(msg_str)
                if msg_obj.get("message_id") == message_id:
                    msg_obj.setdefault("admin_flags", {})["correct"] = True
                    msg_obj["admin_flags"].pop("incorrect", None)
                    r.lset(f"chat:{section}", i, json.dumps(msg_obj))
                    socketio.emit("message_flagged", {
                        "message_id": message_id,
                        "flag_type": "correct",
                        "admin_flags": msg_obj["admin_flags"]
                    }, to=str(section))
                    return
            except:
                continue


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    user = socket_to_user.pop(sid, None)
    if user:
        netid = user["netid"]
        section = user["section"]
        print(f"Disconnect: removing {netid} from section {section}")
        r.srem(f"chat:participants:{section}", netid)
        #participants = list(r.smembers(f"chat:participants:{section}"))
        participants = [get_display_name(n) for n in r.smembers(f"chat:participants:{section}")]

        socketio.emit("participants", {"section": section, "participants": participants}, to=section)
    else:
        print(f"Disconnect: sid {sid} not found in socket_to_user")

@socketio.on("kick_user")
def handle_kick_user(data):
    section = data.get("section")
    netid = data.get("netid")
    admin_netid = data.get("admin_netid")
    admin_password = data.get("admin_password")
    # Only allow admin to kick
    if not check_admin_auth(admin_netid, admin_password):
        print(f"Kick denied: invalid admin credentials for {admin_netid}")
        return
    print(f"Admin {admin_netid} is attempting to kick {netid} from section {section}")
    print(f"Current socket_to_user mapping: {socket_to_user}")
    found = False
    for sid, info in list(socket_to_user.items()):
        print(f"Checking sid {sid}: {info}")
        if info["netid"] == netid and str(info["section"]) == str(section):
            print(f"Kicking user {netid} (sid {sid}) from section {section}")
            # Remove from participants set
            r.srem(f"chat:participants:{section}", netid)
            participants = list(r.smembers(f"chat:participants:{section}"))
            participants = [get_display_name(n) for n in participants]
            socketio.emit("participants", {"section": section, "participants": participants}, to=section)
            # Notify and disconnect the user
            socketio.emit("kicked", {"reason": "You have been removed from the chat by an administrator."}, to=sid)
            disconnect(sid)
            socket_to_user.pop(sid, None)
            found = True
            break
    if not found:
        print(f"Kick: user {netid} not found in socket_to_user, but will remove from Redis anyway.")
        r.srem(f"chat:participants:{section}", netid)
        participants = list(r.smembers(f"chat:participants:{section}"))
        participants = [get_display_name(n) for n in participants]
        socketio.emit("participants", {"section": section, "participants": participants}, to=section)
    # Emit updated participants list again to ensure frontend updates
    participants = list(r.smembers(f"chat:participants:{section}"))
    participants = [get_display_name(n) for n in participants]
    socketio.emit("participants", {"section": section, "participants": participants}, to=section)

@socketio.on("get_participants")
def handle_get_participants(data):
    section = data.get("section")
    if not section:
        return
    participants = list(r.smembers(f"chat:participants:{section}"))
    participants = [get_display_name(n) for n in participants]
    emit("participants", {"section": section, "participants": participants})

@socketio.on("get_poll_results")
def handle_get_poll_results(data):
    poll_id = data.get("poll_id")
    if not poll_id:
        return
    
    # Fetch current results from Redis
    results = r.hgetall(f"{poll_id}:votes")
    if results:
        emit("poll_results", {
            "poll_id": poll_id,
            "results": results
        })

# Handle sending message to correct section
@socketio.on("message")
def handle_message(data):
    section = data.get("section")
    if not session.get("netid"):
        return  # reject if not logged in

    # Enforce student section unless admin
    if not session.get("is_admin") and session.get("section") != section:
        return

    raw_msg = (data.get("msg") or "").strip()
    if not raw_msg:
        return

    netid = session["netid"]
    display_name = get_display_name(netid)
    reply = None
    if "|||reply|||" in raw_msg:
        raw_msg, reply = raw_msg.split("|||reply|||", 1)

    timestamp = get_est_timestamp()
    today = datetime.now(est).strftime("%Y-%m-%d")

    # Track participation
    r.sadd(f"participation:{today}:{section}", netid)

    msg_obj = {
        "netid": netid,
        "display_name": display_name,
        "msg": raw_msg,
        "timestamp": timestamp,
        "reply": reply,
        "edited": False,
        "message_id": f"{section}:{timestamp}:{hash(raw_msg) % 1000000}",
        "admin_flags": {},
        "support_count": 0,
    }

    r.rpush(f"chat:{section}", json.dumps(msg_obj))
    socketio.emit("message", msg_obj, to=section)

@socketio.on("admin_delete_message")
def handle_admin_delete(data):
    section = data.get("section")
    message_id = data.get("message_id")
    netid = data.get("netid")
    password = data.get("password")
    
    if not check_admin_auth(netid, password):
        emit("admin_error", {"message": "Invalid admin credentials"})
        return
    
    # Find and remove the message from Redis
    messages = r.lrange(f"chat:{section}", 0, -1)
    for i, msg_str in enumerate(messages):
        try:
            msg_obj = json.loads(msg_str)
            if msg_obj.get("message_id") == message_id:
                r.lrem(f"chat:{section}", 1, msg_str)
                socketio.emit("message_deleted", {"message_id": message_id}, to=section)
                return
        except:
            continue
    
    emit("admin_error", {"message": "Message not found"})

@socketio.on("admin_flag_message")
def handle_admin_flag(data):
    section = data.get("section")
    message_id = data.get("message_id")
    flag_type = data.get("flag_type")  # "correct" or "incorrect"
    netid = data.get("netid")
    password = data.get("password")
    
    if not check_admin_auth(netid, password):
        emit("admin_error", {"message": "Invalid admin credentials"})
        return
    
    if flag_type not in ["correct", "incorrect"]:
        emit("admin_error", {"message": "Invalid flag type"})
        return
    
    # Find and update the message in Redis
    messages = r.lrange(f"chat:{section}", 0, -1)
    for i, msg_str in enumerate(messages):
        try:
            msg_obj = json.loads(msg_str)
            if msg_obj.get("message_id") == message_id:
                msg_obj["admin_flags"][flag_type] = True
                # Remove opposite flag if it exists
                opposite_flag = "incorrect" if flag_type == "correct" else "correct"
                if opposite_flag in msg_obj["admin_flags"]:
                    del msg_obj["admin_flags"][opposite_flag]
                
                # Update in Redis
                r.lset(f"chat:{section}", i, json.dumps(msg_obj))
                socketio.emit("message_flagged", {
                    "message_id": message_id,
                    "flag_type": flag_type,
                    "admin_flags": msg_obj["admin_flags"]
                }, to=section)
                return
        except:
            continue
    
    emit("admin_error", {"message": "Message not found"})

@socketio.on("support_message")
def handle_support_message(data):
    section = data.get("section")
    message_id = data.get("message_id")
    netid = data.get("netid")
    
    if not netid:
        emit("support_error", {"message": "NetID required"})
        return
    
    # Find and update the message in Redis
    messages = r.lrange(f"chat:{section}", 0, -1)
    for i, msg_str in enumerate(messages):
        try:
            msg_obj = json.loads(msg_str)
            
            # Handle old messages that might not have message_id
            if not msg_obj.get("message_id"):
                # Generate message_id for old messages
                msg_content = msg_obj.get("msg", "")
                msg_timestamp = msg_obj.get("timestamp", "[old]")
                generated_id = f"{section}:{msg_timestamp}:{hash(msg_content) % 1000000}"
                msg_obj["message_id"] = generated_id
            
            if msg_obj.get("message_id") == message_id:
                # Initialize support tracking if not exists
                if "support_votes" not in msg_obj:
                    msg_obj["support_votes"] = []
                
                # Convert to set for easier manipulation
                support_votes = set(msg_obj.get("support_votes", []))
                
                if netid in support_votes:
                    # Remove support
                    support_votes.remove(netid)
                    msg_obj["support_count"] = len(support_votes)
                else:
                    # Add support
                    support_votes.add(netid)
                    msg_obj["support_count"] = len(support_votes)
                
                # Convert back to list for storage
                msg_obj["support_votes"] = list(support_votes)
                
                # Update in Redis
                r.lset(f"chat:{section}", i, json.dumps(msg_obj))
                socketio.emit("message_supported", {
                    "message_id": message_id,
                    "support_count": msg_obj["support_count"],
                    "supported": netid in support_votes
                }, to=section)
                return
        except Exception as e:
            print(f"Error processing support for message {i}: {e}")
            continue
    
    emit("support_error", {"message": "Message not found"})

def check_admin_access():
    if not session.get("is_admin"):
        abort(403)
#@app.before_request

# ---- participation counting rules ----
LECTURE_RESERVED_SLUGS = {
    "browse", "list", "create", "admin", "settings",
    "test", "linetest",
}

# (optional) if you want to count only “active” api calls, keep this.
LECTURE_COUNTED_API_ACTIONS = {"touch", "submit", "save", "run", "event", "heartbeat"}

def _lecture_slug_counts(slug: str | None) -> bool:
    if not slug:
        return False
    slug = slug.strip().lower()
    if slug in LECTURE_RESERVED_SLUGS:
        return False
    if slug.startswith("admin"):
        return False
    return True

def _counts_toward_participation(source: str) -> bool:
    if not source:
        return False
    if source == "lecture":
        return True  # legacy default, if you still use it anywhere
    if source.startswith("lecture:"):
        slug = source.split(":", 1)[1]
        return _lecture_slug_counts(slug)
    return False

def _auto_mark_lecture_participation():
    netid = session.get("netid")
    section = session.get("section")
    if not netid or not section:
        return

    path = request.path or ""
    parts = [p for p in path.split("/") if p]

    # /lecture/<slug>
    if len(parts) >= 2 and parts[0] == "lecture":
        slug = parts[1]
        if not _lecture_slug_counts(slug):
            return
        mark_participation(netid, str(section), source=f"lecture:{slug}")
        return

    # /api/lecture/<slug>/...
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "lecture":
        slug = parts[2]
        if not _lecture_slug_counts(slug):
            return

        action = parts[3] if len(parts) >= 4 else ""
        # If you want to count ANY api call tied to a real slug, delete this if-block.
        if action and action not in LECTURE_COUNTED_API_ACTIONS:
            return

        mark_participation(netid, str(section), source=f"lecture:{slug}")
        return

def _today_est():
    return datetime.now(est).strftime("%Y-%m-%d")

@app.route("/my_participation")
def my_participation():
    if not session.get("netid"):
        return redirect(url_for("login"))  # adjust if needed

    netid = session["netid"]
    section = str(session.get("section") or "")

    # show last 30 days
    rows = []
    start = datetime.now(est).date()
    for i in range(0, 30):
        d = (start - timedelta(days=i)).strftime("%Y-%m-%d")
        did = bool(section and r.sismember(f"participation:{d}:{section}", netid))
        rows.append({"day": d, "section": section, "did": did})

    return render_template("participation_me.html", rows=rows, netid=netid, section=section)

# ---------------------------
# Participation (chat + lecture)
# ---------------------------

def participation_day():
    # your app already defines `est` (America/New_York)
    return datetime.now(est).strftime("%Y-%m-%d")

def mark_participation(netid: str, section: str, source: str = "lecture", day: str | None = None):
    if not netid:
        return
    if not section:
        section = "unknown"
    day = day or participation_day()

    # only “count” certain sources
    if _counts_toward_participation(source):
        r.sadd(f"participation:{day}:{section}", netid)

    # keep per-student log (ok to keep everything)
    r.sadd(f"participation_by_student:{netid}", f"{day}:{section}:{source}")

    try:
        r.expire(f"participation:{day}:{section}", 60 * 60 * 24 * 200)
        r.expire(f"participation_by_student:{netid}", 60 * 60 * 24 * 200)
    except Exception:
        pass

@app.post("/api/participation/ping")
def participation_ping():
    netid = session.get("netid")
    if not netid:
        return jsonify({"ok": False, "error": "not logged in"}), 401

    section = session.get("section") or request.cookies.get("section") or "unknown"
    j = request.get_json(silent=True) or {}
    source = j.get("source") or "lecture"

    mark_participation(netid, section, source=source)
    return jsonify({"ok": True})


@app.get("/participation")
def participation_home():
    admin_netid = (app.config.get("ADMIN_NETID") or "").strip().lower()

    # admin -> existing dashboard
    if session.get("is_admin") or ((session.get("netid") or "").lower() == admin_netid and admin_netid):
        return redirect(url_for("participation_dashboard"))

    netid = session.get("netid")
    if not netid:
        return redirect(url_for("login"))

    raw = list(r.smembers(f"participation_by_student:{netid}") or [])
    entries = []
    for x in raw:
        if isinstance(x, (bytes, bytearray)):
            x = x.decode("utf-8", "replace")
        parts = x.split(":")
        if len(parts) >= 3:
            day, section, source = parts[0], parts[1], ":".join(parts[2:])
        elif len(parts) == 2:
            day, section, source = parts[0], parts[1], ""
        else:
            continue
        entries.append({"day": day, "section": section, "source": source})

    entries.sort(key=lambda e: e["day"], reverse=True)
    today = participation_day()
    did_today = any(e["day"] == today for e in entries)

    return render_template("participation_student.html", netid=netid, entries=entries, today=today, did_today=did_today)


@app.route("/participation_dashboard")
def participation_dashboard():
    check_admin_access()

    keys = r.keys("participation:*:*")
    entries = []
    for key in keys:
        try:
            _, date, section = key.split(":")
            entries.append((date, int(section)))
        except ValueError:
            continue

    entries = sorted(set(entries))
    return render_template("participation_dashboard.html", entries=entries)


# e.g. https://foundations.hobbsresearch.com/participation/2025-07-04/1
@app.route("/participation/<day>/<int:section>")
def view_participation(day, section):
    ids = r.smembers(f"participation:{day}:{section}")
    return "<h2>Participation on {} — Section {}</h2><pre>{}</pre>".format(
        day, section, "\n".join(sorted(ids))
    )

@app.route("/participation_csv/<day>/<int:section>")
def export_participation_csv(day, section):
    ids = r.smembers(f"participation:{day}:{section}")
    csv_data = "\n".join(sorted(ids))
    return Response(csv_data, mimetype='text/csv',
        headers={"Content-Disposition": f"attachment;filename=participation-{day}-section{section}.csv"})

@app.route("/participation_csv_all")
def export_all_participation():
    keys = r.keys("participation:*:*")
    seen = set()
    rows = ["date,section,netid"]

    for key in keys:
        try:
            _, date, section = key.split(":")
            section = int(section)
            ids = r.smembers(key)
            for netid in ids:
                entry = (date, section, netid)
                if entry not in seen:
                    seen.add(entry)
                    rows.append(f"{date},{section},{netid}")
        except ValueError:
            continue

    csv_data = "\n".join(rows)
    return Response(csv_data, mimetype='text/csv',
        headers={"Content-Disposition": "attachment;filename=participation-all.csv"})

@app.route("/participation_search")
def search_netid():
    query = request.args.get("netid", "").strip().lower()
    if not query:
        # Render a search form with the nav bar
        return render_template("participation_search.html", query=None, results=None, participation_dates=[])

    keys = r.keys("participation:*:*")
    results = []
    participation_dates = set()

    for key in keys:
        try:
            _, date, section = key.split(":")
            section = int(section)
            if query in r.smembers(key):
                results.append((date, section))
                participation_dates.add(date)
        except ValueError:
            continue

    participation_dates = sorted(participation_dates)

    return render_template("participation_search.html", query=query, results=results, participation_dates=participation_dates)

@app.route("/sandbox")
def sandbox():
    return render_template(
        "sandbox.html",
        body_class="sandbox",
        course="sandbox",
        lesson="sandbox",
        prompt_md="",
        initial_code="print(2+2)\n",
        default_args="",
    )


@app.route("/tutorials")
def tutorials():
    return render_template("tutorials.html")

@app.route("/tutorials/git")
def git():
    return render_template("git.html")

@app.route("/tutorials/ssh")
def ssh():
    return render_template("ssh.html")

@app.route("/tutorials/bash")
def bash():
    return render_template("bash.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/")
def index():
    return render_template("index.html")

#@app.route("/chat")
#def chat():
#    return render_template("chat.html")

#@socketio.on("message")
#def handle_message(msg):
#    emit("message", msg, broadcast=True)

#@app.route("/assignments")
#def show_assignments():
#    headers = {
#        "Authorization": f"Bearer {GITHUB_TOKEN}",
#        "Accept": "application/vnd.github+json"
#    }
#    url = f"https://api.github.com/orgs/{GITHUB_ORG}/repos"
#
#    try:
#        response = requests.get(url, headers=headers)
#        response.raise_for_status()
#        repos = response.json()
#
#        for assignment in assignments:
#            prefix = assignment['slug']
#            matching_repos = [repo for repo in repos if repo.get('name', '').startswith(prefix)]
#            assignment['count'] = len(matching_repos)
#            assignment['repos'] = [
#                {
#                    "name": repo["name"],
#                    "url": repo["html_url"],
#                    "pushed_at": repo["pushed_at"]
#                }
#                for repo in matching_repos
#            ]
#
#        return render_template("assignments.html", assignments=assignments)
#
#    except Exception as e:
#        return f"<h2>Failed to load assignments</h2><pre>{e}</pre><p>Check GITHUB_TOKEN and GITHUB_ORG.</p>", 500
def norm_section(s):
    if s is None:
        return None
    s = str(s).strip()
    # optional: drop leading zeros if you ever store "01"
    return s.lstrip("0") or "0"

def repo_exists(org: str, repo: str) -> bool:
    """
    Check existence of a (private) repo using the GitHub API.
    Requires GITHUB_TOKEN (or GH_TOKEN) with read access to the org.
    """
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(f"https://api.github.com/repos/{org}/{repo}",
                         headers=headers, timeout=8)
        return r.status_code == 200
    except Exception:
        return False

@app.route("/assignments", methods=["GET", "POST"])
def assignments():
    try:
        netid = request.args.get("netid") or flask_session.get("netid") or "unknown"
        roster = load_roster()

        # --- POST handlers (unchanged logic) ---------------------------------
        if request.method == "POST":
            if "netid" in request.form:  # coming from modal login
                session["netid"] = request.form["netid"].strip().lower()
                return redirect(url_for("assignments"))

            elif "github_username" in request.form:  # from GitHub username form
                username = request.form["github_username"].strip()
                if github_user_exists(username):
                    raw = load_roster_raw()
                    cmap = {c.lower().strip(): c for c in raw.columns}
                    net_col = cmap.get("netid") or cmap.get("net_id") or cmap.get("username")
                    gh_col  = cmap.get("github username") or cmap.get("github") or "GitHub Username"
                    if not net_col:
                        return "Roster missing NetID column.", 500

                    idx = raw[raw[net_col].astype(str).str.lower() == netid].index
                    if not idx.empty:
                        if gh_col not in raw.columns:
                            raw[gh_col] = ""
                        raw.at[idx[0], gh_col] = username
                        save_roster_raw(raw)
                        return redirect(url_for("assignments"))
                    else:
                        return "username not found in roster.", 400
                else:
                    return "Invalid GitHub username.", 400

        # --- GET: figure out if this student already linked -------------------
        _, match = roster_row_for_netid(netid)
        github_username = None
        section = None
        if not match.empty:
            gh = match.iloc[0].get("github")
            if (not pd.isna(gh)) and str(gh).strip() and str(gh).strip().lower() != "nan":
                github_username = str(gh).strip()
                section = section_from_row(match)

        # If no GitHub username yet → show form (same behavior as before)
        if not github_username:
            return render_template("enter_username.html", netid=netid)

        # --- Build assignments list (multiple rows, per-section links) --------
        # NOTE: put your real links here. You can add as many assignments as you want.
        # Each item may specify invite links by section using 'invite_by_section'.
        assignments = [
            {
                "slug": "a01",
                "name": "Assignment 1 – Functions/Strings/Lists",
                #"short": "Basics only: define/call functions; simple string ops; tuple/list basics.",
                "due_utc": "Oct 8, 2025 03:59",
                "sections": ["all"],        # visible to all sections or e.g. ["1","2"] not [1,2]
                "released": True,
                "template_repo": "https://github.com/hobbs-foundations-f25/a01-template",
                "readme": "https://github.com/hobbs-foundations-f25/a01-template#readme",
                "invite_by_section": {
                    # fill the ones you actually use:
                    "1": "https://classroom.github.com/a/HvPv3J5v",
                    "2": "https://classroom.github.com/a/HvPv3J5v",
                    "5": "https://classroom.github.com/a/HvPv3J5v",
                    "6": "https://classroom.github.com/a/HvPv3J5v",
                    "all":"https://classroom.github.com/a/HvPv3J5v",
                },
                # for acceptance detection
                "org": "hobbs-foundations-f25",
                "repo_prefix": "a01-template",
            },
            {
              "slug": "hw2-loops-comprehensions-dicts",
              "name": "Assignment 2 - Loops, Comprehensions & Dictionaries",
              "due_utc": "2025-10-28T23:59:00-04:00",
              "sections": ["all"],
              "released": True, 
              "template_repo": "https://github.com/hobbs-foundations-f25/hw2-loops-comprehensions-dicts",
              "invite_by_section": {
                  "all": "https://classroom.github.com/a/lcLtgWsV"
              },
              "org": "hobbs-foundations-f25",
              "repo_prefix": "hw2-loops-comprehensions-and-dictionaries",
              #"repo_prefix": "hw2-loops-comprehensions-dicts"
            },
            {
              "slug": "hw3-text-prep",
              "name": "Assignment 3 – Text Prep Utilities",
              "due_utc": "2025-11-18T23:59:00-05:00",   # <-- update as needed
              "sections": ["all"],
              "released": True,
              "template_repo": "https://github.com/hobbs-foundations-f25/hw3-template",  # <-- your repo
              "invite_by_section": {
                  "all": "https://classroom.github.com/a/WmCyI4x3"               # <-- paste invite
              },
              # used by the “I’ve accepted—refresh” button to detect the student repo
              "org": "hobbs-foundations-f25",                # <-- your org
              "repo_prefix": "hw3"                  # <-- prefix Classroom uses for student repos
            },
            {
              "slug": "hw4-language-model-beta",
              "name": "Assignment 4 – Language Model Beta",
              "due_utc": "2025-12-10T23:59:00-05:00",
              "sections": ["all"],
              "released": True,
              "template_repo": "https://github.com/hobbs-foundations-f25/foundations-2025-fall-hw4-languagemodelbeta-hw4-language-model",
              "invite_by_section": {
                "all": "https://classroom.github.com/a/6HOgjwvS"
              },
              "org": "hobbs-foundations-f25",
              "repo_prefix": "hw4-lanugagemodelbeta"
            },


        ]

        # For each assignment, select the correct invite link for this student’s section.
        # (Admins can still flip “Show all sections” in the UI; links remain per-student’s section.)
        section = norm_section(section)
        for a in assignments:
            a["invite_link"] = None
            ibs = a.get("invite_by_section") or {}
            ibs_norm = {norm_section(k): v for k, v in ibs.items()}
            a["invite_link"] = ibs_norm.get(section) or ibs_norm.get("all")
            #if section and section in ibs:
            #    a["invite_link"] = ibs[section]
            #elif "all" in ibs:
            #    a["invite_link"] = ibs["all"]

        # --- Build user_repos (only if the GitHub repo actually exists) ------------
        #user_repos = {
        #    "a01": f"https://github.com/hobbs-foundations-f25/a01-template-{github_username}"
        #}
        # --- Build user_repos (detect student repos for all assignments) ---
        user_repos = {}
        for a in assignments:
            org = a.get("org")
            prefix = a.get("repo_prefix")
            if org and prefix and github_username:
                repo_name = f"{prefix}-{github_username}"  # Classroom default naming
                if repo_exists(org, repo_name):
                    user_repos[a["slug"]] = f"https://github.com/{org}/{repo_name}"

        # --- Admin flag for the template toggle --------------------------------
        is_admin = bool(flask_session.get("is_admin"))

        # 1) Compute per-viewer invite link (by their section or 'all')
        viewer_section = (session.get("section") or "all")
        for a in assignments:
            inv_by_section = a.get("invite_by_section") or {}
            a["invite_link"] = inv_by_section.get(viewer_section) or inv_by_section.get("all")

        # 2) Build user_repos for this viewer (auto-flip Accept → View on GitHub)
        user_repos = {}
        gh_user = (github_username or "").strip()
        if gh_user:
            for a in assignments:
                org = a.get("org")
                prefix = a.get("repo_prefix")
                if not (org and prefix):
                    continue
                repo_name = f"{prefix}-{gh_user}"
                if repo_exists(org, repo_name):
                    user_repos[a["slug"]] = f"https://github.com/{org}/{repo_name}"


        return render_template(
            "assignments.html",              # use the per-assignment admin+copy template you installed
            username=github_username,
            section=section,
            is_admin=is_admin,
            assignments=assignments,
            user_repos=user_repos,
        )
    except Exception:
        return f"<pre>{traceback.format_exc()}</pre>", 500

@app.get("/admin/act_as_section")
def admin_act_as_section():
    # use the session-admin flag you already set at login()
    if not session.get("is_admin"):
        abort(403)
    sec = request.args.get("sec", type=int)
    session["admin_view_section"] = sec  # None clears override
    return redirect(request.referrer or url_for("index"))

@app.route("/admin/autograde", methods=["GET", "POST"])
def admin_autograde():
    # Only admin can access
    if not session.get("is_admin"):
        abort(403)

    # Use env if set, fallback to your usual org
    org_name = GITHUB_ORG or "hobbs-foundations-f25"

    results = None
    csv_path = None
    selected_assignment = None
    error = None

    if request.method == "POST":
        selected_assignment = (request.form.get("assignment") or "").strip()
        if selected_assignment not in ASSIGNMENTS:
            error = "Invalid assignment selected."
            flash(error, "danger")
        else:
            try:
                # base_dir is where student repos will be cloned/pulled on the server
                results, csv_path = run_autograde(
                    org=org_name,
                    assignment=selected_assignment,
                    base_dir="student_repos",
                )
                if not results:
                    flash("No repos found for that assignment/prefix.", "warning")
                else:
                    flash(f"Graded {len(results)} repos for {selected_assignment}.", "success")
            except Exception as e:
                error = str(e)
                flash(f"Autograde error: {error}", "danger")

    return render_template(
        "admin_autograde.html",
        assignments=ASSIGNMENTS,          # dict: {"hw2": {...}, "hw3": {...}, ...}
        selected_assignment=selected_assignment,
        results=results,
        csv_path=csv_path,
        error=error,
    )


def current_view_section():
    # prefer admin override if present
    sec = session.get("section")
    if session.get("is_admin"):
        sec = session.get("admin_view_section", sec)
    return sec

@app.get("/api/assignments/check")
def api_assignments_check():
    org  = request.args.get("org")
    repo = request.args.get("repo")
    if not org or not repo:
        return jsonify(ok=False), 400
    url = f"https://api.github.com/repos/{org}/{repo}"
    h   = {"Accept":"application/vnd.github+json"}
    if GITHUB_TOKEN: h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    r = requests.get(url, headers=h)
    if r.status_code == 403 and "rate limit" in r.text.lower():
        return jsonify(ok=True, exists=False, rate_limited=True)
    return jsonify(ok=True, exists=(r.status_code==200))

def _slugify(s):
    s = s.lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

@app.get("/api/assignments/check2")
def api_assignments_check2():
    org      = request.args.get("org")
    username = request.args.get("username")
    slug     = request.args.get("slug") or ""   # your internal assignment slug
    if not org or not username:
        return jsonify(ok=False), 400

    # Optional: pull the assignment title/prefix you store for better matching
    # a = Assignment.query.filter_by(slug=slug).first()
    # title   = a.title if a else slug
    # prefix1 = getattr(a, "repo_prefix", None)
    # title_slug = _slugify(title)

    headers = {"Accept":"application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    # list repos in org (private)
    repos = []
    page = 1
    while page <= 3:  # up to ~300 repos
        r = requests.get(
            f"https://api.github.com/orgs/{org}/repos",
            params={"per_page": 100, "page": page, "type": "private", "sort": "created"},
            headers=headers, timeout=15
        )
        if r.status_code == 403 and "rate limit" in r.text.lower():
            return jsonify(ok=True, exists=False, rate_limited=True)
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        repos.extend(batch)
        page += 1

    # look for repos that end with -username
    suffix = f"-{username.lower()}"
    candidates = []
    now = time.time()
    for repo in repos:
        name = repo.get("name","").lower()
        if not name.endswith(suffix):
            continue
        # must be fairly recent (last 14 days) to avoid old assignments
        created_at = repo.get("created_at") or ""
        # slack on parsing; just accept if present
        # lightweight heuristic: prefer names containing tokens from your assignment
        # tokens = {"loops","comprehensions","dictionaries","hw2"}
        tokens = {"loops","comprehensions","dictionaries","hw2"}
        score = sum(1 for t in tokens if t in name)
        candidates.append((score, repo))

    if not candidates:
        return jsonify(ok=True, exists=False)

    # best-scoring candidate
    best = sorted(candidates, key=lambda x: (-x[0], x[1].get("name","")))[0][1]
    return jsonify(ok=True, exists=True, repo_html_url=best.get("html_url"))

@app.get("/screenshots")
def screenshots_gallery():
    return render_template("screenshots_gallery.html")


def split_code_blocks(value):
    """
    Splits a string into a list of dicts: {type: 'code'|'text'|'inline_code', content: ...}
    using triple backticks as code block delimiters and single backticks for inline code.
    """
    import re
    parts = re.split(r'(```)', value)
    result = []
    in_code = False
    buffer = ''
    for part in parts:
        if part == '```':
            if buffer:
                # Further split text blocks for inline code
                if not in_code:
                    result.extend(_split_inline_code(buffer))
                else:
                    result.append({'type': 'code', 'content': buffer})
                buffer = ''
            in_code = not in_code
        else:
            buffer += part
    if buffer:
        if not in_code:
            result.extend(_split_inline_code(buffer))
        else:
            result.append({'type': 'code', 'content': buffer})
    return result

def _split_inline_code(text):
    """Helper: splits text into text and inline_code blocks using single backticks."""
    import re
    segments = re.split(r'(`[^`]+`)', text)
    result = []
    for seg in segments:
        if seg.startswith('`') and seg.endswith('`') and len(seg) > 2:
            result.append({'type': 'inline_code', 'content': seg[1:-1]})
        elif seg:
            result.append({'type': 'text', 'content': seg})
    return result

app.jinja_env.filters['split_code_blocks'] = split_code_blocks

# --- Multiple Challenge Support ---
# Redis keys:
#   weekly_challenge:list -> list of challenge IDs
#   weekly_challenge:challenge:<id> -> JSON { 'id', 'problem', 'test_cases', 'title' }
#   weekly_challenge:submissions:<id> -> list of JSON { netid, code, keystrokes, timestamp, passed, results }
#   weekly_challenge:leaderboard:<id> -> sorted set (timestamp, netid)

#@app.route("/weekly_challenge/challenges", methods=["GET"])
#def list_challenges():
#    admin_netid = request.args.get("admin_netid")
#    admin_password = request.args.get("admin_password")
#    is_admin = admin_netid and admin_password and check_admin_auth(admin_netid, admin_password)
#    ids = r.lrange("weekly_challenge:list", 0, -1)
#    challenges = []
#    for cid in ids:
#        raw = r.get(f"weekly_challenge:challenge:{cid}")
#        if raw:
#            c = json.loads(raw)
#            # Only show active challenges to students
#            if is_admin or c.get("active", True):
#                challenges.append({"id": c["id"], "title": c.get("title", c["problem"][:40]), "active": c.get("active", True)})
#    return jsonify(challenges)

@app.route("/weekly_challenge/challenges")
def get_challenges():
    if not session.get("netid"):
        return jsonify(success=False, error="Not logged in"), 403

    challenges = load_challenges()

    if session.get("is_admin"):
        return jsonify(success=True, challenges=challenges)

    published_active = [c for c in challenges if c.get("published", True) and c.get("active", True)]
    if published_active:
        return jsonify(success=True, challenges=published_active)

    active_only = [c for c in challenges if c.get("active", True)]
    return jsonify(success=True, challenges=active_only)

@app.route("/weekly_challenge/challenge/<cid>", methods=["GET"])
def get_challenge(cid):
    if not session.get("netid"):
        return jsonify({"error": "Not logged in"}), 403
    raw = r.get(f"weekly_challenge:challenge:{cid}")
    if not raw:
        return jsonify({"error": "Challenge not found."}), 404
    challenge = json.loads(raw)

    if session.get("is_admin"):
        return jsonify(challenge)

    # Students may only see published/active challenge
    if not challenge.get("active", True) and not challenge.get("published", challenge.get("active", True)):
        return jsonify({"error": "Challenge not active."}), 403

    safe = {
        "id": challenge["id"],
        "title": challenge.get("title", challenge["problem"][:40]),
        "problem": challenge["problem"],
        "test_cases": [{"input": tc["input"]} for tc in challenge.get("test_cases", [])]
    }
    if "examples" in challenge:
        safe["examples"] = challenge["examples"]
    return jsonify(safe)

#@app.route("/weekly_challenge/submit/<cid>", methods=["POST"])
#def submit_challenge(cid):
#    data = request.get_json()
#    netid = data.get("netid")
#    code = data.get("code")
#    keystrokes = data.get("keystrokes")
#    timestamp = datetime.now(est).isoformat()
#    if not (netid and code and keystrokes):
#        return jsonify({"error": "Missing fields."}), 400
#    raw = r.get(f"weekly_challenge:challenge:{cid}")
#    if not raw:
#        return jsonify({"error": "Challenge not found."}), 404
#    challenge = json.loads(raw)
#    test_cases = challenge.get("test_cases", [])
#    passed, results = run_code_against_tests(code, test_cases)
#    submission = {
#        "netid": netid,
#        "code": code,
#        "keystrokes": keystrokes,
#        "timestamp": timestamp,
#        "passed": passed,
#        "results": results
#    }
#    r.rpush(f"weekly_challenge:submissions:{cid}", json.dumps(submission))
#    if passed:
#        r.zadd(f"weekly_challenge:leaderboard:{cid}", {netid: datetime.now().timestamp()})
#    return jsonify({"passed": passed, "results": results})

@app.route("/weekly_challenge/submit/<challenge_id>", methods=["POST"])
def submit_challenge(challenge_id):
    if not session.get("netid"):
        return jsonify(success=False, error="Not logged in"), 403

    data = request.json or {}
    netid = session["netid"]
    code = data.get("code", "")
    keystrokes = data.get("keystrokes", "")

    # run + store like before, but also return results now
    raw = r.get(f"weekly_challenge:challenge:{challenge_id}")
    if not raw:
        return jsonify(success=False, error="Challenge not found"), 404
    ch = json.loads(raw)
    passed, results = run_code_against_tests(code, ch.get("test_cases", []))

    submission = {
        "netid": netid,
        "code": code,
        "keystrokes": keystrokes or [],
        "timestamp": datetime.now(est).isoformat(),
        "passed": passed,
        "results": results
    }
    r.rpush(f"weekly_challenge:submissions:{challenge_id}", json.dumps(submission))
    if passed:
        r.zadd(f"weekly_challenge:leaderboard:{challenge_id}", {netid: datetime.now().timestamp()})

    return jsonify(success=True, passed=passed, results=results)

@app.route("/weekly_challenge/leaderboard/<cid>", methods=["GET"])
def get_leaderboard(cid):
    def _dec(x): return x.decode("utf-8", "ignore") if isinstance(x, (bytes, bytearray)) else x

    leaderboard = r.zrange(f"weekly_challenge:leaderboard:{cid}", 0, -1, withscores=True)
    raw = r.get(f"weekly_challenge:challenge:{cid}")
    solutions_available_date = None
    if raw:
        challenge = json.loads(_dec(raw))
        solutions_available_date = challenge.get("solutions_available_date")

    out = []
    for netid, score in leaderboard:
        netid = _dec(netid)
        out.append({
            "netid": netid,
            "display_name": get_display_name(netid),
            "timestamp": datetime.fromtimestamp(score, est).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return jsonify({"leaderboard": out, "solutions_available_date": solutions_available_date})

@app.route("/weekly_challenge/submissions/<cid>", methods=["GET"])
def get_submissions(cid):
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 403
    submissions = r.lrange(f"weekly_challenge:submissions:{cid}", 0, -1)
    out = []
    for s in submissions:
        try:
            obj = json.loads(s)
            obj["display_name"] = get_display_name(obj.get("netid", ""))
            out.append(obj)
        except Exception:
            continue
    return jsonify(out)


@app.route("/weekly_challenge/remove_leaderboard/<cid>", methods=["POST"])
def remove_from_leaderboard_multi(cid):
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 403
    netid = request.json.get("netid")
    if not netid:
        return jsonify({"error": "Missing netid"}), 400
    r.zrem(f"weekly_challenge:leaderboard:{cid}", netid)
    return jsonify({"success": True})


# Admin: add/edit/delete challenges
#@app.route("/weekly_challenge/add", methods=["POST"])
#def add_challenge():
#    admin_netid = request.args.get("netid")
#    admin_password = request.args.get("password")
#    if not check_admin_auth(admin_netid, admin_password):
#        abort(403)
#    data = request.get_json()
#    problem = data.get("problem")
#    test_cases = data.get("test_cases")
#    title = data.get("title") or problem[:40]
#    # Set solutions_available_date to 1 week from now if not provided
#    solutions_available_date = data.get("solutions_available_date")
#    if not solutions_available_date:
#        solutions_available_date = (datetime.now(est) + timedelta(days=7)).strftime("%Y-%m-%d")
#    active = data.get("active", False)  # New challenges default to inactive
#    if not (problem and test_cases):
#        return jsonify({"error": "Missing fields."}), 400
#    challenge_id = str(uuid4())
#    challenge = {
#        "id": challenge_id,
#        "problem": problem,
#        "test_cases": test_cases,
#        "title": title,
#        "solutions_available_date": solutions_available_date,
#        "active": active
#    }
#    if "examples" in data:
#        challenge["examples"] = data["examples"]
#    r.set(f"weekly_challenge:challenge:{challenge_id}", json.dumps(challenge))
#    r.lpush("weekly_challenge:list", challenge_id)
#    return jsonify({"success": True, "id": challenge_id})

@app.route("/weekly_challenge/add", methods=["POST"])
def add_challenge():
    if not session.get("is_admin"):
        return jsonify(success=False, error="Unauthorized"), 403

    data = request.json
    # validate + add
    save_challenge(data)
    return jsonify(success=True)


@app.route("/weekly_challenge/delete/<cid>", methods=["POST"])
def delete_challenge(cid):
    admin_netid = request.args.get("netid")
    admin_password = request.args.get("password")
    if not check_admin_auth(admin_netid, admin_password):
        abort(403)
    r.delete(f"weekly_challenge:challenge:{cid}")
    r.delete(f"weekly_challenge:submissions:{cid}")
    r.delete(f"weekly_challenge:leaderboard:{cid}")
    r.lrem("weekly_challenge:list", 0, cid)
    return jsonify({"success": True})

#@app.route("/weekly_challenge/edit/<cid>", methods=["POST"])
#def edit_challenge(cid):
    #admin_netid = request.args.get("netid")
    #admin_password = request.args.get("password")
    #if not check_admin_auth(admin_netid, admin_password):
        #abort(403)
    #raw = r.get(f"weekly_challenge:challenge:{cid}")
    #if not raw:
        #return jsonify({"error": "Challenge not found."}), 404
    #challenge = json.loads(raw)
    #data = request.get_json()
    # Update fields if present
    #for field in ["title", "problem", "examples", "solutions_available_date"]:
        #if field in data:
            #challenge[field] = data[field]
    # Only update test_cases if present and not empty/null
    #if "test_cases" in data and data["test_cases"]:
        #challenge["test_cases"] = data["test_cases"]
    #r.set(f"weekly_challenge:challenge:{cid}", json.dumps(challenge))
    #return jsonify({"success": True, "challenge": challenge})

@app.route("/weekly_challenge/edit/<challenge_id>", methods=["POST"])
def edit_challenge(challenge_id):
    if not session.get("is_admin"):
        return jsonify(success=False, error="Unauthorized"), 403

    data = request.json
    update_challenge(challenge_id, data)
    return jsonify(success=True)


@app.route("/weekly_challenge/toggle_active/<cid>", methods=["POST"])
def toggle_challenge_active(cid):
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 403
    raw = r.get(f"weekly_challenge:challenge:{cid}")
    if not raw:
        return jsonify({"error": "Challenge not found."}), 404
    challenge = json.loads(raw)
    challenge["active"] = not challenge.get("active", False)
    r.set(f"weekly_challenge:challenge:{cid}", json.dumps(challenge))
    return jsonify({"success": True, "active": challenge["active"]})


#@app.route("/weekly_challenge/reorder", methods=["POST"])
#def reorder_challenges():
#    admin_netid = request.json.get("admin_netid")
#    admin_password = request.json.get("admin_password")
#    ids = request.json.get("ids")
#    if not check_admin_auth(admin_netid, admin_password):
#        return jsonify({"error": "Invalid admin credentials"}), 403
#    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
#        return jsonify({"error": "Invalid ids list"}), 400
#    # Remove all and re-add in new order
#    r.delete("weekly_challenge:list")
#    for cid in reversed(ids):
#        r.lpush("weekly_challenge:list", cid)
#    return jsonify({"success": True})

@app.route("/weekly_challenge/reorder", methods=["POST"])
def reorder_challenges():
    if not session.get("is_admin"):
        return jsonify(success=False, error="Unauthorized"), 403

    order = request.json.get("order")
    if not order:
        return jsonify(success=False, error="Missing order"), 400

    reorder_and_save(order)
    return jsonify(success=True)


# --- Code execution sandbox (updated for print output) ---
@app.post("/api/sandbox/run")
def api_sandbox_run():
    data = request.get_json(silent=True) or {}
    code = data.get("code", "")

    res = run_python_in_docker(code, timeout_s=3)
    return jsonify(stdout=res.get("stdout",""), stderr=res.get("stderr",""), exit_code=res.get("exit_code", 0))

# ----- Weekly Challenge helpers (Redis-backed) -----

def load_challenges():
    """
    Load challenges in order from 'weekly_challenge:list', falling back to scanning keys.
    Handles Redis bytes <-> str so we don't silently drop items.
    """
    def _dec(x):
        return x.decode("utf-8", "ignore") if isinstance(x, (bytes, bytearray)) else x

    def _normalize(ch):
        ch = dict(ch or {})
        ch.setdefault("id", ch.get("_id") or ch.get("cid") or ch.get("uuid") or str(uuid4()))
        ch.setdefault("title", (ch.get("problem") or "")[:40] or f"Challenge {ch['id'][:6]}")
        ch.setdefault("test_cases", ch.get("tests") or ch.get("cases") or [])
        if "published" not in ch: ch["published"] = True
        if "active" not in ch: ch["active"] = True
        sol_date = ch.get("solutions_available_date") or ch.get("solutions_date") or ch.get("solutions")
        if not sol_date:
            sol_date = (datetime.now(est) + timedelta(days=7)).strftime("%Y-%m-%d")
        ch["solutions_available_date"] = sol_date
        return ch

    # Ordered list first
    ids_raw = r.lrange("weekly_challenge:list", 0, -1)
    ids = [_dec(i) for i in ids_raw]
    out = []
    if ids:
        for cid in ids:
            raw = r.get(f"weekly_challenge:challenge:{cid}")
            if not raw:
                continue
            try:
                out.append(_normalize(json.loads(_dec(raw))))
            except Exception:
                continue
        if out:
            return out

    # Fallback: scan keys
    for key in r.keys("weekly_challenge:challenge:*"):
        key = _dec(key)
        raw = r.get(key)
        if not raw:
            continue
        try:
            out.append(_normalize(json.loads(_dec(raw))))
        except Exception:
            continue

    # Rebuild the list in a stable order if we found any via scan
    if out:
        out.sort(key=lambda c: (str(c.get("title") or ""), str(c.get("id"))))
        pipe = r.pipeline()
        pipe.delete("weekly_challenge:list")
        for c in out:
            pipe.rpush("weekly_challenge:list", c["id"])
            r.set(f"weekly_challenge:challenge:{c['id']}", json.dumps(c))
        pipe.execute()

    return out

def save_challenge(data):
    """Create a new challenge; ensure ID is pushed to weekly_challenge:list."""
    def _dec(x): return x.decode("utf-8", "ignore") if isinstance(x, (bytes, bytearray)) else x

    problem = (data or {}).get("problem", "").strip()
    test_cases = (data or {}).get("test_cases", [])
    if not problem or not isinstance(test_cases, list) or not test_cases:
        raise ValueError("Missing problem or test_cases")

    cid = data.get("id") or str(uuid4())
    title = data.get("title") or problem[:40]
    published = bool(data.get("published", True))
    active = bool(data.get("active", True))
    sol_date = data.get("solutions_available_date") or (datetime.now(est) + timedelta(days=7)).strftime("%Y-%m-%d")

    challenge = {
        "id": cid,
        "title": title,
        "problem": problem,
        "test_cases": test_cases,
        "published": published,
        "active": active,
        "solutions_available_date": sol_date
    }
    if "examples" in data:
        challenge["examples"] = data["examples"]

    r.set(f"weekly_challenge:challenge:{cid}", json.dumps(challenge))
    existing = [_dec(x) for x in r.lrange("weekly_challenge:list", 0, -1)]
    if cid not in existing:
        r.rpush("weekly_challenge:list", cid)

def update_challenge(challenge_id, data):
    """Update fields of an existing challenge."""
    raw = r.get(f"weekly_challenge:challenge:{challenge_id}")
    if not raw:
        raise ValueError("Challenge not found")
    ch = json.loads(raw)

    for k in ["title", "problem", "examples", "published", "active", "solutions_available_date"]:
        if k in data:
            ch[k] = data[k]
    if "test_cases" in data and isinstance(data["test_cases"], list) and data["test_cases"]:
        ch["test_cases"] = data["test_cases"]

    r.set(f"weekly_challenge:challenge:{challenge_id}", json.dumps(ch))

def reorder_and_save(order_ids):
    """Rewrite weekly_challenge:list to the provided list of ids."""
    if not isinstance(order_ids, list) or not all(isinstance(i, str) for i in order_ids):
        raise ValueError("order must be list[str]")
    # ensure all exist
    valid = []
    for cid in order_ids:
        if r.get(f"weekly_challenge:challenge:{cid}"):
            valid.append(cid)
    pipe = r.pipeline()
    pipe.delete("weekly_challenge:list")
    for cid in valid:
        pipe.rpush("weekly_challenge:list", cid)
    pipe.execute()

def record_submission(challenge_id, netid, code, keystrokes):
    """Run tests, store submission, and update leaderboard on pass."""
    raw = r.get(f"weekly_challenge:challenge:{challenge_id}")
    if not raw:
        raise ValueError("Challenge not found")
    ch = json.loads(raw)
    test_cases = ch.get("test_cases", [])

    passed, results = run_code_against_tests(code, test_cases)
    submission = {
        "netid": netid,
        "code": code,
        "keystrokes": keystrokes or [],
        "timestamp": datetime.now(est).isoformat(),
        "passed": passed,
        "results": results
    }
    r.rpush(f"weekly_challenge:submissions:{challenge_id}", json.dumps(submission))
    if passed:
        r.zadd(f"weekly_challenge:leaderboard:{challenge_id}", {netid: datetime.now().timestamp()})

@app.route("/api/notebooks")
def api_notebooks():
    if session.get("is_admin"):
        section_str = (
        request.args.get("section")
        or str(session.get("admin_view_section") or session.get("section") or "")
        or next(iter(SECTION_REPOS.keys()), None)
        )
        if section_str is None:
            return jsonify(success=False, error="No sections configured"), 500
    else:
        netid = session.get("netid")
        if not netid:
            return jsonify(success=False, error="Not logged in"), 403
        roster = load_roster()
        _, row = roster_row_for_netid(netid)
        if row.empty:
            return jsonify(success=False, error="Roster match not found"), 403
        section_str = str(section_from_row(row))

        #row = roster.loc[roster["NetID"].str.lower() == netid.lower()]
        #row = roster.loc[roster["netid_lc"] == netid.lower()]
        #if row.empty:
        #    return jsonify(success=False, error="Roster match not found"), 403
        #section_str = str(int(row.iloc[0]["Section"]))

    repo = SECTION_REPOS.get(section_str)
    if not repo:
        return jsonify(success=False, error="Invalid section"), 400

    items_nb   = list_notebooks_from_github(repo, folder="notebooks")
    items_root = list_notebooks_from_github(repo, folder="")  # repo root
    # de-dupe by filename
    seen = set()
    items = []
    for it in items_nb + items_root:
        if it["filename"] in seen: 
            continue
        seen.add(it["filename"])
        items.append(it)
    return jsonify(success=True, items=items, section=int(section_str))


def run_code_against_tests(code, test_cases):
    """Run code against test cases. Distinguish between print and return-based challenges."""
    results = []
    passed = True
    for tc in test_cases:
        try:
            local_vars = {}
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                exec(code, {}, local_vars)
                func = local_vars.get('solution')
                if not func:
                    raise Exception("No function named 'solution'")
                # Support both positional and no-argument calls
                if isinstance(tc["input"], list):
                    result = func(*tc["input"])
                else:
                    result = func(tc["input"])
            printed = f.getvalue()
            # If expected output is not None, check if this is a print or return challenge
            # If the expected output is a string and the function returns None, treat as print-based
            # If the function returns a string, treat as return-based
            # If the test case has a 'mode' key, use it ('print' or 'return')
            mode = tc.get('mode')
            if mode == 'print' or (mode is None and result is None and isinstance(tc["output"], str)):
                # Print-based: compare printed output
                ok = printed == tc["output"]
            else:
                # Return-based: compare return value
                ok = result == tc["output"]
            results.append({
                "input": tc["input"],
                "printed": printed,
                "output": result,
                "expected": tc["output"],
                "passed": ok
            })
            if not ok:
                passed = False
        except Exception as e:
            results.append({
                "input": tc["input"],
                "printed": None,
                "output": None,
                "expected": tc["output"],
                "passed": False,
                "error": str(e)
            })
            passed = False
    return passed, results

@app.route("/weekly_challenge")
def weekly_challenge_page():
    if not session.get("netid"):
        return redirect(url_for("index"))  # force login first

    section = session.get("section")
    if session.get("is_admin"):
        # Admins can override via query or dropdown later
        section = request.args.get("section", section)

    raw = r.get("weekly_challenge:current")
    challenge = json.loads(raw) if raw else None
    return render_template(
        "weekly_challenge.html",
        netid=session["netid"],
        section=section,
        is_admin=session.get("is_admin", False),
        challenge=challenge
    )


@app.route("/weekly_challenge/solution_replay/<cid>/<netid>", methods=["GET"])
def solution_replay(cid, netid):
    raw = r.get(f"weekly_challenge:challenge:{cid}")
    if not raw:
        return jsonify({"error": "Challenge not found."}), 404
    challenge = json.loads(raw)
    sol_date = challenge.get("solutions_available_date")
    if not sol_date:
        return jsonify({"error": "No solutions date set."}), 403
    now = datetime.now(est).date()
    sol_date_dt = datetime.strptime(sol_date, "%Y-%m-%d").date()
    if now < sol_date_dt:
        return jsonify({"error": "Solutions not available yet."}), 403
    # Find the latest passed submission for this netid (iterate from end)
    submissions = r.lrange(f"weekly_challenge:submissions:{cid}", 0, -1)
    for s in reversed(submissions):
        sub = json.loads(s)
        if sub.get("netid") == netid and sub.get("passed"):
            return jsonify({"keystrokes": sub.get("keystrokes", [])})
    return jsonify({"error": "No passed solution found for this user."}), 404

# >>> Minimal fix: don't auto-run at import time
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
# <<<

