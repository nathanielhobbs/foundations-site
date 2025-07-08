import os
import json
import redis
import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_ORG = os.getenv("GITHUB_ORG")

# Redis connection
r = redis.Redis(host="localhost", port=6379, decode_responses=True)

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

def fetch_notebooks(section_number):
    repo_name = f"foundations-notebooks-sec{int(section_number):02}"
    url = f"https://api.github.com/repos/{GITHUB_ORG}/{repo_name}/contents"

    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"❌ Could not access {repo_name}: {resp.status_code}")
        return []

    files = resp.json()
    notebooks = []
    for file in files:
        name = file["name"]
        if name.endswith(".ipynb"):
            title = name.replace("_", " ").replace(".ipynb", "").title()
            notebooks.append({
                "title": title,
                "github_path": f"{repo_name}/blob/main/{name}"
            })

    return notebooks

def sync_all_sections(max_sections=5):
    for sec in range(1, max_sections + 1):
        print(f"🔄 Syncing section {sec}...")
        notebooks = fetch_notebooks(sec)
        r.set(f"notebooks:section:{sec}", json.dumps(notebooks, indent=2))
        print(f"✅ Stored {len(notebooks)} notebooks in Redis for section {sec}")

if __name__ == "__main__":
    sync_all_sections()

