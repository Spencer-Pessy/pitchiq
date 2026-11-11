import unittest

from pitchiq_data import (
    INTERNATIONAL_COMPETITIONS,
    average_bucket,
    goal_average_keys,
    build_feed_health,
    player_goals_per_appearance,
    player_rate_stats,
    team_venue_stats,
    forecast_input_snapshot,
)


class TeamVenueStatsTests(unittest.TestCase):
    def test_venue_rates_are_shrunk_and_sample_sizes_are_exposed(self):
        history = [
            (True, 3, 1, "W"),
            (False, 0, 2, "L"),
            (True, 1, 1, "D"),
            (False, 2, 0, "W"),
            (True, 2, 0, "W"),
        ]
        result = team_venue_stats(history, True, 1.5, 1.2, 1600, shrink=2, form_limit=3)
        self.assertEqual(result["venue_matches"], 3)
        self.assertEqual(result["form_matches"], 3)
        self.assertEqual(result["form"], "DWW")
        self.assertEqual(result["form_scope"], "all_venues")
        self.assertAlmostEqual(result["gf"], 1.8)
        self.assertAlmostEqual(result["ga"], 0.88)
        self.assertEqual(result["elo"], 1600)

    def test_no_venue_history_uses_prior_and_discloses_zero_sample(self):
        result = team_venue_stats([], False, 1.4, 1.1, 1500)
        self.assertEqual(result["gf"], 1.4)
        self.assertEqual(result["ga"], 1.1)
        self.assertEqual(result["venue_matches"], 0)
        self.assertEqual(result["form_matches"], 0)
        self.assertEqual(result["form"], "")


class ForecastSnapshotTests(unittest.TestCase):
    def test_snapshot_captures_model_inputs_for_future_diagnostics(self):
        stats = {
            "h": {"gf": 1.8, "ga": 1.1, "elo": 1550, "form": "WWDLW", "out": 0,
                  "venue_matches": 8, "form_matches": 5, "form_scope": "all_venues"},
            "a": {"gf": 1.2, "ga": 1.5, "elo": 1490, "form": "LDWDL", "out": 0,
                  "venue_matches": 6, "form_matches": 5, "form_scope": "all_venues"},
            "lh": 1.55, "la": 1.25,
        }
        snapshot = forecast_input_snapshot(stats)
        self.assertEqual(snapshot["schema"], 2)
        self.assertEqual(snapshot["home"]["venue_matches"], 8)
        self.assertEqual(snapshot["away"]["form"], "LDWDL")
        self.assertEqual(snapshot["league_home"], 1.55)
        self.assertEqual(snapshot["league_away"], 1.25)
        self.assertEqual(snapshot["calibration"], {"kh": 1.0, "ka": 1.0})
        self.assertNotIn("unrelated", snapshot["home"])

    def test_snapshot_supports_older_or_partial_team_inputs(self):
        snapshot = forecast_input_snapshot({"h": {"gf": 1.4}, "a": {}, "lh": 1.5})
        self.assertEqual(snapshot["home"], {"gf": 1.4})
        self.assertEqual(snapshot["away"], {})
        self.assertIsNone(snapshot["league_away"])


