"""Build a small, public live-score snapshot from SportAPI.

One request per scheduled run. API credentials stay in GitHub Actions and are
never exposed to the browser or committed to the repository. The scheduled
workflow also supports a push-triggered refresh for operational recovery.
"""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sportapi_smoke_test import request_json

ACTIVE_STATUSES = {"LIVE", "HT"}


def build_live_feed(payload, updated=None):
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("SportAPI fixture response was not successful")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("SportAPI fixture response did not contain a data list")

    live = []
    status_counts = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("SportAPI fixture record must be an object")
        status = row.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("SportAPI fixture record has no status")
        status = status.strip().upper()
        status_counts[status] = status_counts.get(status, 0) + 1
        minute = row.get("minute")
        if isinstance(minute, str) and minute.strip().upper() == "HT":
            status = "HT"
        if status not in ACTIVE_STATUSES:
            continue

        fixture_id = row.get("id")
        home, away = row.get("home_team"), row.get("away_team")
        kickoff = row.get("kickoff_utc")
        competition = row.get("league_name")
        if not isinstance(fixture_id, int) or isinstance(fixture_id, bool):
            raise ValueError("Live fixture has an invalid ID")
        if not all(isinstance(value, str) and value.strip()
                   for value in (home, away, kickoff, competition)):
            raise ValueError("Live fixture is missing team, competition, or kickoff data")
        try:
            parsed = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Live fixture has an invalid kickoff timestamp") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Live fixture kickoff must include a timezone")

        hs, aws = row.get("home_score"), row.get("away_score")
        score = None
        if (isinstance(hs, int) and not isinstance(hs, bool) and hs >= 0
                and isinstance(aws, int) and not isinstance(aws, bool) and aws >= 0):
            score = [hs, aws]
        live.append({
            "id": fixture_id,
            "comp": competition.strip(),
            "h": home.strip(),
            "a": away.strip(),
            "utc": parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": status,
            "minute": minute.strip() if isinstance(minute, str) else None,
            "score": score,
            "source": "SportAPI",
        })

    live.sort(key=lambda item: (item["utc"], item["comp"], item["h"], item["a"]))
    return {
        "provider": "SportAPI",
        "updated": (updated or datetime.now(timezone.utc)).isoformat(),
        "fixtures_returned": len(rows),
        "status_counts": status_counts,
        "active_statuses": sorted(ACTIVE_STATUSES),
        "count": len(live),
        "matches": live,
    }


def fetch_live_feed(api_key, today=None):
    if not isinstance(api_key, str) or not api_key.strip():
        raise RuntimeError("SPORTAPI_KEY is missing; add it as a repository Actions secret")
    today = today or datetime.now(timezone.utc).date()
    payload, headers = request_json(f"/fixtures/date/{today.isoformat()}", api_key)
    report = build_live_feed(payload)
    report["requests_used"] = 1
    report["daily_requests_remaining"] = headers.get("X-RateLimit-Remaining")
    report["monthly_requests_remaining"] = headers.get("X-RateLimit-Month-Remaining")
    return report


def write_live_feed(report, path="live.json"):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent,
                                     delete=False) as handle:
        json.dump(report, handle, ensure_ascii=False)
        temporary = handle.name
    os.replace(temporary, destination)


if __name__ == "__main__":
    result = fetch_live_feed(os.environ.get("SPORTAPI_KEY"))
    write_live_feed(result)
    print(json.dumps({
        "provider": result["provider"],
        "updated": result["updated"],
        "fixtures_returned": result["fixtures_returned"],
        "status_counts": result["status_counts"],
        "live_count": result["count"],
        "requests_used": result["requests_used"],
        "daily_requests_remaining": result.get("daily_requests_remaining"),
        "monthly_requests_remaining": result.get("monthly_requests_remaining"),
    }, indent=2))
