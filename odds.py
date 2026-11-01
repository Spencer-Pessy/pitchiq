import json, os, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone

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


def avg(l):
    return round(sum(l) / len(l), 2)


active = {s["key"] for s in (get("/sports") or []) if s.get("active")}
events = []
for sk in WANT:
    if sk not in active:
        print("skipping", sk)
        continue
    for ev in get(f"/sports/{sk}/odds", regions="eu", markets="h2h", oddsFormat="decimal") or []:
        prices = {}
        for b in ev.get("bookmakers", []):
            for mk in b.get("markets", []):
                if mk["key"] == "h2h":
                    for o in mk["outcomes"]:
                        prices.setdefault(o["name"], []).append(o["price"])
        h, a, d = prices.get(ev["home_team"]), prices.get(ev["away_team"]), prices.get("Draw")
        if h and a and d:
            events.append({"home": ev["home_team"], "away": ev["away_team"],
                           "commence": ev["commence_time"], "odds": [avg(h), avg(d), avg(a)]})

with open("odds.json", "w") as f:
    json.dump({"updated": datetime.now(timezone.utc).isoformat(), "events": events}, f, ensure_ascii=False)
print("events with odds:", len(events))