class CompetitionDataTests(unittest.TestCase):
    def test_world_cup_and_euro_are_international(self):
        self.assertEqual(INTERNATIONAL_COMPETITIONS, frozenset({"WC", "EC"}))

    def test_international_results_get_separate_and_shared_buckets(self):
        self.assertEqual(goal_average_keys("WC"), ("WC", "INTL", "ALL"))
        self.assertEqual(goal_average_keys("EC"), ("EC", "INTL", "ALL"))

    def test_club_results_never_enter_international_bucket(self):
        self.assertEqual(goal_average_keys("PL"), ("PL", "ALL"))

    def test_small_international_sample_uses_international_prior(self):
        counts = {"WC": 8, "EC": 6, "INTL": 14, "ALL": 120}
        self.assertEqual(average_bucket("WC", counts), "INTL")
        self.assertEqual(average_bucket("EC", counts), "INTL")

    def test_large_international_sample_uses_own_competition(self):
        self.assertEqual(average_bucket("WC", {"WC": 24, "INTL": 40}), "WC")

    def test_champions_league_keeps_existing_combined_prior_rule(self):
        self.assertEqual(average_bucket("CL", {"CL": 40, "ALL": 200}), "ALL")

    def test_small_club_competition_keeps_existing_fallback(self):
        self.assertEqual(average_bucket("PL", {"PL": 12, "ALL": 100}), "ALL")

    def test_international_fixture_detection_uses_team_metadata(self):
        from pitchiq_data import is_international_fixture

        national = {"league": {"name": "Friendly", "country": "World"},
                    "teams": {"home": {"national": True}, "away": {"national": True}}}
        club = {"league": {"name": "Friendlies", "country": "World"},
                "teams": {"home": {"national": False}, "away": {"national": False}}}
        self.assertTrue(is_international_fixture(national))
        self.assertFalse(is_international_fixture(club))

    def test_international_fixture_detection_recognizes_tournaments(self):
        from pitchiq_data import is_international_fixture

        world_cup = {"league": {"name": "World Cup - Qualification Africa", "country": "Africa"},
                     "teams": {"home": {}, "away": {}}}
        friendlies = {"league": {"name": "Friendlies", "country": "World"},
                      "teams": {"home": {}, "away": {}}}
        club_friendly = {"league": {"name": "Friendlies Clubs", "country": "World"},
                         "teams": {"home": {}, "away": {}}}
        women_club = {"league": {"name": "UEFA Champions League Women", "country": "World"},
                       "teams": {"home": {}, "away": {}}}
        women_europa = {"league": {"name": "UEFA Europa Cup - Women", "country": "World"},
                          "teams": {"home": {}, "away": {}}}
        self.assertTrue(is_international_fixture(world_cup))
        self.assertTrue(is_international_fixture(friendlies))
        self.assertFalse(is_international_fixture(club_friendly))
        self.assertFalse(is_international_fixture(women_club))
        self.assertFalse(is_international_fixture(women_europa))

    def test_player_scoring_rate_is_calculated_safely(self):
        self.assertEqual(player_goals_per_appearance(9, 10), 0.9)
        self.assertEqual(player_goals_per_appearance(1, 3), 0.333)
        self.assertIsNone(player_goals_per_appearance(4, 0))
        self.assertIsNone(player_goals_per_appearance(None, 10))
        self.assertIsNone(player_goals_per_appearance(-1, 5))

    def test_player_contribution_rates_handle_missing_assists(self):
        self.assertEqual(player_rate_stats(9, 3, 10), {
            "gpm": 0.9, "apm": 0.3, "gapm": 1.2,
        })
        self.assertEqual(player_rate_stats(4, None, 8), {
            "gpm": 0.5, "apm": None, "gapm": None,
        })
        self.assertEqual(player_rate_stats(4, 2, 0), {
            "gpm": None, "apm": None, "gapm": None,
        })

    def test_forecast_snapshot_preserves_schema_and_calibration(self):
        stats = {
            "h": {"gf": 1.4, "ga": 1.1, "elo": 1600, "form": "WWD",
                  "venue_matches": 4, "form_matches": 3, "form_scope": "all_venues"},
            "a": {"gf": 1.2, "ga": 1.3, "elo": 1500, "form": "LDW",
                  "venue_matches": 5, "form_matches": 3, "form_scope": "all_venues"},
            "lh": 1.5, "la": 1.2,
        }
        snapshot = forecast_input_snapshot(stats, {"kh": 1.05, "ka": 0.95})
        self.assertEqual(snapshot["schema"], 2)
        self.assertEqual(snapshot["calibration"], {"kh": 1.05, "ka": 0.95})
        self.assertEqual(snapshot["home"]["venue_matches"], 4)
        self.assertEqual(snapshot["league_home"], 1.5)

    def test_forecast_snapshot_uses_neutral_calibration_by_default(self):
        snapshot = forecast_input_snapshot({"h": {}, "a": {}, "lh": 1.5, "la": 1.2})
        self.assertEqual(snapshot["schema"], 2)
        self.assertEqual(snapshot["calibration"], {"kh": 1.0, "ka": 1.0})

    def test_feed_health_reports_competition_coverage(self):
        health = build_feed_health(
            {"PL": 30, "WC": 4, "EC": 2},
            {"PL", "WC"},
            18,
            {"EC"},
        )
        self.assertEqual(health["fixture_competitions"], 3)
        self.assertEqual(health["fixture_total"], 36)
        self.assertEqual(health["international_fixture_total"], 6)
        self.assertEqual(health["standings_competitions"], 2)
        self.assertEqual(health["standings_failed"], [])
        self.assertEqual(health["standings_failures"], 0)
        self.assertEqual(health["published_match_count"], 18)
        self.assertEqual(health["fixture_counts"], {"EC": 2, "PL": 30, "WC": 4})

    def test_only_unexpected_standings_failures_are_reported(self):
        health = build_feed_health(
            {"PL": 20, "WC": 10, "EC": 8},
            {"PL"},
            5,
            {"WC", "EC", "PL"},
        )
        self.assertEqual(health["standings_failed"], ["PL"])
        self.assertEqual(health["standings_failures"], 1)

    def test_feed_health_handles_no_standings_or_fixtures(self):
        health = build_feed_health({}, set(), 0)
        self.assertEqual(health["fixture_total"], 0)
        self.assertEqual(health["international_fixture_total"], 0)
        self.assertEqual(health["standings_available"], [])
        self.assertEqual(health["standings_failures"], 0)


if __name__ == "__main__":
    unittest.main()
