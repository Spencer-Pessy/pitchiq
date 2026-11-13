import unittest
from datetime import datetime, timezone

from sportapi_smoke_test import (
    select_upcoming_fixtures,
    inspect_h2h_payload,
    select_h2h_fixtures,
    validate_success_payload,
)


class SportAPIPayloadTests(unittest.TestCase):
    def test_accepts_successful_object(self):
        payload = {"success": True, "data": []}
        self.assertIs(validate_success_payload(payload, "/leagues"), payload)

    def test_rejects_provider_error(self):
        with self.assertRaisesRegex(ValueError, "not a successful JSON object"):
            validate_success_payload({"success": False, "error": "bad key"}, "/leagues")

    def test_rejects_non_object(self):
        with self.assertRaises(ValueError):
            validate_success_payload([], "/leagues")


class HeadToHeadPayloadTests(unittest.TestCase):
    def test_accepts_valid_history(self):
        payload = {
            "success": True,
            "data": [{
                "home_id": 10, "away_id": 20, "date": "2026-10-01",
                "home_score": 2, "away_score": 1, "status": "FT",
            }],
        }
        self.assertEqual(len(inspect_h2h_payload(payload, 10, 20)["scored_records"]), 1)

    def test_accepts_empty_history_without_fabricating_zero_record(self):
        self.assertEqual(
            inspect_h2h_payload({"success": True, "data": []}, 10, 20)["records"], []
        )

    def test_rejects_wrong_pair(self):
        payload = {
            "success": True,
            "data": [{
                "home_id": 10, "away_id": 30, "date": "2026-10-01",
                "home_score": 2, "away_score": 1, "status": "FT",
            }],
        }
        with self.assertRaisesRegex(ValueError, "different team pairing"):
            inspect_h2h_payload(payload, 10, 20)

    def test_rejects_non_finished_or_incomplete_record(self):
        payload = {
            "success": True,
            "data": [{
                "home_id": 10, "away_id": 20, "date": "2026-10-01",
                "home_score": 2, "away_score": 1, "status": "LIVE",
            }],
        }
        report = inspect_h2h_payload(payload, 10, 20)
        self.assertEqual(report["unscored_records"], 1)
        self.assertEqual(report["scored_records"], [])


    def test_reports_null_scores_without_treating_endpoint_as_broken(self):
        payload = {"success": True, "data": [{"home_id": 10, "away_id": 20, "date": "2026-10-01", "home_score": None, "away_score": None, "status": "FT"}]}
        report = inspect_h2h_payload(payload, 10, 20)
        self.assertEqual(report["unscored_records"], 1)
        self.assertEqual(report["score_field_types"], ["NoneType/NoneType"])

    def test_selects_unique_valid_pairs_up_to_limit(self):
        upcoming = [
            (None, {"id": 1, "home_id": 10, "away_id": 20}),
            (None, {"id": 2, "home_id": 20, "away_id": 10}),
            (None, {"id": 3, "home_id": 30, "away_id": 40}),
            (None, {"id": 4, "home_id": 50, "away_id": 50}),
            (None, {"id": 5, "home_id": "60", "away_id": 70}),
            (None, {"id": 6, "home_id": 80, "away_id": 90}),
        ]
        selected = select_h2h_fixtures(upcoming, limit=3)
        self.assertEqual([item["id"] for item in selected], [1, 3, 6])

    def test_score_boolean_is_not_counted_as_a_valid_score(self):
        payload = {"success": True, "data": [{
            "home_id": 10, "away_id": 20, "date": "2026-10-01",
            "home_score": True, "away_score": 1, "status": "FT",
        }]}
        report = inspect_h2h_payload(payload, 10, 20)
        self.assertEqual(report["scored_records"], [])
        self.assertEqual(report["unscored_records"], 1)


class UpcomingFixtureSelectionTests(unittest.TestCase):
    def test_selects_future_scheduled_fixtures_from_distinct_leagues(self):
        now = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)
        fixtures = [
            {"id": 1, "league_id": 10, "status": "FT", "kickoff_utc": "2026-11-13T08:00:00Z"},
            {"id": 2, "league_id": 10, "status": "Scheduled", "kickoff_utc": "2026-11-13T12:00:00Z"},
            {"id": 3, "league_id": 10, "status": "Scheduled", "kickoff_utc": "2026-11-13T13:00:00Z"},
            {"id": 4, "league_id": 20, "status": "TIMED", "kickoff_utc": "2026-11-13T14:00:00Z"},
            {"id": 5, "league_id": 30, "status": "LIVE", "kickoff_utc": "2026-11-13T15:00:00Z"},
            {"id": 6, "league_id": 40, "status": "Scheduled", "kickoff_utc": "2026-11-13T16:00:00Z"},
        ]
        selected = select_upcoming_fixtures(fixtures, now=now, limit=3)
        self.assertEqual([item[1]["id"] for item in selected], [2, 4, 6])

    def test_ignores_missing_or_invalid_kickoff(self):
        now = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)
        fixtures = [
            {"id": 1, "league_id": 10, "status": "Scheduled"},
            {"id": 2, "league_id": 20, "status": "Scheduled", "kickoff_utc": "not-a-date"},
        ]
        self.assertEqual(select_upcoming_fixtures(fixtures, now=now), [])


if __name__ == "__main__":
    unittest.main()
