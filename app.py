import os
import requests
import traceback
from dotenv import load_dotenv
from flask import Flask, render_template, request, Response, abort, redirect, url_for, session
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
from flask import make_response

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'foundationsP4ss;'
app.config['ADMIN_PASSCODE'] = 'fnP4ssword;'  
app.config['ADMIN_NETID'] = 'nh385'
app.config['ADMIN_PASSWORD'] = 'foundationsP4ss;'
app.config['ROSTER_FILE'] = "data/github_roster.csv"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

ROSTER_FILE = 'data/github_roster.csv'

# EST timezone
est = pytz.timezone('US/Eastern')

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_ORG = os.environ.get("GITHUB_ORG")

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
    return pd.read_csv(ROSTER_FILE)

def save_roster(df):
    df.to_csv(ROSTER_FILE, index=False)

def get_display_name(netid):
    try:
        roster = load_roster()
        row = roster.loc[roster["NetID"].str.lower() == netid.lower()]
        if not row.empty:
            first = row.iloc[0]["Full Name"].split(', ')[1].split()[0]
            last_initial = row.iloc[0]["Full Name"][0]
            #first = row.iloc[0]["First Name"]
            #last_initial = row.iloc[0]["Last Name"][0] if pd.notna(row.iloc[0]["Last Name"]) else ""
            section = row.iloc[0]["Section"]
            return f"{first} {last_initial} (Section {section})"
    except Exception as e:
        print(f"Roster lookup failed for {netid}: {e}")
    return netid  # fallback if not found


def github_user_exists(username):
    r = requests.get(f"https://api.github.com/users/{username}")
    return r.status_code == 200

def check_admin_access():
    code = request.args.get("code")
    if code != app.config['ADMIN_PASSCODE']:
        abort(403)

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

@app.route("/login_netid", methods=["POST"])
def login_netid():
    netid = request.form.get("netid", "").strip().lower()
    if not netid:
        return "Invalid NetID", 400

    # Save in session
    flask_session["netid"] = netid

    # Send them back to the username linking page
    return redirect(url_for("assignments"))

@app.route("/notebooks")
def notebooks():
    section = request.args.get("section")
    instructor = request.args.get("code") == app.config["ADMIN_PASSCODE"]

    if instructor:
        keys = r.keys("notebooks:section:*")
        all_links = {}
        for key in keys:
            sec_id = key.split(":")[-1]
            raw = r.get(key)
            links = json.loads(raw) if raw else []
            all_links[sec_id] = links
        return render_template("notebooks.html", all_sections=all_links, instructor=True)
    else:
        key = f"notebooks:section:{section}"
        raw = r.get(key)
        links = json.loads(raw) if raw else []
        return render_template("notebooks.html", section=section, links=links)



# Route: chat by section
@app.route("/chat/<int:section>")
def chat(section):
    raw = r.lrange(f"chat:{section}", 0, -1)
    messages = []

    for item in raw:
        try:
            msg_obj = json.loads(item)
            # Ensure all expected fields are present
            if isinstance(msg_obj, dict):
                msg_obj.setdefault("netid", "unknown")
                msg_obj.setdefault("msg", "")
                msg_obj.setdefault("timestamp", "[unknown]")
                msg_obj.setdefault("reply", None)
                msg_obj.setdefault("edited", False)
                msg_obj.setdefault("message_id", f"{section}:{msg_obj.get('timestamp', '[unknown]')}:{hash(msg_obj.get('msg', '')) % 1000000}")
                msg_obj.setdefault("admin_flags", {})
                msg_obj.setdefault("support_count", 0)
                msg_obj.setdefault("support_votes", [])
                # Format timestamp for display
                msg_obj["timestamp"] = format_timestamp_for_display(msg_obj["timestamp"])
                msg_obj["display_name"] = get_display_name(msg_obj["netid"])
                messages.append(msg_obj)
            else:
                # fallback for malformed entries
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
            # fallback for old string messages
            messages.append({
                "netid": "unknown",
                "msg": item,
                "timestamp": "[old]",
                "reply": None,
                "edited": False,
                "message_id": f"{section}:[old]:{hash(item) % 1000000}",
                "admin_flags": {},
                "support_count": 0,
                "support_votes": []
            })

    netid = flask_session.get("netid") or request.args.get("netid") or ""
    display_name = get_display_name(netid).split('(')[0] if netid else ""
    return render_template("chat.html", section=section, messages=messages, display_name=display_name)

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


