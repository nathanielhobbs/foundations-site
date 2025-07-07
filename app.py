import os
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, Response, abort#, redirect
from flask_socketio import SocketIO, emit, join_room
import redis
from datetime import datetime

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
    messages = r.lrange(f"chat:{section}", 0, -1)
    return render_template("chat.html", section=section, messages=messages)

# When a user joins, assign them to a room
@socketio.on("join")
def on_join(data):
    section = data["section"]
    join_room(section)

# Handle sending message to correct section
@socketio.on("message")
def handle_message(data):
    section = data.get("section")
    msg = data.get("msg")
    today = datetime.now().strftime("%Y-%m-%d")

    # Extract NetID (before first colon)
    if ':' in msg:
        netid = msg.split(':')[0].strip()
        r.sadd(f"participation:{today}:{section}", netid)

    # Save message
    r.rpush(f"chat:{section}", msg)
    emit("message", msg, to=section)

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

    # Remove duplicates and sort
    entries = sorted(set(entries))

    html = f"""
    <h2>Participation Dashboard</h2>
    <p>
      <a href="/participation_csv_all?code={passcode}">Download all participation as CSV</a><br><br>
      <form action="/participation_search" method="get">
        <input type="hidden" name="code" value="{passcode}">
        Search NetID: <input name="netid" required>
        <input type="submit" value="Search">
      </form>
    </p>
    <ul>
    """

    for date, section in entries:
        html += f"""
        <li>
          {date} – Section {section}:
          <a href="/participation/{date}/{section}?code={passcode}">View</a> |
          <a href="/participation_csv/{date}/{section}?code={passcode}">CSV</a>
        </li>
        """

    html += "</ul>"
    return html

    
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
    check_admin_access()
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
