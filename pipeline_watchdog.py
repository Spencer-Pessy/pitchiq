"""Watch published PitchIQ snapshots and dispatch recovery refreshes when stale.

This is a small, quota-free GitHub Actions watchdog. It reads only the timestamps
already committed to the repository and uses the GitHub API to dispatch the
existing refresh workflows. It never calls football-data or SportAPI itself.
"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPOSITORY = "Spencer-Pessy/pitchiq"
CHECKS = (
    {"name": "club_data", "path": "data.json", "workflow": "update.yml",
     "max_age_minutes": 90, "cooldown_minutes": 20},
    {"name": "live_scores", "path": "live.json", "workflow": "live-scores.yml",
     "max_age_minutes": 20, "cooldown_minutes": 15},
)


def parse_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def snapshot_status(path, now, max_age_minutes):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"status": "missing_or_invalid", "updated": None, "age_minutes": None}
    updated = parse_timestamp(payload.get("updated"))
    if updated is None:
        return {"status": "missing_or_invalid", "updated": None, "age_minutes": None}
    age = int((now - updated).total_seconds() // 60)
    if age < -5:
        return {"status": "future_timestamp", "updated": updated.isoformat(), "age_minutes": age}
    if age > max_age_minutes:
        status = "stale"
    else:
        status = "fresh"
    return {"status": status, "updated": updated.isoformat(), "age_minutes": max(0, age)}


def github_request(url, token, method="GET", body=None, opener=urllib.request.urlopen):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "PitchIQ-Pipeline-Watchdog/1.0",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, headers=headers, data=data, method=method)
    try:
        with opener(request, timeout=25) as response:
            raw = response.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"GitHub API request failed with HTTP {error.code}") from None
    except urllib.error.URLError:
        raise RuntimeError("GitHub API network request failed") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("GitHub API returned invalid JSON") from None


def recovery_decision(runs, now, cooldown_minutes):
    """Do not duplicate a queued/running recovery or hammer a recently dispatched job."""
    valid = [run for run in runs if isinstance(run, dict)]
    for run in valid:
        if run.get("status") in {"queued", "in_progress"}:
            return "already_running"
    recent_dispatches = []
    for run in valid:
        if run.get("event") != "workflow_dispatch":
            continue
        created = parse_timestamp(run.get("created_at"))
        if created and timedelta(0) <= now - created <= timedelta(minutes=cooldown_minutes):
            recent_dispatches.append(created)
    return "cooldown" if recent_dispatches else "dispatch"


def run_watchdog(token, repository=REPOSITORY, root=".", now=None, opener=urllib.request.urlopen):
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required for the pipeline watchdog.")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    report = {"checked_at": now.astimezone(timezone.utc).isoformat(), "feeds": []}
    for check in CHECKS:
        snapshot = snapshot_status(Path(root) / check["path"], now, check["max_age_minutes"])
        item = {**check, **snapshot, "recovery": "not_needed"}
        if snapshot["status"] != "fresh":
            runs_url = (
                f"https://api.github.com/repos/{repository}/actions/workflows/"
                f"{check['workflow']}/runs?branch=main&per_page=20"
            )
            runs_payload = github_request(runs_url, token, opener=opener)
            runs = runs_payload.get("workflow_runs")
            if not isinstance(runs, list):
                raise RuntimeError(f"GitHub returned invalid workflow runs for {check['workflow']}.")
            decision = recovery_decision(runs, now, check["cooldown_minutes"])
            if decision == "dispatch":
                dispatch_url = (
                    f"https://api.github.com/repos/{repository}/actions/workflows/"
                    f"{check['workflow']}/dispatches"
                )
                github_request(dispatch_url, token, method="POST",
                               body={"ref": "main"}, opener=opener)
                item["recovery"] = "dispatched"
            else:
                item["recovery"] = decision
        report["feeds"].append(item)
        print(
            f"{check['name']}: {snapshot['status']} "
            f"(age_minutes={snapshot['age_minutes']}, recovery={item['recovery']})"
        )
    return report


if __name__ == "__main__":
    result = run_watchdog(
        os.environ.get("GITHUB_TOKEN"),
        repository=os.environ.get("GITHUB_REPOSITORY", REPOSITORY),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