# When a user joins, assign them to a room
@socketio.on("join")
def on_join(data):
    section = data["section"]
    netid = data.get("netid") or flask_session.get("netid") or "unknown"
    join_room(section)
    if netid:
        r.sadd(f"chat:participants:{section}", netid)
        # Track socket id to netid/section
        socket_to_user[request.sid] = {"netid": netid, "section": section}
        # Broadcast updated list to room
        #participants = list(r.smembers(f"chat:participants:{section}"))
        participants = [get_display_name(n) for n in r.smembers(f"chat:participants:{section}")]
        socketio.emit("participants", {"section": section, "participants": participants}, to=section)
        # Also emit to the joining user directly
        emit("participants", {"section": section, "participants": participants})

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
    raw_msg = data.get("msg")
    netid = data.get("netid", "unknown")  # Get netid from data parameter
    reply = None
    if "|||reply|||" in raw_msg:
        raw_msg, reply = raw_msg.split("|||reply|||", 1)

    timestamp = get_est_timestamp()
    today = datetime.now(est).strftime("%Y-%m-%d")

    # Track participation
    r.sadd(f"participation:{today}:{section}", netid)

    # Create structured message
    msg_obj = {
        "netid": netid,
        "msg": raw_msg.strip(),
        "timestamp": timestamp,
        "reply": reply,
        "edited": False,
        "message_id": f"{section}:{timestamp}:{hash(raw_msg.strip()) % 1000000}",
        "admin_flags": {},
        "support_count": 0
    }

    # Store JSON in Redis
    r.rpush(f"chat:{section}", json.dumps(msg_obj))

    # Send structured message to clients
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

@app.route("/assignments", methods=["GET", "POST"])
def assignments():
    try:
        netid = request.args.get("netid") or flask_session.get("netid") or "unknown"
        roster = load_roster()

        # Check if student already linked
        match = roster.loc[roster["NetID"] == netid]
        if not match.empty and pd.notna(match.iloc[0]["GitHub Username"]):
            github_username = match.iloc[0]["GitHub Username"]
            section = match.iloc[0]["Section"]

            # ✅ Already linked → show assignments
            links = {
                "01": "https://classroom.github.com/a/link_for_01",
                "02": "https://classroom.github.com/a/link_for_02",
                "03": "https://classroom.github.com/a/link_for_03",
                "04": "https://classroom.github.com/a/link_for_04",
            }
            return render_template("assignments.html",
                                   username=github_username,
                                   section=section,
                                   invite_link=links.get(str(section)))

        # If POST: student is submitting GitHub username
        if request.method == "POST":
            if "netid" in request.form:  # coming from modal login
                session["netid"] = request.form["netid"].strip().lower()
                return redirect(url_for("assignments"))
            elif "github_username" in request.form:  # coming from GitHub username form
                username = request.form["github_username"].strip()
                if github_user_exists(username):
                    # Update roster
                    idx = roster[roster["NetID"] == netid].index
                    if not idx.empty:
                        roster.at[idx[0], "GitHub Username"] = username
                        save_roster(roster)
                        return redirect(url_for("assignments"))
                    else:
                        return "NetID not found in roster.", 400
                else:
                    return "Invalid GitHub username.", 400

        # If GET and no GitHub username yet → show form
        return render_template("enter_username.html", netid=netid)
    except Exception as e:
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

@app.route("/weekly_challenge/challenges", methods=["GET"])
def list_challenges():
    admin_netid = request.args.get("admin_netid")
    admin_password = request.args.get("admin_password")
    is_admin = admin_netid and admin_password and check_admin_auth(admin_netid, admin_password)
    ids = r.lrange("weekly_challenge:list", 0, -1)
    challenges = []
    for cid in ids:
        raw = r.get(f"weekly_challenge:challenge:{cid}")
        if raw:
            c = json.loads(raw)
            # Only show active challenges to students
            if is_admin or c.get("active", True):
                challenges.append({"id": c["id"], "title": c.get("title", c["problem"][:40]), "active": c.get("active", True)})
    return jsonify(challenges)

