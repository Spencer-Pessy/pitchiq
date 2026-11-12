from pathlib import Path
"""Tests for Telegram input validation."""
import unittest
from pitchiq_telegram import (parse_kickoff, valid_probabilities, valid_forecast, valid_final, clean_seen_urls,
                              snapshot_published_pick, clean_pick_state, resolve_published_picks, pick_label)


class TelegramValidationTests(unittest.TestCase):
    def test_timezone_aware_kickoff_only(self):
        self.assertIsNotNone(parse_kickoff("2026-11-12T19:00:00Z"))
        self.assertIsNotNone(parse_kickoff("2026-11-12T19:00:00+03:00"))
        self.assertIsNone(parse_kickoff("2026-11-12T19:00:00"))
        self.assertIsNone(parse_kickoff("not-a-date"))
        self.assertIsNone(parse_kickoff(None))

    def test_probabilities_must_be_numeric_bounded_and_normalized(self):
        self.assertTrue(valid_probabilities({"ph": 0.5, "pd": 0.25, "pa": 0.25}))
        self.assertTrue(valid_probabilities({"ph": 0.5001, "pd": 0.2499, "pa": 0.25}))
        self.assertFalse(valid_probabilities({"ph": 0.5, "pd": 0.2, "pa": 0.1}))
        self.assertFalse(valid_probabilities({"ph": 1.1, "pd": 0, "pa": 0}))
        self.assertFalse(valid_probabilities({"ph": True, "pd": 0, "pa": 0}))
        self.assertFalse(valid_probabilities(None))

    def test_forecast_requires_publishable_fields(self):
        good = {"h": "Home", "a": "Away", "comp": "League",
                "utc": "2026-11-12T19:00:00Z",
                "p": {"ph": 0.5, "pd": 0.25, "pa": 0.25}}
        self.assertTrue(valid_forecast(good))
        for change in ({"h": ""}, {"utc": "2026-11-12T19:00:00"},
                       {"p": {"ph": 0.5, "pd": 0.2, "pa": 0.1}}):
            row = dict(good)
            row.update(change)
            self.assertFalse(valid_forecast(row))
        self.assertFalse(valid_forecast(None))

    def test_seen_history_is_sanitized_and_bounded(self):
        self.assertEqual(clean_seen_urls({"bad": "shape"}), [])
        self.assertEqual(clean_seen_urls([" https://a ", None, "", 3, "https://b"]),
                         ["https://a", "https://b"])
        self.assertEqual(clean_seen_urls([str(i) for i in range(205)]),
                         [str(i) for i in range(5, 205)])

    def test_final_score_requires_two_nonnegative_integers(self):
        self.assertTrue(valid_final([0, 0]))
        self.assertTrue(valid_final([3, 2]))
        self.assertFalse(valid_final([1]))
        self.assertFalse(valid_final([1, -1]))
        self.assertFalse(valid_final([1, 2.5]))
        self.assertFalse(valid_final([True, 0]))


    def test_published_pick_snapshot_requires_a_stable_fixture_id(self):
        forecast = {"h": "Home", "a": "Away", "comp": "League",
                    "utc": "2026-11-12T19:00:00Z",
                    "p": {"ph": 0.5, "pd": 0.25, "pa": 0.25}}
        self.assertIsNone(snapshot_published_pick(forecast))
        forecast["id"] = "fixture-123"
        self.assertEqual(snapshot_published_pick(forecast)["id"], "fixture-123")

    def test_published_pick_snapshot_and_result_use_original_prediction(self):
        forecast = {"id": 42, "h": "Home", "a": "Away", "comp": "League",
                    "utc": "2026-11-12T19:00:00Z",
                    "p": {"ph": 0.6, "pd": 0.2, "pa": 0.2}}
        snap = snapshot_published_pick(forecast)
        self.assertEqual(snap["pick_index"], 0)
        self.assertEqual(pick_label(snap), "Home win: Home")
        changed = dict(forecast, p={"ph": 0.1, "pd": 0.1, "pa": 0.8}, final=[1, 0])
        results, state = resolve_published_picks({"pending": [snap], "sent_ids": ["42"]}, [changed])
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["correct"])
        self.assertEqual(results[0]["p"]["ph"], 0.6)
        self.assertEqual(results[0]["final"], [1, 0])
        self.assertEqual(state["pending"], [])
        self.assertEqual(len(state["results"]), 1)
        self.assertTrue(state["results"][0]["correct"])

    def test_unfinished_or_unpublished_matches_are_not_reported(self):
        snap = snapshot_published_pick({"id": "m1", "h": "A", "a": "B", "comp": "L",
            "utc": "2026-11-12T19:00:00Z", "p": {"ph": .5, "pd": .3, "pa": .2}})
        results, state = resolve_published_picks({"pending": [snap]}, [
            {"id": "m1", "final": None}, {"id": "other", "final": [3, 0]}])
        self.assertEqual(results, [])
        self.assertEqual([x["id"] for x in state["pending"]], ["m1"])

    def test_settled_results_are_unique_and_override_stale_pending_entries(self):
        snap = snapshot_published_pick({"id": "settled-1", "h": "A", "a": "B", "comp": "L",
            "utc": "2026-11-12T19:00:00Z", "p": {"ph": .6, "pd": .2, "pa": .2}})
        result = dict(snap, final=[2, 0], actual_index=0, correct=True)
        stale_pending = dict(snap, pick_index=2)
        state = clean_pick_state({
            "pending": [stale_pending],
            "results": [result, result],
            "sent_ids": ["settled-1"],
        })
        self.assertEqual(state["pending"], [])
        self.assertEqual(len(state["results"]), 1)
        self.assertEqual(state["results"][0]["pick_index"], 0)
        self.assertTrue(state["results"][0]["correct"])

    def test_pick_state_rejects_malformed_entries_and_duplicate_ids(self):
        snap = snapshot_published_pick({"id": 7, "h": "A", "a": "B", "comp": "L",
            "utc": "2026-11-12T19:00:00Z", "p": {"ph": .5, "pd": .3, "pa": .2}})
        state = clean_pick_state({"pending": [snap, snap, None], "sent_ids": [7, True, "7", "x"]})
        self.assertEqual(len(state["pending"]), 1)
        self.assertEqual(state["sent_ids"], ["7", "x"])
        self.assertEqual(state["results"], [])



