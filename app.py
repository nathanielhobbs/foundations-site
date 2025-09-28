import os
import requests
import traceback
from dotenv import load_dotenv
from flask import Flask, render_template, request, Response, abort, redirect, url_for, session, make_response
import pandas as pd
from flask_socketio import SocketIO, emit, join_room, disconnect
import redis
from datetime import datetime, timedelta
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


load_dotenv()

SECTION_REPOS = {
    "1": "foundations-f25-sec1",
    "2": "foundations-f25-sec2",
    "5": "foundations-f25-sec5",
    "6": "foundations-f25-sec6",
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

CURRENT_LOGIN_VERSION = "2025-09-24-username-reset"

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

db.init_app(app)

from lecture import lecture_bp
app.register_blueprint(lecture_bp)

# Make sure models are imported before create_all()
from models_lecture import LectureChallenge, LectureSubmission
# ... import any other models you want in the same metadata

# NOTE: Flask 3.x removed before_first_request. Just do this once at import time.
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        app.logger.warning(f"db.create_all() skipped/failed: {e}")

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")
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
    Return 'First L.' (and Section if available), else fallback to netid.
    """
    try:
        roster, row = roster_row_for_netid(netid)
        if row.empty:
            return netid

        first = (row.iloc[0].get("first") or "").strip()
        last  = (row.iloc[0].get("last") or "").strip()
        sect  = row.iloc[0].get("section")

        # Build base name
        if first or last:
            last_initial = (last[:1] or "").upper()
            name = f"{first} {last_initial}.".strip()
        else:
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

def _is_open_now(ch):
    now = datetime.now(est)
    if not ch.is_open:
        return False
    if ch.open_at and now < (ch.open_at.astimezone(est) if ch.open_at.tzinfo else ch.open_at):
        return False
    if ch.close_at and now > (ch.close_at.astimezone(est) if ch.close_at.tzinfo else ch.close_at):
        return False
    return True

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

# --- Admin: list all lecture challenges ---
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
    def _open_now(ch):
        return _is_open_now(ch) if "_is_open_now" in globals() else (
            ch.is_open and
            (ch.open_at is None or datetime.now(est) >= (ch.open_at.astimezone(est) if ch.open_at.tzinfo else ch.open_at)) and
            (ch.close_at is None or datetime.now(est) <= (ch.close_at.astimezone(est) if ch.close_at.tzinfo else ch.close_at))
        )

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
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    url = f"https://api.github.com/repos/{GITHUB_NOTES_ORG}/{repo}/contents/{folder}"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return []

    items = []
    for file in resp.json():
        if not file["name"].endswith(".ipynb"):
            continue

        # Get last commit date for this file
        commits_url = f"https://api.github.com/repos/{GITHUB_NOTES_ORG}/{repo}/commits"
        params = {"path": f"{folder}/{file['name']}", "per_page": 1}
        c_resp = requests.get(commits_url, headers=headers, params=params)
        commit_date = None
        if c_resp.status_code == 200 and c_resp.json():
            commit_date = c_resp.json()[0]["commit"]["committer"]["date"]

        # Build direct raw URL for download
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_NOTES_ORG}/{repo}/main/{folder}/{file['name']}"

        items.append({
            "title": file["name"].replace(".ipynb", ""),
            "github_path": f"{GITHUB_NOTES_ORG}/{repo}/blob/main/{folder}/{file['name']}",
            "download_url": raw_url,
            "date": commit_date
        })

    # Sort newest first
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

@app.context_processor
def inject_active_lecture():
    """
    Make an 'active_lecture' available to all templates.
    Priority:
      1) Redis override: lecture_challenge:active_slug
      2) Fallback: most recently-created open challenge right now
    """
    try:
        active_slug = r.get("lecture_challenge:active_slug")
        if active_slug:
            ch = LectureChallenge.query.filter_by(slug=active_slug).first()
            if ch:
                return {"active_lecture": {"slug": ch.slug, "title": ch.title}}
        # Fallback: “best open” by created_at DESC
        ch = (LectureChallenge.query
              .order_by(LectureChallenge.created_at.desc())
              .all())
        for c in ch:
            if _is_open_now(c):
                return {"active_lecture": {"slug": c.slug, "title": c.title}}
    except Exception:
        pass
    return {"active_lecture": None}

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


@app.route("/notebooks")
def notebooks():
    if session.get("is_admin"):
        return render_template("notebooks.html", section=None, is_admin=True)

    netid = session.get("netid")
    if not netid:
        # was: redirect(url_for("login")) which is POST-only
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


@app.route("/set_section", methods=["POST"])
def set_section():
    if not session.get("is_admin"):
        return jsonify(success=False, error="Unauthorized"), 403

    new_section = request.json.get("section")
    if new_section not in ["1", "2", "5", "6"]:
        return jsonify(success=False, error="Invalid section"), 400

    session["section"] = int(new_section)
    return jsonify(success=True, section=session["section"])


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

    
@app.route("/participation_dashboard")
def participation_dashboard():
    check_admin_access()
    passcode = request.args.get("code")

    keys = r.keys("participation:*:*")
    entries = []
    for key in keys:
        try:
            _, date, section = key.split(":")
            entries.append((date, int(section)))
        except ValueError:
            continue

    entries = sorted(set(entries))

    return render_template("participation_dashboard.html",
                           entries=entries,
                           passcode=passcode)


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
    return render_template("sandbox.html")

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
    # Lightweight existence check (no token needed)
    url = f"https://github.com/{org}/{repo}"
    try:
        r = requests.get(url, timeout=5)
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
                "name": "Assignment1 – Functions/Strings/Lists",
                "short": "Basics only: define/call functions; simple string ops; tuple/list basics.",
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
            #{
            #    "slug": "a02",
            #    "name": "Assignment2 – Coming soon...",
            #    "due_utc": None,
            #    "sections": ["all"],
            #    "released": False,
            #    "invite_by_section": {},    # not released yet
            #},
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
        user_repos = {
            "a01": f"https://github.com/hobbs-foundations-f25/a01-template-{github_username}"
        }
        #user_repos = {}
        #for a in assignments:
        #    org = a.get("org")
        #    prefix = a.get("repo_prefix")
        #    if org and prefix and github_username:
        #        repo_name = f"{prefix}-{github_username}"  # Classroom default
        #        if repo_exists(org, repo_name):
        #            user_repos[a["slug"]] = f"https://github.com/{org}/{repo_name}"

        # --- Admin flag for the template toggle --------------------------------
        is_admin = bool(flask_session.get("is_admin"))

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
    """Very small code runner for the sandbox."""
    from io import StringIO
    import contextlib, traceback as tb

    data = request.get_json(silent=True) or {}
    code = data.get("code", "")

    out_buf, err_buf = StringIO(), StringIO()
    try:
        g = {}  # no builtins injected; you can allow a few safe ones if needed
        l = {}
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            exec(code, g, l)
        return jsonify(stdout=out_buf.getvalue(), stderr=err_buf.getvalue())
    except Exception:
        return jsonify(stdout=out_buf.getvalue(),
                       stderr=err_buf.getvalue() + tb.format_exc()), 200

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
        section_str = request.args.get("section") or str(session.get("section") or "1")
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

    items = list_notebooks_from_github(repo, folder="notebooks")
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

