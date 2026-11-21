import unittest

from sportapi_live_probe import summarize_live_fixtures


class LiveFixtureSummaryTests(unittest.TestCase):
    def test_counts_live_half_time_and_non_live_statuses(self):
        payload = {"success": True, "data": [
            {"id": 1, "status": "LIVE", "league_name": "Premier League",
             "home_team": "Arsenal", "away_team": "Chelsea",
             "home_score": 1, "away_score": 0, "minute": "67'"},
            {"id": 4, "status": "HT", "league_name": "La Liga",
             "home_team": "Barcelona", "away_team": "Real Madrid",
             "home_score": 1, "away_score": 1, "minute": "HT"},
            {"id": 2, "status": "FT"},
            {"id": 3, "status": "Scheduled"},
        ]}
        result = summarize_live_fixtures(payload)
        self.assertEqual(result["fixtures_returned"], 4)
        self.assertEqual(result["status_counts"], {
            "LIVE": 1, "HT": 1, "FT": 1, "SCHEDULED": 1
        })
        self.assertEqual(result["live_fixture_count"], 2)
        self.assertEqual(
            [fixture["status"] for fixture in result["live_fixtures"]],
            ["LIVE", "HT"],
        )
        self.assertEqual(result["live_fixtures"][0]["fixture_id"], 1)
        self.assertEqual(result["live_fixtures"][0]["minute"], "67'")

    def test_accepts_empty_day_without_inventing_live_matches(self):
        result = summarize_live_fixtures({"success": True, "data": []})
        self.assertEqual(result["live_fixture_count"], 0)
        self.assertEqual(result["status_counts"], {})

    def test_rejects_missing_status(self):
        with self.assertRaisesRegex(ValueError, "no valid status"):
            summarize_live_fixtures({"success": True, "data": [{"id": 1}]})

    def test_rejects_invalid_payload(self):
        with self.assertRaisesRegex(ValueError, "successful JSON object"):
            summarize_live_fixtures({"success": False, "data": []})


if __name__ == "__main__":
    unittest.main()
