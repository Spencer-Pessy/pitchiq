import unittest
from international import normalize_matches, parse_kickoff


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
        self.assertEqual(rows[0]["source"] if "source" in rows[0] else "ok", "ok")

    def test_rejects_malformed_or_empty_source(self):
        with self.assertRaises(ValueError):
            normalize_matches({"matches": []})
        with self.assertRaises(ValueError):
            normalize_matches({"response": []})


if __name__ == "__main__":
    unittest.main()
