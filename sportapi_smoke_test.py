"""Low-volume, read-only SportAPI credential and coverage probe.

This script is only run manually from GitHub Actions. It never writes provider
data into the production feed and never prints the API key or raw responses.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://sportapi.ai/api"


def validate_success_payload(payload, endpoint):
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError(f"{endpoint}: response was not a successful JSON object")
    return payload


def request_json(path, api_key):
    request = Request(
        BASE_URL + path,
        headers={"X-Api-Key": api_key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return validate_success_payload(payload, path), response.headers
    except HTTPError as exc:
        # Do not print response bodies: provider errors must never echo secrets.
        raise RuntimeError(f"{path}: HTTP {exc.code}") from None
    except URLError:
        raise RuntimeError(f"{path}: network connection failed") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError(f"{path}: response was not valid JSON") from None


def select_upcoming_fixtures(fixtures, now=None, limit=3):
    """Choose a small, diverse set of genuinely upcoming scheduled fixtures."""
    now = now or datetime.now(timezone.utc)
    candidates = []
    seen_leagues = set()
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            continue
        if str(fixture.get("status", "")).upper() not in ("SCHEDULED", "TIMED"):
            continue
        fixture_id = fixture.get("id")
        league_id = fixture.get("league_id")
        kickoff = fixture.get("kickoff_utc") or fixture.get("utcDate")
        if not isinstance(fixture_id, int) or league_id is None or not isinstance(kickoff, str):
            continue
        try:
            kickoff_at = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        except ValueError:
            continue
        if kickoff_at.tzinfo is None or kickoff_at <= now:
            continue
        candidates.append((kickoff_at, fixture))
    candidates.sort(key=lambda item: item[0])
    selected = []
    for kickoff_at, fixture in candidates:
        league_id = fixture.get("league_id")
        if league_id in seen_leagues:
            continue
        seen_leagues.add(league_id)
        selected.append((kickoff_at, fixture))
        if len(selected) >= limit:
            break
    return selected


def run_probe(api_key, today=None, now=None):
    if not isinstance(api_key, str) or not api_key.strip():
        raise RuntimeError("SPORTAPI_KEY is missing. Add it as a repository Actions secret.")
    today = today or datetime.now(timezone.utc).date()
    now = now or datetime.now(timezone.utc)
    summary = {"provider": "SportAPI", "authenticated": False, "requests": 0}
    latest_headers = {}

    leagues, latest_headers = request_json("/leagues", api_key)
    summary["requests"] += 1
    if not isinstance(leagues.get("data"), list):
        raise RuntimeError("/leagues: expected a data list")
    summary["authenticated"] = True
    summary["league_records_returned"] = len(leagues["data"])

    fixtures = []
    dates_checked = []
    for offset in (0, 1):
        date_text = (today + timedelta(days=offset)).isoformat()
        payload, latest_headers = request_json(f"/fixtures/date/{date_text}", api_key)
        summary["requests"] += 1
        if not isinstance(payload.get("data"), list):
            raise RuntimeError(f"/fixtures/date/{date_text}: expected a data list")
        dates_checked.append(date_text)
        fixtures.extend(payload["data"])

    summary["fixture_dates_checked"] = dates_checked
    summary["fixtures_returned"] = len(fixtures)

    upcoming = select_upcoming_fixtures(fixtures, now=now, limit=3)
    lineup_checks = []
    for kickoff_at, fixture in upcoming:
        lineups, latest_headers = request_json(
            f"/fixtures/{fixture['id']}/lineups", api_key
        )
        summary["requests"] += 1
        lineup_checks.append({
            "fixture_id": fixture["id"],
            "competition": fixture.get("league_name"),
            "kickoff_utc": kickoff_at.isoformat(),
            "lineups_available": lineups.get("available") is True,
        })
    summary["upcoming_lineup_checks"] = lineup_checks
    summary["upcoming_lineups_available"] = sum(
        item["lineups_available"] for item in lineup_checks
    )

    # Keep one small statistics endpoint check, separate from the pre-match XI checks.
    candidate = next(
        (
            fixture for fixture in fixtures
            if isinstance(fixture, dict)
            and isinstance(fixture.get("id"), int)
        ),
        None,
    )
    if candidate is not None:
        stats, latest_headers = request_json(
            f"/fixtures/{candidate['id']}/stats", api_key
        )
        summary["requests"] += 1
        summary["sample_stats_fixture_id"] = candidate["id"]
        summary["stats_endpoint_ok"] = True
        summary["stats_available"] = stats.get("available") is True
    else:
        summary["stats_endpoint_note"] = "No fixture was returned for the dates checked."

    for header, output in (
        ("X-RateLimit-Remaining", "daily_requests_remaining"),
        ("X-RateLimit-Month-Remaining", "monthly_requests_remaining"),
    ):
        value = latest_headers.get(header)
        if value is not None:
            summary[output] = value

    return summary

if __name__ == "__main__":
    try:
        result = run_probe(os.environ.get("SPORTAPI_KEY"))
        print(json.dumps(result, indent=2))
        print("SportAPI smoke test completed. No production data or prediction records were changed.")
    except Exception as error:
        print(f"SportAPI smoke test failed: {error}", file=sys.stderr)
        sys.exit(1)
