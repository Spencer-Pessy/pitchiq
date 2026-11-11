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

    def test_unfinished_or_unpublished_matches_are_not_reported(self):
        snap = snapshot_published_pick({"id": "m1", "h": "A", "a": "B", "comp": "L",
            "utc": "2026-11-12T19:00:00Z", "p": {"ph": .5, "pd": .3, "pa": .2}})
        results, state = resolve_published_picks({"pending": [snap]}, [
            {"id": "m1", "final": None}, {"id": "other", "final": [3, 0]}])
        self.assertEqual(results, [])
        self.assertEqual([x["id"] for x in state["pending"]], ["m1"])

    def test_pick_state_rejects_malformed_entries_and_duplicate_ids(self):
        snap = snapshot_published_pick({"id": 7, "h": "A", "a": "B", "comp": "L",
            "utc": "2026-11-12T19:00:00Z", "p": {"ph": .5, "pd": .3, "pa": .2}})
        state = clean_pick_state({"pending": [snap, snap, None], "sent_ids": [7, True, "7", "x"]})
        self.assertEqual(len(state["pending"]), 1)
        self.assertEqual(state["sent_ids"], ["7", "x"])


if __name__ == "__main__":
    unittest.main()
