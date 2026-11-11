import json, os, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone

from pitchiq_odds import active_sport_keys, market_events, require_nonempty_snapshot

KEY = os.environ["ODDS_API_KEY"]
BASE = "https://api.the-odds-api.com/v4"
WANT = ["soccer_epl", "soccer_spain_la_liga", "soccer_italy_serie_a",
        "soccer_germany_bundesliga", "soccer_france_ligue_one", "soccer_uefa_champs_league"]


def get(path, **q):
    q["apiKey"] = KEY
    url = BASE + path + "?" + urllib.parse.urlencode(q)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            print("credits remaining:", r.headers.get("x-requests-remaining"))
            return json.load(r)
    except urllib.error.HTTPError as e:
        print("error", path, e.code)
    except Exception as e:
        print("error", path, e)
    return None


sports = get("/sports")
try:
    active = active_sport_keys(sports)
except ValueError as error:
    raise SystemExit(f"Aborting odds update: invalid sports response ({error}); previous odds.json will be kept.")

events = []
for sk in WANT:
    if sk not in active:
        print("skipping", sk)
        continue
    data = get(f"/sports/{sk}/odds", regions="eu", markets="h2h", oddsFormat="decimal")
    try:
        events.extend(market_events(data))
    except ValueError as error:
        raise SystemExit(f"Aborting odds update: invalid {sk} odds response ({error}); previous odds.json will be kept.")

snapshot = {"updated": datetime.now(timezone.utc).isoformat(), "events": events}
with open("odds.json", "w", encoding="utf-8") as f:
    json.dump(snapshot, f, ensure_ascii=False)
print("events with odds:", len(events))
