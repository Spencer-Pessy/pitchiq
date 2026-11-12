import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from international import (
    deduplicate, normalize_espn_event, normalize_matches, parse_kickoff,
)


class InternationalFeedTests(unittest.TestCase):
    def test_timezone_is_converted_to_utc(self):
        self.assertEqual(parse_kickoff("2026-06-11", "13:00 UTC-6"), "2026-06-11T19:00:00+00:00")
        self.assertEqual(parse_kickoff("2026-06-11", "20:00 UTC+3"), "2026-06-11T17:00:00+00:00")

    def test_invalid_or_missing_kickoff_is_rejected(self):
        self.assertIsNone(parse_kickoff("2026-06-11", "TBD"))
        self.assertIsNone(parse_kickoff("2026-06-11", "25:70 UTC+2"))

    def test_normalizes_national_world_cup_fixtures(self):
        payload = {
            "name": "World Cup 2026",
            "matches": [
                {"date": "2026-06-11", "time": "13:00 UTC-6",
                 "team1": "Mexico", "team2": "South Africa",
                 "score": {"ft": [2, 0]}, "ground": "Mexico City"},
                {"date": "2026-06-12", "time": "15:00 UTC-4",
                 "team1": "Canada", "team2": "Qatar", "score": {}},
                {"date": "2026-06-13", "time": "TBD",
                 "team1": "Missing Time", "team2": "Fixture"},
            ],
        }
        rows = normalize_matches(payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "FT")
        self.assertEqual(rows[0]["score"], [2, 0])
        self.assertEqual(rows[0]["utc"], "2026-06-11T19:00:00+00:00")
        self.assertEqual(rows[1]["status"], "NS")
        self.assertIsNone(rows[1]["score"])
        self.assertEqual(rows[0]["source"], "OpenFootball worldcup.json (CC0)")

    def test_normalizes_espn_upcoming_event(self):
        event = {
            "id": "12345",
            "date": "2026-11-14T16:00:00Z",
            "status": {"type": {"state": "pre", "name": "STATUS_SCHEDULED"}},
            "competitions": [{
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": "Japan"}, "score": ""},
                    {"homeAway": "away", "team": {"displayName": "Brazil"}, "score": ""},
                ],
                "venue": {"fullName": "National Stadium"},
            }],
            "leagues": [{"name": "International Friendly"}],
        }
        row = normalize_espn_event(event, "fifa.friendly", "International Friendlies")
        self.assertEqual(row["id"], "espn-fifa.friendly-12345")
        self.assertEqual(row["h"], "Japan")
        self.assertEqual(row["a"], "Brazil")
        self.assertEqual(row["status"], "NS")
        self.assertIsNone(row["score"])
        self.assertEqual(row["utc"], "2026-11-14T16:00:00+00:00")
        self.assertEqual(row["source"], "ESPN public scoreboard (unofficial)")

    def test_normalizes_espn_final_score_and_status(self):
        event = {
            "id": "987",
            "date": "2026-11-14T16:00:00Z",
            "status": {"type": {"state": "post", "name": "STATUS_FINAL", "description": "Final"}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"name": "Japan"}, "score": "2"},
                {"homeAway": "away", "team": {"name": "Brazil"}, "score": "1"},
            ]}],
        }
        row = normalize_espn_event(event, "fifa.friendly", "International Friendlies")
        self.assertEqual(row["status"], "FT")
        self.assertEqual(row["score"], [2, 1])

    def test_rejects_malformed_espn_event(self):
        self.assertIsNone(normalize_espn_event({}, "fifa.friendly", "Friendlies"))
        self.assertIsNone(normalize_espn_event({
            "id": "1", "date": "2026-11-14T16:00:00Z",
            "competitions": [{"competitors": []}],
        }, "fifa.friendly", "Friendlies"))

    def test_deduplicates_identical_fixture_rows(self):
        row = {"utc": "2026-11-14T16:00:00+00:00", "h": "Japan", "a": "Brazil", "id": "a"}
        duplicate = dict(row, id="b")
        self.assertEqual([x["id"] for x in deduplicate([row, duplicate])], ["a"])

    def test_rejects_malformed_or_empty_openfootball_source(self):
        with self.assertRaises(ValueError):
            normalize_matches({"matches": []})
        with self.assertRaises(ValueError):
            normalize_matches({"response": []})


if __name__ == "__main__":
    unittest.main()
