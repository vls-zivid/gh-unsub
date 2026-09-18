import argparse
import os
import requests, yaml

with open("token") as f:
    TOKEN = f.read().strip()

API = "https://api.github.com"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}

# whitelist file: {repos: ["org/repo"], reasons: ["mention","review_requested"]}
WHITELIST_PATHS = ("whitelist.yml", "whitelist.yaml")

def load_whitelist():
    for path in WHITELIST_PATHS:
        if os.path.exists(path):
            with open(path) as f:
                return yaml.safe_load(f) or {}
    raise FileNotFoundError(f"None of {WHITELIST_PATHS} found")

whitelist = load_whitelist()

def is_whitelisted(n):
    repo = n["repository"]["full_name"]
    reason = n["reason"]
    return (repo in whitelist.get("repos", [])
            or reason in whitelist.get("reasons", [])
            or n["id"] in whitelist.get("thread_ids", []))

def fetch_notifications():
    notifications = []
    url = f"{API}/notifications"
    params = {"all": "true", "per_page": 100}
    while url:
        r = requests.get(url, headers=HEADERS, params=params)
        r.raise_for_status()
        notifications.extend(r.json())
        url = r.links.get("next", {}).get("url")
        params = None
    return notifications

def run(dry_run=False):
    notifications = fetch_notifications()
    for n in notifications:
        if is_whitelisted(n):
            continue
        tid = n["id"]
        label = f"{n['repository']['full_name']} - {n['subject']['title']}"
        if dry_run:
            print(f"Would unsubscribe: {label}")
            continue
        put = requests.put(f"{API}/notifications/threads/{tid}/subscription",
                            headers=HEADERS, json={"ignored": True})
        if put.ok:
            print(f"Unsubscribed: {label}")
        else:
            print(f"Failed to unsubscribe ({put.status_code}): {label}")
    print(f"\n{len(notifications)} notification(s) checked.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                         help="Show what would be unsubscribed without changing anything")
    args = parser.parse_args()
    run(dry_run=args.dry_run)