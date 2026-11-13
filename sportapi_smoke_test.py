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


def inspect_h2h_payload(payload, team1, team2):
    """Validate team identity and report score coverage without assuming every row is scored."""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("H2H: response was not a successful JSON object")
    records = payload.get("data")
    if not isinstance(records, list):
        raise ValueError("H2H: expected a data list")
    scored, unscored, score_types, statuses = [], 0, set(), {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("H2H: record was not an object")
        home_id, away_id = record.get("home_id"), record.get("away_id")
        if not isinstance(home_id, int) or not isinstance(away_id, int):
            raise ValueError("H2H: record missing numeric team IDs")
        if {home_id, away_id} != {team1, team2}:
            raise ValueError("H2H: record contains a different team pairing")
        if not isinstance(record.get("date"), str):
            raise ValueError("H2H: record missing match date")
        status = record.get("status")
        if not isinstance(status, str):
            raise ValueError("H2H: record missing status")
        statuses[status] = statuses.get(status, 0) + 1
        hs, aws = record.get("home_score"), record.get("away_score")
        score_types.add(type(hs).__name__ + "/" + type(aws).__name__)
        if status.upper() in ("FT", "AET", "PENS") and type(hs) is int and type(aws) is int:
            scored.append(record)
        else:
            unscored += 1
    return {"records": records, "scored_records": scored, "unscored_records": unscored,
            "score_field_types": sorted(score_types), "status_counts": statuses}


def select_h2h_fixtures(upcoming, limit=3):
    """Choose a small set of unique, valid team pairs for H2H coverage sampling."""
    selected, seen_pairs = [], set()
    for _, fixture in upcoming:
        if not isinstance(fixture, dict):
            continue
        home_id, away_id = fixture.get("home_id"), fixture.get("away_id")
        if not isinstance(home_id, int) or not isinstance(away_id, int) or home_id == away_id:
            continue
        pair = tuple(sorted((home_id, away_id)))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        selected.append(fixture)
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

    # Sample up to three unique H2H pairs; this is validation, not production enrichment.
    h2h_fixtures = select_h2h_fixtures(upcoming, limit=3)
    h2h_checks = []
    for h2h_fixture in h2h_fixtures:
        home_id, away_id = h2h_fixture["home_id"], h2h_fixture["away_id"]
        h2h_payload, latest_headers = request_json(
            f"/fixtures/h2h/{home_id}/{away_id}", api_key
        )
        summary["requests"] += 1
        h2h_report = inspect_h2h_payload(h2h_payload, home_id, away_id)
        h2h_checks.append({
            "fixture_id": h2h_fixture["id"],
            "team_pair": [h2h_fixture.get("home_team"), h2h_fixture.get("away_team")],
            "meetings_returned": len(h2h_report["records"]),
            "scored_meetings": len(h2h_report["scored_records"]),
            "unscored_meetings": h2h_report["unscored_records"],
            "score_field_types": h2h_report["score_field_types"],
            "status_counts": h2h_report["status_counts"],
            "history_available": bool(h2h_report["records"]),
        })
    summary["h2h_endpoint_ok"] = bool(h2h_checks)
    summary["h2h_pairs_checked"] = len(h2h_checks)
    summary["h2h_pair_checks"] = h2h_checks
    summary["h2h_meetings_returned"] = sum(
        item["meetings_returned"] for item in h2h_checks
    )
    summary["h2h_scored_meetings"] = sum(
        item["scored_meetings"] for item in h2h_checks
    )
    summary["h2h_unscored_meetings"] = sum(
        item["unscored_meetings"] for item in h2h_checks
    )
    if not h2h_checks:
        summary["h2h_endpoint_note"] = (
            "No upcoming fixtures with valid provider team IDs were available."
        )

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
