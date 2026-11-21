"""Read-only live-score probe for SportAPI.

Uses one date-fixtures request, reports status coverage, and never writes
production feeds, predictions, or caches.
"""
import json
from datetime import datetime, timezone

from sportapi_smoke_test import request_json


def summarize_live_fixtures(payload):
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("Fixture response was not a successful JSON object")
    fixtures = payload.get("data")
    if not isinstance(fixtures, list):
        raise ValueError("Fixture response did not contain a data list")

    status_counts = {}
    live = []
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            raise ValueError("Fixture record was not an object")
        status = fixture.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("Fixture record has no valid status")
        normalized = status.strip().upper()
        status_counts[normalized] = status_counts.get(normalized, 0) + 1
        if normalized == "LIVE":
            live.append({
                "fixture_id": fixture.get("id"),
                "competition": fixture.get("league_name"),
                "home": fixture.get("home_team"),
                "away": fixture.get("away_team"),
                "home_score": fixture.get("home_score"),
                "away_score": fixture.get("away_score"),
                "minute": fixture.get("minute"),
                "kickoff_utc": fixture.get("kickoff_utc"),
            })

    return {
        "fixtures_returned": len(fixtures),
        "status_counts": status_counts,
        "live_fixture_count": len(live),
        "live_fixtures": live[:30],
    }


def run_live_probe(api_key, today=None):
    if not isinstance(api_key, str) or not api_key.strip():
        raise RuntimeError("SPORTAPI_KEY is missing. Add it as a repository Actions secret.")
    today = today or datetime.now(timezone.utc).date()
    date_text = today.isoformat()
    payload, headers = request_json(f"/fixtures/date/{date_text}", api_key)
    report = summarize_live_fixtures(payload)
    report["provider"] = "SportAPI"
    report["date_checked_utc"] = date_text
    report["requests_used"] = 1
    report["authenticated"] = True
    report["daily_requests_remaining"] = headers.get("X-RateLimit-Remaining")
    report["monthly_requests_remaining"] = headers.get("X-RateLimit-Month-Remaining")
    return report


if __name__ == "__main__":
    import os
    result = run_live_probe(os.environ.get("SPORTAPI_KEY"))
    print(json.dumps(result, indent=2))
    print("Read-only live-score probe completed; production data was not changed.")
