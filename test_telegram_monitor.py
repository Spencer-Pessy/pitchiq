import unittest
from datetime import datetime, timezone
from telegram_monitor import build_snapshot, evaluate_workflow


class TelegramMonitorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)

    def run_row(self, hours_ago=1, event="schedule", status="completed", conclusion="success"):
        from datetime import timedelta
        created = self.now - timedelta(hours=hours_ago)
        return {
            "id": 123,
            "event": event,
            "status": status,
            "conclusion": conclusion,
            "created_at": created.isoformat(),
        }

    def test_recent_successful_scheduled_run_is_healthy(self):
        result = evaluate_workflow("telegram-news.yml", 4, 4, [self.run_row(7)], self.now)
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["age_minutes"], 420)

    def test_old_successful_news_run_is_stale_after_grace(self):
        result = evaluate_workflow("telegram-news.yml", 4, 4, [self.run_row(9)], self.now)
        self.assertEqual(result["status"], "stale")

    def test_manual_run_does_not_hide_missing_scheduled_run(self):
        result = evaluate_workflow(
            "telegram.yml", 24, 12,
            [self.run_row(0, event="workflow_dispatch")],
            self.now,
        )
        self.assertEqual(result["status"], "no_scheduled_runs")

    def test_failed_scheduled_run_is_failed_even_if_recent(self):
        result = evaluate_workflow(
            "telegram-results.yml", 1, 1,
            [self.run_row(0, conclusion="failure")],
            self.now,
        )
        self.assertEqual(result["status"], "failed")

    def test_in_progress_scheduled_run_is_running(self):
        result = evaluate_workflow(
            "telegram.yml", 24, 12,
            [self.run_row(0, status="in_progress", conclusion=None)],
            self.now,
        )
        self.assertEqual(result["status"], "running")

    def test_future_timestamp_is_not_reported_healthy(self):
        from datetime import timedelta
        future = self.now + timedelta(hours=1)
        row = self.run_row(0)
        row["created_at"] = future.isoformat()
        result = evaluate_workflow("telegram.yml", 24, 12, [row], self.now)
        self.assertEqual(result["status"], "invalid_timestamp")

    def test_snapshot_covers_all_three_publishers_without_claiming_delivery(self):
        runs = {
            "telegram.yml": [self.run_row(2)],
            "telegram-news.yml": [self.run_row(2)],
            "telegram-results.yml": [self.run_row(1)],
        }
        snapshot = build_snapshot(runs, self.now)
        self.assertEqual(len(snapshot["workflows"]), 3)
        self.assertEqual(snapshot["overall"], "healthy")
        self.assertIs(snapshot["telegram_delivery_verified"], False)
        self.assertIn("does not prove", snapshot["note"])

    def test_empty_snapshot_is_degraded_not_healthy(self):
        snapshot = build_snapshot({}, self.now)
        self.assertEqual(snapshot["overall"], "degraded")
        self.assertTrue(all(item["status"] == "no_scheduled_runs" for item in snapshot["workflows"]))


if __name__ == "__main__":
    unittest.main()
