import unittest

from pitchiq_data import (
    INTERNATIONAL_COMPETITIONS,
    build_head_to_head,
    average_bucket,
    goal_average_keys,
    build_feed_health,
    player_goals_per_appearance,
    player_rate_stats,
    team_venue_stats,
    forecast_input_snapshot,
    record_forward_evaluations,
    backfill_market_odds,
    goal_rate_calibration,
    clean_prediction_ledger,
)


class HeadToHeadTests(unittest.TestCase):
    def test_last_five_meetings_are_sorted_and_scored_from_fixture_home_perspective(self):
        matches = [
            {"status":"FINISHED","utcDate":"2025-01-01T12:00:00Z","homeTeam":{"id":1,"shortName":"Alpha"},"awayTeam":{"id":2,"shortName":"Beta"},"score":{"fullTime":{"home":2,"away":0}}},
            {"status":"FINISHED","utcDate":"2025-02-01T12:00:00Z","homeTeam":{"id":2,"shortName":"Beta"},"awayTeam":{"id":1,"shortName":"Alpha"},"score":{"fullTime":{"home":1,"away":1}}},
            {"status":"FINISHED","utcDate":"2025-03-01T12:00:00Z","homeTeam":{"id":1,"shortName":"Alpha"},"awayTeam":{"id":2,"shortName":"Beta"},"score":{"fullTime":{"home":0,"away":1}}},
            {"status":"FINISHED","utcDate":"2025-04-01T12:00:00Z","homeTeam":{"id":1,"shortName":"Alpha"},"awayTeam":{"id":2,"shortName":"Beta"},"score":{"fullTime":{"home":3,"away":0}}},
            {"status":"FINISHED","utcDate":"2025-05-01T12:00:00Z","homeTeam":{"id":2,"shortName":"Beta"},"awayTeam":{"id":1,"shortName":"Alpha"},"score":{"fullTime":{"home":0,"away":2}}},
            {"status":"FINISHED","utcDate":"2025-06-01T12:00:00Z","homeTeam":{"id":1,"shortName":"Alpha"},"awayTeam":{"id":2,"shortName":"Beta"},"score":{"fullTime":{"home":1,"away":0}}},
            {"status":"SCHEDULED","utcDate":"2025-07-01T12:00:00Z","homeTeam":{"id":1},"awayTeam":{"id":2},"score":{"fullTime":{"home":9,"away":0}}},
            {"status":"FINISHED","utcDate":"2026-01-01T12:00:00Z","homeTeam":{"id":1},"awayTeam":{"id":2},"score":{"fullTime":{"home":9,"away":0}}},
        ]
        result = build_head_to_head(matches, 1, 2, "2025-08-01T00:00:00Z")
        self.assertEqual(result["played"], 5)
        self.assertEqual((result["home_wins"], result["draws"], result["away_wins"]), (3, 1, 1))
        self.assertEqual((result["home_goals"], result["away_goals"]), (7, 2))
        self.assertEqual(result["meetings"][0]["utc"], "2025-06-01T12:00:00+00:00")

    def test_h2h_requires_completed_matches_and_stops_at_kickoff(self):
        result = build_head_to_head([
            {"status":"FINISHED","utcDate":"2025-01-01T12:00:00Z","homeTeam":{"id":1},"awayTeam":{"id":2},"score":{"fullTime":{"home":1,"away":0}}},
        ], 1, 2, "2025-01-01T12:00:00Z")
        self.assertEqual(result["played"], 0)


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
        self.assertEqual(goal_average_keys("WC"), ("WC", "INTL"))
        self.assertEqual(goal_average_keys("EC"), ("EC", "INTL"))

    def test_club_and_international_fallback_pools_are_disjoint(self):
        club_keys = goal_average_keys("PL")
        international_keys = goal_average_keys("WC")
        self.assertNotIn("INTL", club_keys)
        self.assertNotIn("CLUB", international_keys)
        self.assertNotIn("ALL", club_keys + international_keys)

    def test_club_results_never_enter_international_bucket(self):
        self.assertEqual(goal_average_keys("PL"), ("PL", "CLUB"))

    def test_small_international_sample_uses_international_prior(self):
        counts = {"WC": 8, "EC": 6, "INTL": 14, "CLUB": 120}
        self.assertEqual(average_bucket("WC", counts), "INTL")
        self.assertEqual(average_bucket("EC", counts), "INTL")

    def test_large_international_sample_uses_own_competition(self):
        self.assertEqual(average_bucket("WC", {"WC": 24, "INTL": 40}), "WC")

    def test_champions_league_keeps_existing_combined_prior_rule(self):
        self.assertEqual(average_bucket("CL", {"CL": 40, "CLUB": 200}), "CLUB")

    def test_small_club_competition_keeps_existing_fallback(self):
        self.assertEqual(average_bucket("PL", {"PL": 12, "CLUB": 100}), "CLUB")

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


