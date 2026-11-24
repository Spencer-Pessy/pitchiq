"""Tests for the public SportAPI live-score snapshot."""
import unittest
from datetime import datetime, timezone

from sportapi_live_feed import build_live_feed


class SportAPILiveFeedTests(unittest.TestCase):
    def fixture(self, **overrides):
        row = {
            "id": 123, "league_name": "Premier League",
            "home_team": "Arsenal", "away_team": "Chelsea",
            "kickoff_utc": "2026-11-21T14:00:00Z",
            "status": "LIVE", "minute": "37'",
            "home_score": 2, "away_score": 1,
        }
        row.update(overrides)
        return row

    def test_live_fixture_is_normalized_for_the_public_site(self):
        result = build_live_feed({"success": True, "data": [self.fixture()]},
                                 datetime(2026, 11, 21, tzinfo=timezone.utc))
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["fixtures_returned"], 1)
        self.assertEqual(result["status_counts"], {"LIVE": 1})
        self.assertEqual(result["active_statuses"], ["HT", "LIVE"])
        match = result["matches"][0]
        self.assertEqual(match["score"], [2, 1])
        self.assertEqual(match["status"], "LIVE")
        self.assertEqual(match["source"], "SportAPI")
        self.assertEqual(match["utc"], "2026-11-21T14:00:00Z")

    def test_provider_status_diagnostics_include_non_live_rows(self):
        result = build_live_feed({"success": True, "data": [
            self.fixture(status="SCHEDULED"),
            self.fixture(id=124, status="FT"),
            self.fixture(id=125, status="LIVE", minute="HT"),
        ]})
        self.assertEqual(result["fixtures_returned"], 3)
        self.assertEqual(result["status_counts"], {
            "SCHEDULED": 1, "FT": 1, "LIVE": 1
        })
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["matches"][0]["status"], "HT")

    def test_half_time_is_kept_as_active_status(self):
        result = build_live_feed({"success": True, "data": [
            self.fixture(status="LIVE", minute="HT")
        ]})
        self.assertEqual(result["matches"][0]["status"], "HT")

    def test_non_live_fixtures_are_excluded(self):
        result = build_live_feed({"success": True, "data": [
            self.fixture(status="SCHEDULED"),
            self.fixture(id=124, status="FT"),
        ]})
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["matches"], [])

    def test_missing_score_does_not_invent_zero_zero(self):
        result = build_live_feed({"success": True, "data": [
            self.fixture(home_score=None, away_score=None)
        ]})
        self.assertIsNone(result["matches"][0]["score"])

    def test_invalid_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            build_live_feed({"success": False, "data": []})
        with self.assertRaises(ValueError):
            build_live_feed({"success": True, "data": {}})

    def test_malformed_live_fixture_is_rejected(self):
        with self.assertRaises(ValueError):
            build_live_feed({"success": True, "data": [
                self.fixture(home_team="")
            ]})


if __name__ == "__main__":
    unittest.main()
