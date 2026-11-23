import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from pipeline_watchdog import recovery_decision, run_watchdog, snapshot_status


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8") if self.payload else b""


class PipelineWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 23, 20, 0, tzinfo=timezone.utc)

    def run_row(self, minutes_ago=1, event="schedule", status="completed"):
        return {
            "event": event,
            "status": status,
            "created_at": (self.now - timedelta(minutes=minutes_ago)).isoformat(),
        }

    def test_snapshot_is_fresh_within_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text(json.dumps({"updated": (self.now - timedelta(minutes=89)).isoformat()}))
            self.assertEqual(snapshot_status(path, self.now, 90)["status"], "fresh")

    def test_snapshot_is_stale_after_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "live.json"
            path.write_text(json.dumps({"updated": (self.now - timedelta(minutes=21)).isoformat()}))
            self.assertEqual(snapshot_status(path, self.now, 20)["status"], "stale")

    def test_missing_or_invalid_snapshot_is_not_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(snapshot_status(Path(directory) / "missing.json", self.now, 20)["status"],
                             "missing_or_invalid")

    def test_active_refresh_prevents_duplicate_dispatch(self):
        self.assertEqual(recovery_decision([self.run_row(status="in_progress")], self.now, 15),
                         "already_running")

    def test_recent_manual_recovery_obeys_cooldown(self):
        self.assertEqual(recovery_decision([self.run_row(5, event="workflow_dispatch")],
                                           self.now, 15), "cooldown")

    def test_old_manual_recovery_can_be_retried(self):
        self.assertEqual(recovery_decision([self.run_row(30, event="workflow_dispatch")],
                                           self.now, 15), "dispatch")

    def test_stale_feeds_dispatch_only_their_own_workflows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.json").write_text(json.dumps({
                "updated": (self.now - timedelta(hours=3)).isoformat()
            }))
            (root / "live.json").write_text(json.dumps({
                "updated": (self.now - timedelta(minutes=5)).isoformat()
            }))
            calls = []
            def opener(request, timeout=25):
                calls.append((request.full_url, request.get_method(), request.data))
                if request.get_method() == "GET":
                    return FakeResponse({"workflow_runs": [self.run_row(200)]})
                return FakeResponse()
            result = run_watchdog("token", root=root, now=self.now, opener=opener)
            self.assertEqual(result["feeds"][0]["recovery"], "dispatched")
            self.assertEqual(result["feeds"][1]["recovery"], "not_needed")
            self.assertEqual(len(calls), 2)
            self.assertIn("update.yml/dispatches", calls[1][0])
            self.assertEqual(json.loads(calls[1][2]), {"ref": "main"})

    def test_stale_live_feed_dispatches_live_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.json").write_text(json.dumps({
                "updated": (self.now - timedelta(minutes=10)).isoformat()
            }))
            (root / "live.json").write_text(json.dumps({
                "updated": (self.now - timedelta(minutes=45)).isoformat()
            }))
            calls = []
            def opener(request, timeout=25):
                calls.append((request.full_url, request.get_method()))
                return FakeResponse({"workflow_runs": []}) if request.get_method() == "GET" else FakeResponse()
            result = run_watchdog("token", root=root, now=self.now, opener=opener)
            self.assertEqual(result["feeds"][0]["recovery"], "not_needed")
            self.assertEqual(result["feeds"][1]["recovery"], "dispatched")
            self.assertTrue(any("live-scores.yml/dispatches" in url for url, method in calls))

    def test_active_or_recent_dispatch_does_not_create_extra_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("data.json", "live.json"):
                (root / name).write_text(json.dumps({
                    "updated": (self.now - timedelta(days=1)).isoformat()
                }))
            def opener(request, timeout=25):
                if request.get_method() == "GET":
                    return FakeResponse({"workflow_runs": [self.run_row(3, event="workflow_dispatch")]})
                self.fail("No new dispatch should be made during cooldown")
            result = run_watchdog("token", root=root, now=self.now, opener=opener)
            self.assertEqual([x["recovery"] for x in result["feeds"]], ["cooldown", "cooldown"])

    def test_watchdog_has_its_own_schedule_and_manual_dispatch(self):
        workflow = Path(".github/workflows/pipeline-watchdog.yml").read_text()
        self.assertIn('cron: "*/10 * * * *"', workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("actions: write", workflow)
        self.assertIn("pipeline_watchdog.py", workflow)
        self.assertIn("test_pipeline_watchdog.py", workflow)
        self.assertNotIn("workflow_run:", workflow)

    def test_refresh_workflows_explicitly_dispatch_watchdog_after_success(self):
        update = Path(".github/workflows/update.yml").read_text()
        live = Path(".github/workflows/live-scores.yml").read_text()
        self.assertIn("actions: write", update)
        self.assertIn("actions: write", live)
        self.assertIn("gh workflow run pipeline-watchdog.yml --ref main", update)
        self.assertIn("gh workflow run pipeline-watchdog.yml --ref main", live)
        self.assertNotIn("workflow_run:", live)

    def test_live_score_publication_retries_without_spending_extra_provider_requests(self):
        live = Path(".github/workflows/live-scores.yml").read_text()
        self.assertIn("python sportapi_live_feed.py", live)
        self.assertIn("cp live.json /tmp/pitchiq-live.json", live)
        self.assertIn("for attempt in 1 2 3", live)
        self.assertIn("git fetch origin main", live)


if __name__ == "__main__":
    unittest.main()