class ForwardEvaluationLedgerTests(unittest.TestCase):
    def test_creates_immutable_shadow_forecast_and_scores_it_later(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        fixture = {
            "id": 123, "status": "TIMED", "utc": "2026-11-20T18:00:00Z",
            "comp": "Premier League", "code": "PL", "h": "Arsenal", "a": "Chelsea",
            "s": {"h": {"gf": 1.8}, "a": {"gf": 1.2}, "lh": 1.5, "la": 1.1},
        }
        calls = []
        def predict(stats):
            calls.append("predict")
            return {"ph": 0.5, "pd": 0.25, "pa": 0.25}
        def snapshot(stats):
            calls.append("snapshot")
            return {"schema": 2, "home": stats["h"], "away": stats["a"],
                    "league_home": stats["lh"], "league_away": stats["la"],
                    "calibration": {"kh": 1.0, "ka": 1.0}}
        ledger = record_forward_evaluations({}, [fixture], {}, now, predict, snapshot)
        self.assertEqual(list(ledger), ["123"])
        self.assertTrue(ledger["123"]["evaluation_only"])
        self.assertEqual(ledger["123"]["inputs"]["schema"], 2)
        self.assertIsNone(ledger["123"]["final"])
        self.assertEqual(calls, ["predict", "snapshot"])

        # A later refresh must not replace the original shadow forecast.
        original_probability = ledger["123"]["p"]
        changed_fixture = dict(fixture, s={"h": {"gf": 99}, "a": {"gf": 0}, "lh": 2, "la": 0.2})
        ledger = record_forward_evaluations(
            ledger, [changed_fixture], {123: [2, 1]}, now, predict, snapshot)
        self.assertEqual(ledger["123"]["p"], original_probability)
        self.assertEqual(ledger["123"]["final"], [2, 1])
        self.assertEqual(calls, ["predict", "snapshot"])

    def test_ignores_started_fixtures(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        fixture = {
            "id": 124, "status": "TIMED", "utc": "2026-11-11T11:00:00Z",
            "comp": "Premier League", "code": "PL", "h": "A", "a": "B",
            "s": {"h": {}, "a": {}, "lh": 1.5, "la": 1.2},
        }
        ledger = record_forward_evaluations({}, [fixture], {}, now, lambda _: {}, lambda _: {})
        self.assertEqual(ledger, {})


    def test_existing_final_score_is_immutable(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        existing = {
            "123": {
                "id": 123, "final": [1, 0],
                "p": {"ph": 0.5, "pd": 0.25, "pa": 0.25},
            }
        }
        ledger = record_forward_evaluations(
            existing, [], {123: [2, 2]}, now, lambda _: {}, lambda _: {})
        self.assertEqual(ledger["123"]["final"], [1, 0])


class PredictionLedgerCleaningTests(unittest.TestCase):
    def test_non_dictionary_ledgers_become_empty(self):
        for value in (None, [], "bad", 7):
            self.assertEqual(clean_prediction_ledger(value), {})

    def test_non_record_entries_are_removed_and_valid_records_preserved(self):
        valid = {"id": 123, "final": None, "p": {"ph": 0.5}}
        cleaned = clean_prediction_ledger({
            "123": valid, "bad": None, "list": [], "": {"id": 1},
        })
        self.assertEqual(cleaned, {"123": valid})




class GoalRateCalibrationTests(unittest.TestCase):
    def test_valid_records_preserve_existing_calibration_formula(self):
        rows = []
        for _ in range(10):
            rows.append({"final": [2, 1], "p": {"rlh": 1.5, "rla": 1.0}})
        calibration, count = goal_rate_calibration(rows)
        weight = 10 / 130
        self.assertEqual(count, 10)
        self.assertEqual(calibration["kh"], round(1 + (2 / 1.5 - 1) * weight, 4))
        self.assertEqual(calibration["ka"], round(1 + (1 / 1.0 - 1) * weight, 4))

    def test_malformed_or_nonfinite_history_is_excluded_safely(self):
        valid = {"final": [1, 0], "p": {"lh": 1.2, "la": 0.8}}
        invalid = [
            None,
            {"final": [1], "p": {"lh": 1.0, "la": 1.0}},
            {"final": [True, 0], "p": {"lh": 1.0, "la": 1.0}},
            {"final": [1.5, 0], "p": {"lh": 1.0, "la": 1.0}},
            {"final": [1, 0], "p": {"lh": 0, "la": 1.0}},
            {"final": [1, 0], "p": {"lh": float("nan"), "la": 1.0}},
            {"final": [1, 0], "p": None},
        ]
        calibration, count = goal_rate_calibration([valid] * 9 + invalid)
        self.assertEqual(count, 9)
        self.assertEqual(calibration, {"kh": 1.0, "ka": 1.0})

    def test_calibration_is_bounded_and_handles_non_list_input(self):
        rows = [{"final": [20, 0], "p": {"lh": 0.1, "la": 2.0}}] * 10
        calibration, count = goal_rate_calibration(rows)
        self.assertEqual(count, 10)
        self.assertEqual(calibration["kh"], 1.15)
        self.assertEqual(calibration["ka"], 0.9231)
        self.assertEqual(goal_rate_calibration(None), ({"kh": 1.0, "ka": 1.0}, 0))


class MarketOddsBackfillTests(unittest.TestCase):
    def test_backfills_future_forecast_without_changing_prediction(self):
        from datetime import datetime, timezone
        predictions = {
            "1": {"id": 1, "utc": "2026-11-22T15:00:00Z", "h": "Arsenal",
                  "a": "Chelsea", "p": {"ph": 0.6, "pd": 0.2, "pa": 0.2},
                  "made": "2026-11-01T08:00:00+00:00", "final": None, "odds": None}
        }
        events = [{"home": "Arsenal FC", "away": "Chelsea FC",
                   "commence": "2026-11-22T15:00:00Z", "odds": [1.8, 3.7, 4.5]}]
        now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        same = lambda a, b: (a or "").replace(" FC", "") == (b or "").replace(" FC", "")
        count = backfill_market_odds(predictions, events, "2026-11-11T07:00:00Z", now, same)
        self.assertEqual(count, 1)
        self.assertEqual(predictions["1"]["odds"], [1.8, 3.7, 4.5])
        self.assertEqual(predictions["1"]["odds_updated"], "2026-11-11T07:00:00+00:00")
        self.assertEqual(predictions["1"]["p"], {"ph": 0.6, "pd": 0.2, "pa": 0.2})
        self.assertEqual(predictions["1"]["made"], "2026-11-01T08:00:00+00:00")

    def test_does_not_overwrite_existing_market_snapshot(self):
        from datetime import datetime, timezone
        predictions = {"1": {"utc": "2026-11-22T15:00:00Z", "h": "Arsenal",
                             "a": "Chelsea", "odds": [2.0, 3.0, 4.0]}}
        events = [{"home": "Arsenal", "away": "Chelsea",
                   "commence": "2026-11-22T15:00:00Z", "odds": [1.8, 3.7, 4.5]}]
        count = backfill_market_odds(
            predictions, events, "2026-11-11T07:00:00Z",
            datetime(2026, 11, 11, 12, tzinfo=timezone.utc), lambda a, b: a == b)
        self.assertEqual(count, 0)
        self.assertEqual(predictions["1"]["odds"], [2.0, 3.0, 4.0])

    def test_rejects_post_kickoff_or_mismatched_market_events(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        base = {"utc": "2026-11-22T15:00:00Z", "h": "Arsenal",
                "a": "Chelsea", "odds": None}
        late = [{"home": "Arsenal", "away": "Chelsea",
                 "commence": "2026-11-22T15:00:00Z", "odds": [1.8, 3.7, 4.5]}]
        far = [{"home": "Arsenal", "away": "Chelsea",
                "commence": "2026-11-23T15:00:00Z", "odds": [1.8, 3.7, 4.5]}]
        same = lambda a, b: a == b
        post = {"1": dict(base)}
        self.assertEqual(backfill_market_odds(post, late, "2026-11-23T00:00:00Z", now, same), 0)
        distant = {"1": dict(base)}
        self.assertEqual(backfill_market_odds(distant, far, "2026-11-11T07:00:00Z", now, same), 0)
        self.assertIsNone(post["1"]["odds"])
        self.assertIsNone(distant["1"]["odds"])



    def test_rejects_market_snapshots_with_wrong_number_of_prices(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        base = {"utc": "2026-11-22T15:00:00Z", "h": "Arsenal",
                "a": "Chelsea", "odds": None}
        for prices in ([1.8, 3.7], [1.8, 3.7, 4.5, 5.0], []):
            with self.subTest(prices=prices):
                predictions = {"1": dict(base)}
                events = [{"home": "Arsenal", "away": "Chelsea",
                           "commence": "2026-11-22T15:00:00Z", "odds": prices}]
                self.assertEqual(backfill_market_odds(
                    predictions, events, "2026-11-11T07:00:00Z", now,
                    lambda a, b: a == b), 0)
                self.assertIsNone(predictions["1"]["odds"])

    def test_rejects_future_dated_odds_snapshot(self):
        from datetime import datetime, timezone
        predictions = {"1": {"utc": "2026-11-22T15:00:00Z", "h": "Arsenal",
                             "a": "Chelsea", "odds": None}}
        events = [{"home": "Arsenal", "away": "Chelsea",
                   "commence": "2026-11-22T15:00:00Z", "odds": [1.8, 3.7, 4.5]}]
        count = backfill_market_odds(
            predictions, events, "2026-11-12T07:00:00Z",
            datetime(2026, 11, 11, 12, tzinfo=timezone.utc), lambda a, b: a == b)
        self.assertEqual(count, 0)
        self.assertIsNone(predictions["1"]["odds"])


if __name__ == "__main__":
    unittest.main()

class TeamNameMatchingTests(unittest.TestCase):
    def test_normalization_accepts_accents_punctuation_and_club_suffixes(self):
        from pitchiq_data import same_team_name
        self.assertTrue(same_team_name("Bodø/Glimt", "Bodo Glimt"))
        self.assertTrue(same_team_name("Arsenal FC", "Arsenal"))
        self.assertTrue(same_team_name("Paris Saint-Germain", "Paris Saint Germain"))

    def test_ambiguous_substrings_and_similar_names_are_not_matched(self):
        from pitchiq_data import same_team_name
        self.assertFalse(same_team_name("City", "Manchester City"))
        self.assertFalse(same_team_name("United", "Manchester United"))
        self.assertFalse(same_team_name("Arsenal", "Arsenal Women"))
        self.assertFalse(same_team_name("Inter", "Inter Miami"))
        self.assertFalse(same_team_name("", "Arsenal"))

