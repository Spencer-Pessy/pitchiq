import unittest
from datetime import date
from international_history import (
    build_ratings, parse_results, tournament_weight,
)


class InternationalHistoryTests(unittest.TestCase):
    def test_parses_completed_results_and_skips_invalid_rows(self):
        csv_text = (
            "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
            "2024-01-01,Kenya,Uganda,2,1,Friendly,Nairobi,Kenya,FALSE\n"
            "2024-01-02,Tanzania,Rwanda,0,0,African Cup of Nations qualification,Dar es Salaam,Tanzania,TRUE\n"
            "not-a-date,Invalid,Fixture,1,0,Friendly,Nowhere,Nowhere,FALSE\n"
            "2024-01-03,Kenya,Kenya,1,0,Friendly,Nairobi,Kenya,FALSE\n"
            "2024-01-04,Kenya,Uganda,,0,Friendly,Nairobi,Kenya,FALSE\n"
        )
        rows, invalid = parse_results(csv_text, today=date(2024, 12, 31))
        self.assertEqual(len(rows), 2)
        self.assertEqual(invalid, 3)
        self.assertEqual(rows[0]["home"], "Kenya")
        self.assertFalse(rows[0]["neutral"])
        self.assertTrue(rows[1]["neutral"])

    def test_rejects_missing_required_columns(self):
        with self.assertRaises(ValueError):
            parse_results("date,home_team,away_team\n2024-01-01,A,B\n")

    def test_duplicate_matches_are_not_counted_twice(self):
        csv_text = (
            "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
            "2024-01-01,Kenya,Uganda,2,1,Friendly,Nairobi,Kenya,FALSE\n"
            "2024-01-01,Kenya,Uganda,2,1,Friendly,Nairobi,Kenya,FALSE\n"
        )
        rows, invalid = parse_results(csv_text, today=date(2024, 12, 31))
        self.assertEqual(len(rows), 1)
        self.assertEqual(invalid, 0)

    def test_elo_replay_is_chronological_and_uses_neutral_venue(self):
        home_match = {
            "date": "2024-01-01", "home": "Kenya", "away": "Uganda",
            "home_score": 1, "away_score": 0, "tournament": "Friendly", "neutral": False,
        }
        neutral_match = dict(home_match, neutral=True)
        home_ratings = {row["team"]: row["elo"] for row in build_ratings([home_match])}
        neutral_ratings = {row["team"]: row["elo"] for row in build_ratings([neutral_match])}
        self.assertLess(home_ratings["Kenya"], neutral_ratings["Kenya"])
        self.assertGreater(home_ratings["Uganda"], neutral_ratings["Uganda"])

    def test_tournament_weights_are_conservative_and_ordered(self):
        self.assertLess(tournament_weight("Friendly"), tournament_weight("FIFA World Cup qualification"))
        self.assertLess(tournament_weight("FIFA World Cup qualification"), tournament_weight("FIFA World Cup"))
        self.assertEqual(tournament_weight("Unknown regional tournament"), 1.0)


if __name__ == "__main__":
    unittest.main()
