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
    if not isinstance(data, dict) or not isinstance(data.get("response"), list) or data.get("errors"):
        raise SystemExit(f"Aborting injury update for {d:%Y-%m-%d}: source request failed; previous injuries.json will be kept.")
    for x in data.get("response", []):
        items.append({
            "team": x["team"]["name"], "player": x["player"]["name"],
            "reason": x["player"].get("reason") or x["player"].get("type") or "",
            "date": x["fixture"]["date"],
        })

with open("injuries.json", "w") as f:
    json.dump({"updated": now.isoformat(), "items": items}, f, ensure_ascii=False)
print("injury entries:", len(items))
