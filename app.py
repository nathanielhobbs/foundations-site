import os
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, Response, abort#, redirect
from flask_socketio import SocketIO, emit, join_room
import redis
from datetime import datetime
import json
import re
from flask import session as flask_session

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'foundationsP4ss;'
app.config['ADMIN_PASSCODE'] = 'fnP4ssword;'  
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

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


def check_admin_access():
    code = request.args.get("code")
    if code != app.config['ADMIN_PASSCODE']:
        abort(403)

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
                messages.append(msg_obj)
            else:
                # fallback for malformed entries
                messages.append({
                    "netid": "unknown",
                    "msg": str(item),
                    "timestamp": "[old]",
                    "reply": None,
                    "edited": False
                })
        except json.JSONDecodeError:
            # fallback for old string messages
            messages.append({
                "netid": "unknown",
                "msg": item,
                "timestamp": "[old]",
                "reply": None,
                "edited": False
            })

    return render_template("chat.html", section=section, messages=messages)

@socketio.on("poll")
def handle_poll(data):
    section = data.get("section")
    question = data.get("question")
    options = data.get("options")
    netid = data.get("netid", "unknown")

    if not section or not question or not options or not isinstance(options, list):
        return

    timestamp = datetime.now().strftime("%H:%M")

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
        # Broadcast updated list to room
        participants = list(r.smembers(f"chat:participants:{section}"))
        socketio.emit("participants", {"section": section, "participants": participants}, to=section)
        # Also emit to the joining user directly
        emit("participants", {"section": section, "participants": participants})

@socketio.on("disconnect")
def on_disconnect():
    # Remove user from all participant sets (not perfect, but works for demo)
    netid = flask_session.get("netid") or "unknown"
    for key in r.keys("chat:participants:*"):
        r.srem(key, netid)
        section = key.split(":")[-1]
        participants = list(r.smembers(key))
        socketio.emit("participants", {"section": section, "participants": participants}, to=section)

@socketio.on("get_participants")
def handle_get_participants(data):
    section = data.get("section")
    if not section:
        return
    participants = list(r.smembers(f"chat:participants:{section}"))
    emit("participants", {"section": section, "participants": participants})

# Handle sending message to correct section
@socketio.on("message")
def handle_message(data):
    section = data.get("section")
    raw_msg = data.get("msg")
    netid = data.get("netid", "unknown")  # Get netid from data parameter
    reply = None
    if "|||reply|||" in raw_msg:
        raw_msg, reply = raw_msg.split("|||reply|||", 1)

    timestamp = datetime.now().strftime("%H:%M")
    today = datetime.now().strftime("%Y-%m-%d")

    # Track participation
    r.sadd(f"participation:{today}:{section}", netid)

    # Create structured message
    msg_obj = {
        "netid": netid,
        "msg": raw_msg.strip(),
        "timestamp": timestamp,
        "reply": reply,
        "edited": False
    }

    # Store JSON in Redis
    r.rpush(f"chat:{section}", json.dumps(msg_obj))

    # Send structured message to clients
    socketio.emit("message", msg_obj, to=section)

    
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
        return render_template("participation_search.html", query=None, results=None)

    keys = r.keys("participation:*:*")
    results = []

    for key in keys:
        try:
            _, date, section = key.split(":")
            section = int(section)
            if query in r.smembers(key):
                results.append((date, section))
        except ValueError:
            continue

    return render_template("participation_search.html", query=query, results=results)

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

@app.route("/")
def index():
    return render_template("index.html")

#@app.route("/chat")
#def chat():
#    return render_template("chat.html")

#@socketio.on("message")
#def handle_message(msg):
#    emit("message", msg, broadcast=True)

@app.route("/assignments")
def show_assignments():
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    url = f"https://api.github.com/orgs/{GITHUB_ORG}/repos"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        repos = response.json()

        for assignment in assignments:
            prefix = assignment['slug']
            matching_repos = [repo for repo in repos if repo.get('name', '').startswith(prefix)]
            assignment['count'] = len(matching_repos)
            assignment['repos'] = [
                {
                    "name": repo["name"],
                    "url": repo["html_url"],
                    "pushed_at": repo["pushed_at"]
                }
                for repo in matching_repos
            ]

        return render_template("assignments.html", assignments=assignments)

    except Exception as e:
        return f"<h2>Failed to load assignments</h2><pre>{e}</pre><p>Check GITHUB_TOKEN and GITHUB_ORG.</p>", 500


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

socketio.run(app, host="0.0.0.0", port=5000)