class ResultsOnlyWorkflowTests(unittest.TestCase):
    def test_results_tab_uses_only_published_pick_ledger_for_accuracy(self):
        source = Path("index.html").read_text(encoding="utf-8")
        start = source.index("function publishedResultsHtml()")
        end = source.index("\nfunction list()", start)
        panel = source[start:end]
        self.assertIn("Q?.pending", panel)
        self.assertIn("Q?.results", panel)
        self.assertIn("hits=sorted.filter(r=>r.correct===true).length", panel)
        self.assertIn("Pending picks are not counted in the accuracy rate.", panel)
        self.assertIn("original fixture ID", panel)

    def test_published_pick_ledger_starts_with_valid_empty_schema(self):
        import json
        ledger = json.loads(Path("daily/published_picks.json").read_text(encoding="utf-8"))
        self.assertEqual(set(ledger), {"version", "pending", "results", "sent_ids"})
        self.assertEqual(ledger["version"], 1)
        self.assertEqual(ledger["pending"], [])
        self.assertEqual(ledger["results"], [])
        self.assertEqual(ledger["sent_ids"], [])

    def test_results_only_mode_exits_before_new_picks_and_news(self):
        source = Path("telegram.py").read_text(encoding="utf-8")
        flag = 'RESULTS_ONLY = os.environ.get("PITCHIQ_RESULTS_ONLY") == "1"'
        self.assertIn(flag, source)
        self.assertLess(source.index(flag), source.index('up = [p for p in preds'))
        self.assertIn("no new picks or news posts were requested", source)
        self.assertIn("resolve_published_picks(pick_state, preds)", source)
        self.assertIn("if completed_picks and RESULTS_ONLY:", source)
        self.assertIn("Results are sent only by the dedicated results workflow", source)

    def test_hourly_results_workflow_does_not_install_pillow_or_call_odds(self):
        workflow = Path(".github/workflows/telegram-results.yml").read_text(encoding="utf-8")
        self.assertIn("cron: '17 * * * *'", workflow)
        self.assertIn('PITCHIQ_RESULTS_ONLY: "1"', workflow)
        self.assertIn("python telegram.py", workflow)
        self.assertNotIn("pip install", workflow)
        self.assertNotIn("odds.py", workflow)
        self.assertIn("group: pitchiq-telegram-results", workflow)

    def test_publisher_workflows_use_independent_concurrency_groups(self):
        paths = (
            ".github/workflows/update.yml",
            ".github/workflows/international.yml",
            ".github/workflows/telegram.yml",
            ".github/workflows/telegram-results.yml",
            ".github/workflows/odds.yml",
        )
        groups = {}
        for path in paths:
            workflow = Path(path).read_text(encoding="utf-8")
            group_line = next(
                line.strip() for line in workflow.splitlines()
                if line.strip().startswith("group:")
            )
            groups[path] = group_line.split(":", 1)[1].strip()
        shared = "pitchiq-telegram-published-picks"
        self.assertEqual(groups[".github/workflows/telegram.yml"], shared)
        self.assertEqual(groups[".github/workflows/telegram-results.yml"], shared)
        independent = [groups[path] for path in paths
                       if path not in (".github/workflows/telegram.yml",
                                       ".github/workflows/telegram-results.yml")]
        self.assertEqual(len(independent), len(set(independent)))
        self.assertNotIn(shared, independent)
        self.assertNotIn("pitchiq-publish", groups.values())



    def test_daily_picks_are_scheduled_after_odds_refresh(self):
        workflow = Path(".github/workflows/telegram.yml").read_text(encoding="utf-8")
        self.assertIn("cron: '43 7 * * *'", workflow)
        odds_workflow = Path(".github/workflows/odds.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "23 7 * * *"', odds_workflow)
        odds_minute = int(odds_workflow.split('cron: "')[1].split()[0])
        picks_minute = int(workflow.split("cron: '")[1].split()[0])
        self.assertLess(odds_minute, picks_minute)
        self.assertIn("no Telegram post will be sent", Path("telegram.py").read_text(encoding="utf-8"))

    def test_daily_picks_workflow_never_falls_back_to_unrequested_news(self):
        source = Path("telegram.py").read_text(encoding="utf-8")
        self.assertNotIn("def news_post", source)
        self.assertNotIn("news_post()", source)
        self.assertIn("no Telegram post will be sent", source)
        self.assertIn("no Telegram post will be sent.", source)


    def test_daily_record_uses_only_settled_published_pick_ledger(self):
        source = Path("telegram.py").read_text(encoding="utf-8")
        self.assertIn('published_results = pick_state["results"]', source)
        self.assertIn('Published-pick record:', source)
        self.assertNotIn('done = [p for p in preds if valid_forecast(p) and valid_final(p.get("final"))]', source)
        self.assertNotIn('Record so far:', source)


class TelegramDeliverySafetyTests(unittest.TestCase):
    def test_pick_ledger_is_saved_only_after_confirmed_photo_or_text_delivery(self):
        source = Path("telegram.py").read_text(encoding="utf-8")
        save_at = source.rindex("save_pick_state(pick_state)")
        send_at = source.index("delivered = False")
        self.assertGreater(save_at, send_at)
        self.assertIn("if not delivered:", source)
        self.assertIn("Telegram did not confirm either the photo or text pick post.", source)
        self.assertIn("Only record picks after Telegram confirms", source)


if __name__ == "__main__":
    unittest.main()

class TelegramLedgerWorkflowIsolationTests(unittest.TestCase):
    def test_pick_and_results_workflows_serialize_shared_ledger_updates(self):
        picks = Path(".github/workflows/telegram.yml").read_text(encoding="utf-8")
        results = Path(".github/workflows/telegram-results.yml").read_text(encoding="utf-8")
        self.assertIn("group: pitchiq-telegram-published-picks", picks)
        self.assertIn("group: pitchiq-telegram-published-picks", results)

    def test_telegram_publishers_do_not_copy_unrelated_daily_ledgers(self):
        picks = Path(".github/workflows/telegram.yml").read_text(encoding="utf-8")
        results = Path(".github/workflows/telegram-results.yml").read_text(encoding="utf-8")
        self.assertIn("published_picks.json top3.png", picks)
        self.assertIn("git add -A daily/published_picks.json", picks)
        self.assertIn("git add daily/published_picks.json", results)
        self.assertNotIn("cp -a daily/. ", picks)
        self.assertNotIn("cp -a daily/. ", results)

class PickIndexValidationTests(unittest.TestCase):
    def test_boolean_pick_index_is_rejected_for_pending_and_settled_entries(self):
        snap = snapshot_published_pick({"id": "bool-index", "h": "A", "a": "B", "comp": "L",
            "utc": "2026-11-12T19:00:00Z", "p": {"ph": .5, "pd": .3, "pa": .2}})
        pending = dict(snap, pick_index=True)
        settled = dict(snap, pick_index=True, final=[1, 0], correct=True)
        state = clean_pick_state({"pending": [pending], "results": [settled]})
        self.assertEqual(state["pending"], [])
        self.assertEqual(state["results"], [])

