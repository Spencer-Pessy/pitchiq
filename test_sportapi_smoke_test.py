import unittest
from datetime import datetime, timezone

from sportapi_smoke_test import (
    select_upcoming_fixtures,
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
