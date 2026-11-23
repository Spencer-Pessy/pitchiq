"""Read-only GitHub Actions health monitor for PitchIQ Telegram publishers.

This records scheduled-run evidence only. It never calls Telegram or sends alerts.
"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPOSITORY = "Spencer-Pessy/pitchiq"
OUTPUT = Path("daily/telegram_health.json")
WORKFLOWS = (
    ("telegram.yml", 24, 2),
    ("telegram-news.yml", 4, 4),
    ("telegram-results.yml", 1, 3),
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


def evaluate_workflow(filename, interval_hours, grace_hours, runs, now=None):
    """Classify the latest scheduled execution; manual runs do not mask missed schedules."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    relevant = [
        run for run in runs
        if isinstance(run, dict) and run.get("event") in {"schedule", "workflow_run"}
    ]
    relevant.sort(
        key=lambda run: parse_timestamp(run.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    scheduled = [run for run in relevant if run.get("event") == "schedule"]
    latest_scheduled = scheduled[0] if scheduled else None
    if not relevant:
        return {
            "workflow": filename,
            "status": "no_qualifying_runs",
            "last_scheduled_run": None,
            "last_refresh_trigger_run": None,
            "last_execution": None,
            "age_minutes": None,
            "expected_interval_hours": interval_hours,
            "grace_hours": grace_hours,
        }

    latest = relevant[0]
    created = parse_timestamp(latest.get("created_at"))
    if created is None:
        status, age = "invalid_timestamp", None
    else:
        age = max(0, int((now.astimezone(timezone.utc) - created).total_seconds() // 60))
        if latest.get("status") in {"in_progress", "queued"}:
            status = "running"
        elif latest.get("conclusion") != "success":
            status = "failed"
        elif created > now.astimezone(timezone.utc) + timedelta(minutes=5):
            status = "invalid_timestamp"
        elif now.astimezone(timezone.utc) - created > timedelta(hours=interval_hours + grace_hours):
            status = "stale"
        else:
            status = "healthy"

    def run_summary(run):
        if run is None:
            return None
        return {
            "id": run.get("id"),
            "event": run.get("event"),
            "created_at": run.get("created_at"),
            "run_status": run.get("status"),
            "conclusion": run.get("conclusion"),
        }

    latest_refresh = next((run for run in relevant if run.get("event") == "workflow_run"), None)
    return {
        "workflow": filename,
        "status": status,
        "last_scheduled_run": run_summary(latest_scheduled),
        "last_refresh_trigger_run": run_summary(latest_refresh),
        "last_execution": run_summary(latest),
        "age_minutes": age,
        "expected_interval_hours": interval_hours,
        "grace_hours": grace_hours,
    }


def fetch_runs(filename, token, repository=REPOSITORY, opener=urllib.request.urlopen):
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required for read-only Actions monitoring.")
    url = (
        f"https://api.github.com/repos/{repository}/actions/workflows/"
        f"{filename}/runs?branch=main&per_page=30"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "PitchIQ-Actions-Monitor/1.0",
        },
    )
    with opener(request, timeout=25) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        raise RuntimeError(f"GitHub returned an invalid Actions response for {filename}.")
    return payload["workflow_runs"]


def build_snapshot(run_sets, now=None):
    now = now or datetime.now(timezone.utc)
    workflows = []
    for filename, interval, grace in WORKFLOWS:
        workflows.append(
            evaluate_workflow(filename, interval, grace, run_sets.get(filename, []), now=now)
        )
    overall = "healthy" if all(item["status"] == "healthy" for item in workflows) else "degraded"
    return {
        "schema_version": 1,
        "checked_at": now.astimezone(timezone.utc).isoformat(),
        "overall": overall,
        "telegram_delivery_verified": False,
        "note": "GitHub scheduled-run health only; this does not prove a Telegram message was delivered.",
        "workflows": workflows,
    }


def main():
    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY", REPOSITORY)
    run_sets = {
        filename: fetch_runs(filename, token, repository=repository)
        for filename, _interval, _grace in WORKFLOWS
    }
    snapshot = build_snapshot(run_sets)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in snapshot["workflows"]:
        print(
            f"{item['workflow']}: {item['status']} "
            f"(age_minutes={item['age_minutes']})"
        )
    print("Telegram delivery is not verified by this monitor.")


if __name__ == "__main__":
    main()
