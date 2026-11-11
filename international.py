"""Fetch national-team fixtures from API-Football's free fixtures endpoint.

This feed is intentionally fixtures-only. PitchIQ does not generate a forecast
until it has a defensible international-team history dataset.
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

from pitchiq_data import is_international_fixture

KEY = os.environ.get("API_FOOTBALL_KEY")
BASE = "https://v3.football.api-sports.io"


def fetch_fixtures(start_date, end_date):
    if not KEY:
        raise SystemExit("API_FOOTBALL_KEY is not configured; international.json was not changed.")

    query = urllib.parse.urlencode({"from": start_date, "to": end_date})
    request = urllib.request.Request(
        f"{BASE}/fixtures?{query}",
        headers={"x-apisports-key": KEY},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        print("API-Football requests left today:",
              response.headers.get("x-ratelimit-requests-remaining", "unknown"))
        data = json.load(response)

    if not isinstance(data, dict):
        print("API-Football returned a non-object response:", type(data).__name__)
        raise SystemExit("International fixture source returned an invalid response; last good file preserved.")
    response = data.get("response")
    errors = data.get("errors")
    if not isinstance(response, list) or errors:
        print("API-Football response keys:", sorted(data.keys()))
        print("API-Football errors:", json.dumps(errors, ensure_ascii=False)[:1200])
        print("API-Football response type:", type(response).__name__)
        raise SystemExit("International fixture source returned an invalid response; last good file preserved.")
    paging = data.get("paging") or {}
    if int(paging.get("total", 1) or 1) > 1:
        raise SystemExit("International fixture response is paginated; refusing to publish an incomplete first page.")

    fixtures = []
    for item in data["response"]:
        if not isinstance(item, dict) or not is_international_fixture(item):
            continue
        fixture = item.get("fixture") or {}
        league = item.get("league") or {}
        teams = item.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        goals = item.get("goals") or {}
        if not fixture.get("id") or not fixture.get("date") or not home.get("name") or not away.get("name"):
            continue
        score = None
        if goals.get("home") is not None and goals.get("away") is not None:
            score = [goals["home"], goals["away"]]
        status = (fixture.get("status") or {}).get("short") or "TBD"
        fixtures.append({
            "id": fixture["id"],
            "comp": league.get("name") or "International",
            "country": league.get("country") or "",
            "utc": fixture["date"],
            "status": status,
            "h": home["name"],
            "a": away["name"],
            "score": score,
            "venue": (fixture.get("venue") or {}).get("name") or "",
        })

    unique = {str(f["id"]): f for f in fixtures}
    return sorted(unique.values(), key=lambda f: f["utc"])


def main():
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=1)).date().isoformat()
    end = (now + timedelta(days=7)).date().isoformat()
    fixtures = fetch_fixtures(start, end)
    payload = {
        "updated": now.isoformat(),
        "source": "API-Football",
        "range": {"from": start, "to": end},
        "fixtures": fixtures,
    }
    with open("international.json", "w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False)
    print("national-team fixtures stored:", len(fixtures))


if __name__ == "__main__":
    main()