@app.route("/weekly_challenge/challenge/<cid>", methods=["GET"])
def get_challenge(cid):
    admin_netid = request.args.get("admin_netid")
    admin_password = request.args.get("admin_password")
    raw = r.get(f"weekly_challenge:challenge:{cid}")
    if not raw:
        return jsonify({"error": "Challenge not found."}), 404
    challenge = json.loads(raw)
    is_admin = admin_netid and admin_password and check_admin_auth(admin_netid, admin_password)
    # Only allow students to see active challenges
    if not is_admin and not challenge.get("active", True):
        return jsonify({"error": "Challenge not active."}), 403
    # If admin credentials are valid, return full challenge
    if is_admin:
        return jsonify(challenge)
    # Otherwise, return student-safe version
    safe_challenge = {
        "id": challenge["id"],
        "title": challenge.get("title", challenge["problem"][:40]),
        "problem": challenge["problem"],
        "test_cases": [{"input": tc["input"]} for tc in challenge.get("test_cases", [])]
    }
    if "examples" in challenge:
        safe_challenge["examples"] = challenge["examples"]
    return jsonify(safe_challenge)

@app.route("/weekly_challenge/submit/<cid>", methods=["POST"])
def submit_challenge(cid):
    data = request.get_json()
    netid = data.get("netid")
    code = data.get("code")
    keystrokes = data.get("keystrokes")
    timestamp = datetime.now(est).isoformat()
    if not (netid and code and keystrokes):
        return jsonify({"error": "Missing fields."}), 400
    raw = r.get(f"weekly_challenge:challenge:{cid}")
    if not raw:
        return jsonify({"error": "Challenge not found."}), 404
    challenge = json.loads(raw)
    test_cases = challenge.get("test_cases", [])
    passed, results = run_code_against_tests(code, test_cases)
    submission = {
        "netid": netid,
        "code": code,
        "keystrokes": keystrokes,
        "timestamp": timestamp,
        "passed": passed,
        "results": results
    }
    r.rpush(f"weekly_challenge:submissions:{cid}", json.dumps(submission))
    if passed:
        r.zadd(f"weekly_challenge:leaderboard:{cid}", {netid: datetime.now().timestamp()})
    return jsonify({"passed": passed, "results": results})

@app.route("/weekly_challenge/leaderboard/<cid>", methods=["GET"])
def get_leaderboard(cid):
    leaderboard = r.zrange(f"weekly_challenge:leaderboard:{cid}", 0, -1, withscores=True)
    raw = r.get(f"weekly_challenge:challenge:{cid}")
    solutions_available_date = None
    if raw:
        challenge = json.loads(raw)
        solutions_available_date = challenge.get("solutions_available_date")
    leaderboard_out = [
            {"netid": netid, "display_name": get_display_name(netid), "timestamp": datetime.fromtimestamp(score, est).strftime("%Y-%m-%d %H:%M:%S")}
        for netid, score in leaderboard
    ]
    return jsonify({"leaderboard": leaderboard_out, "solutions_available_date": solutions_available_date})

@app.route("/weekly_challenge/submissions/<cid>", methods=["GET"])
def get_submissions(cid):
    admin_netid = request.args.get("admin_netid")
    admin_password = request.args.get("admin_password")
    if not check_admin_auth(admin_netid, admin_password):
        return jsonify({"error": "Invalid admin credentials"}), 403
    submissions = r.lrange(f"weekly_challenge:submissions:{cid}", 0, -1)
    out = [json.loads(s) for s in submissions]
    return jsonify(out)

@app.route("/weekly_challenge/remove_leaderboard/<cid>", methods=["POST"])
def remove_from_leaderboard_multi(cid):
    admin_netid = request.json.get("admin_netid")
    admin_password = request.json.get("admin_password")
    netid = request.json.get("netid")
    if not check_admin_auth(admin_netid, admin_password):
        return jsonify({"error": "Invalid admin credentials"}), 403
    r.zrem(f"weekly_challenge:leaderboard:{cid}", netid)
    return jsonify({"success": True})

