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


def fetch_fixtures(day):
    if not KEY:
        raise SystemExit("API_FOOTBALL_KEY is not configured; international.json was not changed.")

    query = urllib.parse.urlencode({"date": day})
    request = urllib.request.Request(
        f"{BASE}/fixtures?{query}",
        headers={"x-apisports-key": KEY},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        remaining = response.headers.get("x-ratelimit-requests-remaining", "unknown")
        data = json.load(response)

    if not isinstance(data, dict):
        raise SystemExit(f"International fixture source returned a non-object for {day}; last good file preserved.")
    rows = data.get("response")
    errors = data.get("errors")
    if not isinstance(rows, list) or errors:
        print("API-Football date:", day)
        print("API-Football errors:", json.dumps(errors, ensure_ascii=False)[:1200])
        print("API-Football response type:", type(rows).__name__)
        raise SystemExit("International fixture source returned an invalid response; last good file preserved.")
    paging = data.get("paging") or {}
    if int(paging.get("total", 1) or 1) > 1:
        raise SystemExit(f"International fixture response for {day} is paginated; refusing an incomplete snapshot.")
    return rows, remaining


def normalize_fixture(item):
    if not isinstance(item, dict) or not is_international_fixture(item):
        return None
    fixture = item.get("fixture") or {}
    league = item.get("league") or {}
    teams = item.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    goals = item.get("goals") or {}
    if not fixture.get("id") or not fixture.get("date") or not home.get("name") or not away.get("name"):
        return None
    score = None
    if goals.get("home") is not None and goals.get("away") is not None:
        score = [goals["home"], goals["away"]]
    status = (fixture.get("status") or {}).get("short") or "TBD"
    return {
        "id": fixture["id"],
        "comp": league.get("name") or "International",
        "country": league.get("country") or "",
        "utc": fixture["date"],
        "status": status,
        "h": home["name"],
        "a": away["name"],
        "score": score,
        "venue": (fixture.get("venue") or {}).get("name") or "",
    }


def main():
    now = datetime.now(timezone.utc)
    days = [(now.date() + timedelta(days=offset)).isoformat() for offset in (-1, 0, 1)]
    fixtures = []
    remaining = "unknown"
    for day in days:
        rows, remaining = fetch_fixtures(day)
        fixtures.extend(x for x in (normalize_fixture(row) for row in rows) if x)
    unique = {str(f["id"]): f for f in fixtures}
    fixtures = sorted(unique.values(), key=lambda f: f["utc"])
    payload = {
        "updated": now.isoformat(),
        "source": "API-Football",
        "range": {"from": days[0], "to": days[-1]},
        "requests_used": len(days),
        "requests_remaining": remaining,
        "fixtures": fixtures,
    }
    with open("international.json", "w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False)
    print("national-team fixtures stored:", len(fixtures))
    print("fixture dates queried:", len(days), "requests; API-Football requests left today:", remaining)


if __name__ == "__main__":
    main()
