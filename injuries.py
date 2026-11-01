import json, os, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

KEY = os.environ["API_FOOTBALL_KEY"]
BASE = "https://v3.football.api-sports.io"


def get(path):
    req = urllib.request.Request(BASE + path, headers={"x-apisports-key": KEY})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("requests left today:", r.headers.get("x-ratelimit-requests-remaining"))
            return json.load(r)
    except urllib.error.HTTPError as e:
        print("error", path, e.code)
    except Exception as e:
        print("error", path, e)
    return None


now = datetime.now(timezone.utc)
items = []
for d in (now, now + timedelta(days=1)):
    data = get("/injuries?date=" + d.strftime("%Y-%m-%d"))
    if not data:
        continue
    if data.get("errors"):
        print("API says:", data["errors"])
    for x in data.get("response", []):
        items.append({
            "team": x["team"]["name"], "player": x["player"]["name"],
            "reason": x["player"].get("reason") or x["player"].get("type") or "",
            "date": x["fixture"]["date"],
        })

with open("injuries.json", "w") as f:
    json.dump({"updated": now.isoformat(), "items": items}, f, ensure_ascii=False)
print("injury entries:", len(items))
