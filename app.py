import os
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, Response, abort#, redirect
from flask_socketio import SocketIO, emit, join_room
import redis
from datetime import datetime
import json

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
    join_room(section)

# Handle sending message to correct section
@socketio.on("message")
def handle_message(data):
    section = data.get("section")
    raw_msg = data.get("msg")
    reply = None
    if "|||reply|||" in raw_msg:
        raw_msg, reply = raw_msg.split("|||reply|||", 1)

    timestamp = datetime.now().strftime("%H:%M")
    today = datetime.now().strftime("%Y-%m-%d")

    # Extract netid from start of msg
    netid = raw_msg.split(":")[0].strip() if ":" in raw_msg else "unknown"

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
        return "<form><input name='netid' placeholder='Enter NetID'><input type='submit'></form>"

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

    if not results:
        return f"<p>No participation found for <b>{query}</b>.</p>"

    html = f"<h3>Participation for {query}</h3><ul>"
    for date, section in sorted(results):
        html += f"<li>{date} — Section {section}</li>"
    html += "</ul>"
    return html


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
    repos = requests.get(f"https://api.github.com/orgs/{GITHUB_ORG}/repos", headers=headers).json()

    for assignment in assignments:
        prefix = assignment['slug']
        matching_repos = [repo for repo in repos if repo['name'].startswith(prefix)]
        assignment['count'] = len(matching_repos)
        assignment['repos'] = [{"name": repo["name"], "url": repo["html_url"], "pushed_at": repo["pushed_at"]} for repo in matching_repos]

    return render_template("assignments.html", assignments=assignments)

socketio.run(app, host="0.0.0.0", port=5000)