# Admin: add/edit/delete challenges
@app.route("/weekly_challenge/add", methods=["POST"])
def add_challenge():
    admin_netid = request.args.get("netid")
    admin_password = request.args.get("password")
    if not check_admin_auth(admin_netid, admin_password):
        abort(403)
    data = request.get_json()
    problem = data.get("problem")
    test_cases = data.get("test_cases")
    title = data.get("title") or problem[:40]
    # Set solutions_available_date to 1 week from now if not provided
    solutions_available_date = data.get("solutions_available_date")
    if not solutions_available_date:
        solutions_available_date = (datetime.now(est) + timedelta(days=7)).strftime("%Y-%m-%d")
    active = data.get("active", False)  # New challenges default to inactive
    if not (problem and test_cases):
        return jsonify({"error": "Missing fields."}), 400
    challenge_id = str(uuid4())
    challenge = {
        "id": challenge_id,
        "problem": problem,
        "test_cases": test_cases,
        "title": title,
        "solutions_available_date": solutions_available_date,
        "active": active
    }
    if "examples" in data:
        challenge["examples"] = data["examples"]
    r.set(f"weekly_challenge:challenge:{challenge_id}", json.dumps(challenge))
    r.lpush("weekly_challenge:list", challenge_id)
    return jsonify({"success": True, "id": challenge_id})

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

@app.route("/weekly_challenge/edit/<cid>", methods=["POST"])
def edit_challenge(cid):
    admin_netid = request.args.get("netid")
    admin_password = request.args.get("password")
    if not check_admin_auth(admin_netid, admin_password):
        abort(403)
    raw = r.get(f"weekly_challenge:challenge:{cid}")
    if not raw:
        return jsonify({"error": "Challenge not found."}), 404
    challenge = json.loads(raw)
    data = request.get_json()
    # Update fields if present
    for field in ["title", "problem", "examples", "solutions_available_date"]:
        if field in data:
            challenge[field] = data[field]
    # Only update test_cases if present and not empty/null
    if "test_cases" in data and data["test_cases"]:
        challenge["test_cases"] = data["test_cases"]
    r.set(f"weekly_challenge:challenge:{cid}", json.dumps(challenge))
    return jsonify({"success": True, "challenge": challenge})

@app.route("/weekly_challenge/toggle_active/<cid>", methods=["POST"])
def toggle_challenge_active(cid):
    admin_netid = request.json.get("admin_netid")
    admin_password = request.json.get("admin_password")
    if not check_admin_auth(admin_netid, admin_password):
        return jsonify({"error": "Invalid admin credentials"}), 403
    raw = r.get(f"weekly_challenge:challenge:{cid}")
    if not raw:
        return jsonify({"error": "Challenge not found."}), 404
    challenge = json.loads(raw)
    challenge["active"] = not challenge.get("active", False)
    r.set(f"weekly_challenge:challenge:{cid}", json.dumps(challenge))
    return jsonify({"success": True, "active": challenge["active"]})

@app.route("/weekly_challenge/reorder", methods=["POST"])
def reorder_challenges():
    admin_netid = request.json.get("admin_netid")
    admin_password = request.json.get("admin_password")
    ids = request.json.get("ids")
    if not check_admin_auth(admin_netid, admin_password):
        return jsonify({"error": "Invalid admin credentials"}), 403
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        return jsonify({"error": "Invalid ids list"}), 400
    # Remove all and re-add in new order
    r.delete("weekly_challenge:list")
    for cid in reversed(ids):
        r.lpush("weekly_challenge:list", cid)
    return jsonify({"success": True})

# --- Code execution sandbox (updated for print output) ---
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
    # For now, get netid from query param or session (customize as needed)
    netid = request.args.get("netid") or flask_session.get("netid") or ""
    raw = r.get("weekly_challenge:current")
    challenge = json.loads(raw) if raw else None
    return render_template("weekly_challenge.html", netid=netid, challenge=challenge)

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

socketio.run(app, host="0.0.0.0", port=5000)
