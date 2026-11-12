import unittest
from datetime import date, timedelta
from international_history import (
    backtest_elo, build_ratings, classify_team, load_team_registry, parse_results, tournament_weight,
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

    def test_elo_backtest_uses_date_grouped_chronological_holdout(self):
        matches = []
        start = date(2020, 1, 1)
        teams = ["Kenya", "Uganda", "Tanzania"]
        scores = [(1, 0), (0, 0), (0, 1), (2, 1)]
        for index in range(60):
            home = teams[index % 3]
            away = teams[(index + 1) % 3]
            home_score, away_score = scores[index % len(scores)]
            matches.append({
                "date": (start + timedelta(days=index)).isoformat(),
                "home": home,
                "away": away,
                "home_score": home_score,
                "away_score": away_score,
                "tournament": "Friendly" if index % 2 else "World Cup qualification",
                "neutral": index % 2 == 0,
            })
        result = backtest_elo(matches)
        self.assertEqual(result["training_matches"], 48)
        self.assertEqual(result["test_matches"], 12)
        self.assertEqual(result["holdout_start"], (start + timedelta(days=48)).isoformat())
        self.assertIn("same date share the same pre-date ratings", result["note"])
        self.assertEqual(
            sum(item["matches"] for item in result["holdout_slices"]["era"].values()),
            result["test_matches"],
        )
        self.assertEqual(
            sum(item["matches"] for item in result["holdout_slices"]["competition_type"].values()),
            result["test_matches"],
        )
        for section in ("model", "training_frequency_baseline"):
            self.assertGreaterEqual(result[section]["multiclass_brier"], 0)
            self.assertGreater(result[section]["log_loss"], 0)
            self.assertGreaterEqual(result[section]["accuracy"], 0)
            self.assertLessEqual(result[section]["accuracy"], 1)

    def test_current_elo_does_not_leak_same_day_results_between_fixtures(self):
        same_day = [
            {
                "date": "2024-01-01", "home": "Kenya", "away": "Uganda",
                "home_score": 1, "away_score": 0, "tournament": "Friendly", "neutral": False,
            },
            {
                "date": "2024-01-01", "home": "Kenya", "away": "Tanzania",
                "home_score": 1, "away_score": 0, "tournament": "Friendly", "neutral": False,
            },
        ]
        expected_home = 1 / (1 + 10 ** (-65 / 400))
        expected_rating = round(1500 + 2 * 20 * 0.75 * (1 - expected_home), 2)
        ratings = {row["team"]: row["elo"] for row in build_ratings(same_day)}
        self.assertEqual(ratings["Kenya"], expected_rating)

    def test_fifa_registry_has_211_unique_member_associations(self):
        registry, official, aliases = load_team_registry()
        self.assertEqual(len(registry["fifa_member_associations"]), 211)
        self.assertEqual(len(official), 211)
        self.assertTrue(aliases)

    def test_historical_aliases_share_one_canonical_elo_identity(self):
        csv_text = (
            "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
            "2024-01-01,South Korea,Japan,2,1,Friendly,Seoul,South Korea,FALSE\n"
            "2024-02-01,Korea Republic,China,1,0,Friendly,Seoul,South Korea,FALSE\n"
        )
        rows, invalid = parse_results(csv_text, today=date(2024, 12, 31))
        self.assertEqual(invalid, 0)
        self.assertEqual([row["home"] for row in rows], ["Korea Republic", "Korea Republic"])
        self.assertEqual(rows[0]["home_source"], "South Korea")
        self.assertEqual(rows[1]["home_source"], "Korea Republic")
        ratings = build_ratings(rows)
        korea = [row for row in ratings if row["team"] == "Korea Republic"]
        self.assertEqual(len(korea), 1)
        self.assertEqual(korea[0]["matches"], 2)

    def test_alias_and_canonical_duplicate_fixture_is_deduplicated(self):
        csv_text = (
            "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
            "2024-01-01,South Korea,Japan,2,1,Friendly,Seoul,South Korea,FALSE\n"
            "2024-01-01,Korea Republic,Japan,2,1,Friendly,Seoul,South Korea,FALSE\n"
        )
        rows, invalid = parse_results(csv_text, today=date(2024, 12, 31))
        self.assertEqual(invalid, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["home"], "Korea Republic")

    def test_team_identity_aliases_and_non_fifa_sides_are_separated(self):
        registry_data = load_team_registry()
        self.assertEqual(
            classify_team("Ivory Coast", registry_data)["canonical_team"],
            "Côte d'Ivoire",
        )
        self.assertEqual(
            classify_team("Korea Republic", registry_data)["association_status"],
            "fifa_member_association",
        )
        self.assertEqual(
            classify_team("South Korea", registry_data)["canonical_team"],
            "Korea Republic",
        )
        self.assertEqual(
            classify_team("Hong Kong", registry_data)["canonical_team"],
            "Hong Kong, China",
        )
        representative = classify_team("Abkhazia", registry_data)
        self.assertEqual(representative["association_status"], "non_fifa_or_unverified")
        self.assertFalse(representative["forecast_eligible"])
        self.assertFalse(classify_team("Kenya", registry_data)["forecast_eligible"])

    def test_tournament_weights_are_conservative_and_ordered(self):
        self.assertLess(tournament_weight("Friendly"), tournament_weight("FIFA World Cup qualification"))
        self.assertLess(tournament_weight("FIFA World Cup qualification"), tournament_weight("FIFA World Cup"))
        self.assertEqual(tournament_weight("Unknown regional tournament"), 1.0)


if __name__ == "__main__":
    unittest.main()
