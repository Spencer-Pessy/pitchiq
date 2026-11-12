"""Offline unit tests for the PitchIQ probability model."""
import math
import unittest
from unittest.mock import patch

from pitchiq_model import ppg, pois, predict, tau
from model_metrics import evaluate, input_diagnostics, binary_market_metrics, baseline_comparison, outcome_class_metrics, ablation_comparison, wilson_interval, paired_bootstrap_interval, expected_goals_calibration, scoreline_baseline_comparison



class MetricsTests(unittest.TestCase):
    def test_evaluate_known_predictions(self):
        rows = [
            {"final": [2, 0], "p": {"ph": 0.7, "pd": 0.2, "pa": 0.1, "lh": 1.8, "la": 0.8}},
            {"final": [1, 1], "p": {"ph": 0.2, "pd": 0.6, "pa": 0.2, "lh": 1.0, "la": 1.0}},
        ]
        result = evaluate(rows)
        self.assertEqual(result["matches"], 2)
        self.assertEqual(result["accuracy"], 1.0)
        self.assertIsNotNone(result["brier"])
        self.assertIsNotNone(result["log_loss"])
        self.assertEqual(sum(x["matches"] for x in result["confidence_bins"]), 2)
        self.assertTrue(all(0 <= x["accuracy"] <= 1 for x in result["confidence_bins"]))
        self.assertAlmostEqual(result["expected_calibration_error"], 0.35, places=4)
        self.assertAlmostEqual(result["max_calibration_gap"], 0.4, places=4)
        self.assertAlmostEqual(result["home_goals_mae"], 0.1, places=4)
        self.assertAlmostEqual(result["away_goals_mae"], 0.4, places=4)
        self.assertAlmostEqual(result["home_goals_bias"], -0.1, places=4)
        self.assertAlmostEqual(result["away_goals_bias"], 0.4, places=4)



    def test_paired_bootstrap_interval_is_deterministic_and_requires_pairs(self):
        self.assertIsNone(paired_bootstrap_interval([0.1]))
        values = [0.1, -0.05, 0.02, 0.08, -0.01]
        first = paired_bootstrap_interval(values)
        second = paired_bootstrap_interval(values)
        self.assertEqual(first, second)
        self.assertLessEqual(first[0], first[1])

    def test_ablation_replays_only_schema_two_snapshots_on_same_sample(self):
        stats = {
            "h": {"gf": 1.7, "ga": 0.9, "elo": 1620, "form": "WWDLW"},
            "a": {"gf": 1.2, "ga": 1.4, "elo": 1510, "form": "LDWDL"},
            "lh": 1.5, "la": 1.2,
        }
        calibration = {"kh": 1.05, "ka": 0.97}
        forecast = predict(stats, calibration)
        row = {
            "final": [2, 0],
            "inputs": {"schema": 2, "home": stats["h"], "away": stats["a"],
                       "league_home": stats["lh"], "league_away": stats["la"],
                       "calibration": calibration},
            "p": forecast,
        }
        legacy = {"final": [1, 0], "inputs": {"schema": 1}}
        result = ablation_comparison([row, legacy])
        self.assertEqual(result["matches"], 1)
        self.assertEqual(set(result["variants"]), {
            "full_model", "without_elo", "without_form", "without_elo_or_form"
        })
        self.assertEqual(result["variants"]["full_model"]["matches"], 1)
        self.assertEqual(result["variants"]["full_model"]["brier_delta_vs_full"], 0.0)
        self.assertIsNone(result["variants"]["without_elo"]["brier_delta_ci_95"])
        self.assertTrue(all(value["matches"] == 1 for value in result["variants"].values()))
        self.assertEqual(result["variants"]["full_model"]["accuracy"], 1.0)

    def test_ablation_drops_match_from_every_variant_if_one_variant_is_invalid(self):
        stats = {
            "h": {"gf": 1.7, "ga": 0.9, "elo": 1620, "form": "WWDLW"},
            "a": {"gf": 1.2, "ga": 1.4, "elo": 1510, "form": "LDWDL"},
            "lh": 1.5, "la": 1.2,
        }
        calibration = {"kh": 1.05, "ka": 0.97}
        valid = predict(stats, calibration)

        def controlled_predict(_stats, _calibration, use_elo=True, use_form=True):
            if not use_elo:
                return {"ph": 2.0, "pd": 0.0, "pa": 0.0}
            return valid

        row = {
            "final": [2, 0],
            "inputs": {"schema": 2, "home": stats["h"], "away": stats["a"],
                       "league_home": stats["lh"], "league_away": stats["la"],
                       "calibration": calibration},
            "p": valid,
        }
        with patch("model_metrics.model_predict", side_effect=controlled_predict):
            result = ablation_comparison([row])
        self.assertEqual(result["matches"], 0)
        self.assertTrue(all(value["matches"] == 0 for value in result["variants"].values()))

    def test_ablation_comparison_is_empty_without_schema_two_snapshots(self):
        result = ablation_comparison([
            {"final": [1, 0], "inputs": {"schema": 1}},
            {"final": None, "inputs": {"schema": 2}},
        ])
        self.assertEqual(result["matches"], 0)
        self.assertTrue(all(row["brier"] is None for row in result["variants"].values()))

    def test_outcome_class_metrics_scores_each_one_vs_rest_probability(self):
        rows = [
            {"final": [2, 0], "p": {"ph": 0.8, "pd": 0.1, "pa": 0.1}},
            {"final": [0, 1], "p": {"ph": 0.2, "pd": 0.3, "pa": 0.5}},
            {"final": [1, 2], "p": {"ph": 0.3, "pd": 0.2, "pa": 0.5}},
        ]
        result = outcome_class_metrics(rows)
        self.assertEqual(result["home"]["matches"], 3)
        self.assertAlmostEqual(result["home"]["mean_probability"], 0.4333, places=4)
        self.assertAlmostEqual(result["home"]["observed_rate"], 0.3333, places=4)
        self.assertAlmostEqual(result["home"]["brier"], 0.0567, places=4)
        self.assertAlmostEqual(result["home"]["expected_calibration_error"], 0.2333, places=4)
        self.assertEqual(result["draw"]["matches"], 3)
        self.assertEqual(result["away"]["matches"], 3)

    def test_outcome_class_metrics_returns_empty_values_for_no_valid_rows(self):
        result = outcome_class_metrics([{"final": None, "p": {}}])
        self.assertEqual(set(result), {"home", "draw", "away"})
        self.assertTrue(all(row["matches"] == 0 and row["brier"] is None
                            for row in result.values()))

    def test_baseline_comparison_uses_prior_results_and_de_vigged_odds(self):
        rows = [
            {"utc": "2026-01-01T12:00:00Z", "final": [1, 0],
             "p": {"ph": 0.7, "pd": 0.2, "pa": 0.1}, "odds": [2.0, 4.0, 5.0]},
            {"utc": "2026-01-02T12:00:00Z", "final": [0, 1],
             "p": {"ph": 0.1, "pd": 0.2, "pa": 0.7}, "odds": [5.0, 4.0, 2.0]},
            {"utc": "2026-01-02T12:00:00Z", "final": [1, 1],
             "p": {"ph": 0.2, "pd": 0.7, "pa": 0.1}, "odds": [4.0, 2.0, 5.0]},
            {"utc": "2026-01-03T12:00:00Z", "final": [0, 0],
             "p": {"ph": 0.2, "pd": 0.6, "pa": 0.2}, "odds": None},
        ]
        result = baseline_comparison(rows)
        self.assertEqual(result["rolling_prior"]["matches"], 4)
        self.assertAlmostEqual(result["rolling_prior"]["brier"], 0.7708, places=4)
        self.assertEqual(result["rolling_prior"]["accuracy"], 0.25)
        self.assertEqual(result["model_on_odds_sample"]["matches"], 3)
        self.assertEqual(result["bookmaker_consensus"]["matches"], 3)
        self.assertIsNotNone(result["model_minus_bookmaker_brier"])
        self.assertIsNotNone(result["model_minus_bookmaker_log_loss"])
        self.assertIsNotNone(result["model_minus_bookmaker_brier_ci_95"])
        self.assertIsNotNone(result["model_minus_bookmaker_log_loss_ci_95"])
        self.assertIsNotNone(result["model_minus_competition_prior_brier_ci_95"])
        reversed_result = baseline_comparison(list(reversed(rows)))
        self.assertEqual(result, reversed_result)

    def test_rolling_baseline_excludes_undated_rows_and_orders_timezone_offsets(self):
        rows = [
            {"utc": "2026-01-02T07:00:00Z", "final": [1, 0],
             "p": {"ph": 0.4, "pd": 0.3, "pa": 0.3}},
            {"utc": "2026-01-02T09:00:00+14:00", "final": [0, 1],
             "p": {"ph": 0.3, "pd": 0.3, "pa": 0.4}},
            {"utc": "2026-01-02T08:00:00Z", "final": [1, 1],
             "p": {"ph": 0.3, "pd": 0.4, "pa": 0.3}},
            {"final": [10, 0], "p": {"ph": 0.99, "pd": 0.005, "pa": 0.005}},
            {"utc": "not-a-date", "made": "also-not-a-date", "final": [10, 0],
             "p": {"ph": 0.99, "pd": 0.005, "pa": 0.005}},
        ]
        result = baseline_comparison(rows)
        self.assertEqual(result["rolling_prior"]["matches"], 3)
        self.assertAlmostEqual(result["rolling_prior"]["brier"], 0.8339, places=4)

    def test_competition_rolling_prior_is_smoothed_and_leakage_safe(self):
        rows = [
            {"utc": "2026-01-01T12:00:00Z", "code": "PL", "final": [1, 0],
             "p": {"ph": 0.7, "pd": 0.2, "pa": 0.1}},
            {"utc": "2026-01-02T12:00:00Z", "code": "PL", "final": [0, 1],
             "p": {"ph": 0.1, "pd": 0.2, "pa": 0.7}},
            {"utc": "2026-01-02T12:00:00Z", "code": "SA", "final": [1, 1],
             "p": {"ph": 0.2, "pd": 0.7, "pa": 0.1}},
            {"utc": "2026-01-03T12:00:00Z", "code": "PL", "final": [1, 0],
             "p": {"ph": 0.7, "pd": 0.2, "pa": 0.1}},
        ]
        result = baseline_comparison(rows)
        self.assertEqual(result["competition_rolling_prior"]["matches"], 4)
        self.assertEqual(
            result["competition_rolling_prior"],
            baseline_comparison(list(reversed(rows)))["competition_rolling_prior"],
        )
        self.assertNotEqual(
            result["competition_rolling_prior"]["brier"],
            result["rolling_prior"]["brier"],
        )

    def test_baseline_comparison_ignores_invalid_odds_and_unfinished_matches(self):
        rows = [
            {"utc": "2026-01-01T12:00:00Z", "final": [1, 0],
             "p": {"ph": 0.7, "pd": 0.2, "pa": 0.1}, "odds": [1.0, 4.0, 5.0]},
            {"utc": "2026-01-02T12:00:00Z", "final": None,
             "p": {"ph": 0.5, "pd": 0.3, "pa": 0.2}, "odds": [2.0, 3.0, 4.0]},
        ]
        result = baseline_comparison(rows)
        self.assertEqual(result["rolling_prior"]["matches"], 1)
        self.assertEqual(result["bookmaker_consensus"]["matches"], 0)
        self.assertEqual(result["model_on_odds_sample"]["matches"], 0)

    def test_binary_market_metrics_score_probabilities_and_calibration(self):
        rows = [
            {"final": [2, 0], "p": {"o25": 0.8, "bt": 0.2}},
            {"final": [1, 1], "p": {"o25": 0.2, "bt": 0.8}},
            {"final": [1, 0], "p": {"o25": 0.5, "bt": 0.5}},
        ]
        over = binary_market_metrics(rows, "o25")
        btts = binary_market_metrics(rows, "bt")
        self.assertEqual(over["matches"], 3)
        self.assertAlmostEqual(over["accuracy"], 1 / 3, places=4)
        self.assertAlmostEqual(over["brier"], 0.31, places=4)
        self.assertAlmostEqual(over["expected_calibration_error"], 0.5, places=4)
        self.assertEqual(btts["matches"], 3)
        self.assertAlmostEqual(btts["accuracy"], 2 / 3, places=4)

    def test_binary_market_metrics_ignores_missing_and_invalid_probabilities(self):
        result = binary_market_metrics([
            {"final": [1, 0], "p": {"o25": None}},
            {"final": [1, 0], "p": {"o25": 1.2}},
        ], "o25")
        self.assertEqual(result["matches"], 0)
        self.assertIsNone(result["brier"])
    def test_input_diagnostics_group_saved_venue_samples(self):
        rows = [
            {"final": [2, 0], "p": {"ph": 0.7, "pd": 0.2, "pa": 0.1, "lh": 1.8, "la": 0.8},
             "inputs": {"schema": 1, "home": {"venue_matches": 2, "form": "WWD"},
                        "away": {"venue_matches": 7, "form": "LLD"}}},
            {"final": [0, 1], "p": {"ph": 0.2, "pd": 0.2, "pa": 0.6, "lh": 1.0, "la": 1.4},
             "inputs": {"schema": 2, "home": {"venue_matches": 4, "form": "LLL"},
                        "away": {"venue_matches": 12, "form": "WWW"}}},
            {"final": [1, 1], "p": {"ph": 0.2, "pd": 0.6, "pa": 0.2, "lh": 1.0, "la": 1.0}},
        ]
        result = input_diagnostics(rows)
        self.assertEqual(result["completed_forecasts"], 3)
        self.assertEqual(result["snapshot_forecasts"], 2)
        self.assertEqual(result["missing_or_invalid_snapshots"], 1)
        home = result["groups"]["home_venue_sample"]
        self.assertEqual(home[0]["matches"], 1)
        self.assertEqual(home[1]["matches"], 1)
        self.assertEqual(home[0]["accuracy"], 1.0)
        self.assertEqual(result["groups"]["away_venue_sample"][2]["matches"], 1)
        self.assertEqual(result["groups"]["home_form_points"][0]["matches"], 1)


    def test_input_diagnostics_excludes_missing_form_instead_of_treating_it_as_losses(self):
        rows = [{
            "final": [1, 0],
            "p": {"ph": 0.6, "pd": 0.2, "pa": 0.2},
            "inputs": {"schema": 1,
                "home": {"venue_matches": 4, "form": ""},
                "away": {"venue_matches": 5, "form": "WWD"}},
        }]
        result = input_diagnostics(rows)
        self.assertEqual(result["snapshot_forecasts"], 1)
        self.assertEqual(result["groups"]["home_form_points"][0]["matches"], 0)
        self.assertEqual(result["groups"]["away_form_points"][1]["matches"], 1)

    def test_input_diagnostics_skips_malformed_nested_team_snapshots(self):
        result = input_diagnostics([{
            "final": [1, 0], "p": {"ph": 0.6, "pd": 0.2, "pa": 0.2},
            "inputs": {"schema": 2, "home": "broken", "away": ["broken"]},
        }])
        self.assertEqual(result["snapshot_forecasts"], 1)
        self.assertTrue(all(row["matches"] == 0
                            for group in result["groups"].values() for row in group))
        self.assertTrue(all(row["matches"] == 0 for row in result["venue_support"]))
        self.assertEqual(sum(row["matches"] for row in result["form_edge"]), 0)

    def test_input_diagnostics_rejects_fractional_and_boolean_venue_counts(self):
        rows = [{
            "final": [1, 0], "p": {"ph": 0.6, "pd": 0.2, "pa": 0.2},
            "inputs": {"schema": 2,
                       "home": {"venue_matches": 2.5, "form": "WW"},
                       "away": {"venue_matches": True, "form": "LL"}},
        }]
        result = input_diagnostics(rows)
        self.assertEqual(result["snapshot_forecasts"], 1)
        self.assertTrue(all(row["matches"] == 0
                            for row in result["groups"]["home_venue_sample"]))
        self.assertTrue(all(row["matches"] == 0
                            for row in result["groups"]["away_venue_sample"]))
        self.assertTrue(all(row["matches"] == 0 for row in result["venue_support"]))

    def test_input_diagnostics_ignores_malformed_snapshots(self):
        result = input_diagnostics([
            {"final": [1, 0], "p": {"ph": 0.6, "pd": 0.2, "pa": 0.2},
             "inputs": {"schema": 99, "home": {"venue_matches": 3}}},
        ])
        self.assertEqual(result["snapshot_forecasts"], 0)
        self.assertEqual(result["missing_or_invalid_snapshots"], 1)
        self.assertTrue(all(row["matches"] == 0
                            for row in result["groups"]["home_venue_sample"]))




    def test_wilson_accuracy_interval_reflects_small_sample_uncertainty(self):
        self.assertEqual(wilson_interval(0, 0), None)
        self.assertEqual(wilson_interval(0, 10), [0.0, 0.2775])
        self.assertEqual(wilson_interval(10, 10), [0.7225, 1.0])
        interval = wilson_interval(1, 2)
        self.assertAlmostEqual(interval[0], 0.0945, places=4)
        self.assertAlmostEqual(interval[1], 0.9055, places=4)

    def test_evaluate_returns_accuracy_confidence_interval(self):
        rows = [
            {"final": [2, 0], "p": {"ph": 0.7, "pd": 0.2, "pa": 0.1}},
            {"final": [0, 2], "p": {"ph": 0.7, "pd": 0.2, "pa": 0.1}},
        ]
        result = evaluate(rows)
        self.assertEqual(result["accuracy"], 0.5)
        self.assertEqual(result["accuracy_ci_95"], wilson_interval(1, 2))


class ExpectedGoalsCalibrationTests(unittest.TestCase):
    def test_expected_goals_calibration_groups_home_and_away_separately(self):
        rows = [
            {"final": [2, 0], "p": {"lh": 1.8, "la": 0.4}},
            {"final": [1, 2], "p": {"lh": 1.2, "la": 1.7}},
            {"final": [3, 1], "p": {"lh": 2.2, "la": 0.8}},
            {"final": [0, 0], "p": {"lh": 1.8, "la": 0.4}},
        ]
        result = expected_goals_calibration(rows)
        home = next(x for x in result["home"] if x["band"] == "1.50–1.99")
        away = next(x for x in result["away"] if x["band"] == "0–0.49")
        self.assertEqual(home["matches"], 2)
        self.assertAlmostEqual(home["mean_predicted"], 1.8)
        self.assertAlmostEqual(home["mean_actual"], 1.0)
        self.assertAlmostEqual(home["bias"], 0.8)
        self.assertAlmostEqual(home["mae"], 1.0)
        self.assertEqual(away["matches"], 2)
        self.assertAlmostEqual(away["mean_actual"], 0.0)
        self.assertEqual(home["interpretation"], "monitoring_only")

    def test_expected_goals_calibration_ignores_invalid_or_unfinished_rows(self):
        rows = [
            {"final": None, "p": {"lh": 1.0, "la": 1.0}},
            {"final": [1, 0], "p": {"lh": float("nan"), "la": 1.0}},
            {"final": [1, 0], "p": {"lh": -1, "la": 1.0}},
            {"final": [1, 0], "p": {"lh": 1.0}},
        ]
        result = expected_goals_calibration(rows)
        self.assertEqual(sum(x["matches"] for x in result["home"]), 1)
        self.assertEqual(sum(x["matches"] for x in result["away"]), 2)


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.stats = {
            "h": {"gf": 1.7, "ga": 0.9, "elo": 1620, "form": "WWDLW"},
            "a": {"gf": 1.2, "ga": 1.4, "elo": 1510, "form": "LDWDL"},
            "lh": 1.5,
            "la": 1.2,
        }

    def test_points_per_game(self):
        self.assertEqual(ppg("WWDLW"), 2.0)
        self.assertEqual(ppg(""), 1.5)
        self.assertEqual(ppg("LLLLL"), 0.0)
        self.assertEqual(ppg("WWWWWW"), 3.0)
        self.assertEqual(ppg("W W D L W"), 2.0)
        self.assertEqual(ppg("abcWWDL"), 1.75)

    def test_poisson_distribution_value(self):
        self.assertAlmostEqual(pois(1.0, 0), math.exp(-1), places=12)
        self.assertAlmostEqual(pois(1.0, 1), math.exp(-1), places=12)

    def test_dixon_coles_adjustments(self):
        self.assertAlmostEqual(tau(0, 0, 1.5, 1.2, -0.1), 1.18)
        self.assertAlmostEqual(tau(0, 1, 1.5, 1.2, -0.1), 0.85)
        self.assertAlmostEqual(tau(1, 0, 1.5, 1.2, -0.1), 0.88)
        self.assertAlmostEqual(tau(1, 1, 1.5, 1.2, -0.1), 1.1)
        self.assertEqual(tau(2, 2, 1.5, 1.2, -0.1), 1)

    def test_three_way_probabilities_sum_to_one(self):
        result = predict(self.stats)
        self.assertAlmostEqual(result["ph"] + result["pd"] + result["pa"], 1.0, delta=0.001)

    def test_reference_forecast_is_stable(self):
        result = predict(self.stats)
        self.assertEqual(result["ph"], 0.5597)
        self.assertEqual(result["pd"], 0.2637)
        self.assertEqual(result["pa"], 0.1766)
        self.assertEqual(result["o25"], 0.4638)
        self.assertEqual(result["bt"], 0.477)

    def test_all_market_probabilities_are_bounded(self):
        result = predict(self.stats)
        for key in ("ph", "pd", "pa", "o25", "bt"):
            self.assertGreaterEqual(result[key], 0.0, key)
            self.assertLessEqual(result[key], 1.0, key)

    def test_expected_goals_are_positive_and_raw_rates_preserved(self):
        result = predict(self.stats)
        self.assertGreater(result["lh"], 0)
        self.assertGreater(result["la"], 0)
        self.assertGreater(result["rlh"], 0)
        self.assertGreater(result["rla"], 0)
        self.assertAlmostEqual(result["lh"], result["rlh"], places=4)

    def test_elo_ablation_removes_rating_edge(self):
        full = predict(self.stats)
        no_elo = predict(self.stats, use_elo=False)
        self.assertNotEqual(full["lh"], no_elo["lh"])
        self.assertNotEqual(full["ph"], no_elo["ph"])

    def test_form_ablation_removes_recent_form_edge(self):
        full = predict(self.stats)
        no_form = predict(self.stats, use_form=False)
        self.assertNotEqual(full["lh"], no_form["lh"])
        self.assertNotEqual(full["ph"], no_form["ph"])

    def test_ablation_switches_do_not_change_default_forecast(self):
        self.assertEqual(predict(self.stats), predict(self.stats, use_elo=True, use_form=True))

    def test_manual_absences_reduce_the_affected_team_goal_rate(self):
        baseline = predict(self.stats)
        home_out = dict(self.stats)
        home_out["h"] = {**self.stats["h"], "out": 2}
        away_out = dict(self.stats)
        away_out["a"] = {**self.stats["a"], "out": 3}
        self.assertLess(predict(home_out)["lh"], baseline["lh"])
        self.assertAlmostEqual(predict(home_out)["la"], baseline["la"])
        self.assertLess(predict(away_out)["la"], baseline["la"])
        self.assertAlmostEqual(predict(away_out)["lh"], baseline["lh"])

    def test_calibration_changes_rates_not_raw_rates(self):
        baseline = predict(self.stats)
        adjusted = predict(self.stats, {"kh": 1.1, "ka": 0.9})
        self.assertGreater(adjusted["lh"], baseline["lh"])
        self.assertLess(adjusted["la"], baseline["la"])
        self.assertEqual(adjusted["rlh"], baseline["rlh"])
        self.assertEqual(adjusted["rla"], baseline["rla"])

    def test_low_attack_and_invalidly_small_league_averages_stay_safe(self):
        stats = {
            "h": {"gf": 0, "ga": 0, "elo": 1500, "form": ""},
            "a": {"gf": 0, "ga": 0, "elo": 1500, "form": ""},
            "lh": 0, "la": 0,
        }
        result = predict(stats)
        self.assertGreater(result["lh"], 0)
        self.assertGreater(result["la"], 0)
        self.assertAlmostEqual(result["ph"] + result["pd"] + result["pa"], 1.0, delta=0.001)


class FinalScoreValidationTests(unittest.TestCase):
    def test_all_outcome_metrics_reject_fractional_boolean_and_negative_scores(self):
        invalid = [
            {"final": [1.5, 0], "p": {"ph": .6, "pd": .2, "pa": .2,
                                      "o25": .5, "bt": .5}},
            {"final": [True, 0], "p": {"ph": .6, "pd": .2, "pa": .2,
                                      "o25": .5, "bt": .5}},
            {"final": [-1, 0], "p": {"ph": .6, "pd": .2, "pa": .2,
                                     "o25": .5, "bt": .5}},
        ]
        self.assertEqual(evaluate(invalid)["matches"], 0)
        self.assertEqual(sum(row["matches"] for row in outcome_class_metrics(invalid).values()), 0)
        self.assertEqual(baseline_comparison(invalid)["rolling_prior"]["matches"], 0)
        self.assertEqual(binary_market_metrics(invalid, "o25")["matches"], 0)
        self.assertEqual(scoreline_baseline_comparison(invalid)["matches"], 0)
        goal_metrics = expected_goals_calibration(invalid)
        self.assertTrue(all(row["matches"] == 0
                            for rows in goal_metrics.values() for row in rows))

    def test_numeric_overflow_is_excluded_without_crashing_metrics(self):
        huge = 10 ** 10000
        row = {"final": [1, 0], "p": {"ph": huge, "pd": 0, "pa": 0,
                                       "lh": huge, "la": 1, "o25": huge,
                                       "bt": 0}}
        self.assertEqual(evaluate([row])["matches"], 0)
        self.assertEqual(sum(x["matches"] for x in outcome_class_metrics([row]).values()), 0)
        self.assertEqual(baseline_comparison([row])["rolling_prior"]["matches"], 0)
        self.assertEqual(binary_market_metrics([row], "o25")["matches"], 0)
        goal_metrics = expected_goals_calibration([row])
        self.assertTrue(all(x["matches"] == 0 for x in goal_metrics["home"]))
        self.assertEqual(sum(x["matches"] for x in goal_metrics["away"]), 1)
        snapshot_row = {
            "final": [1, 0], "p": {"ph": .6, "pd": .2, "pa": .2},
            "inputs": {"schema": 2, "home": {"venue_matches": 2, "form": "WW"},
                       "away": {"venue_matches": 2, "form": "LL"},
                       "league_home": huge, "league_away": 1, "calibration": {}},
        }
        self.assertEqual(ablation_comparison([snapshot_row])["matches"], 0)

    def test_valid_integer_scores_remain_in_metrics(self):
        rows = [{"final": [2, 1], "p": {"ph": .6, "pd": .2, "pa": .2,
                                        "lh": 1.8, "la": 1.1,
                                        "o25": .7, "bt": .6}}]
        self.assertEqual(evaluate(rows)["matches"], 1)
        self.assertEqual(sum(row["matches"] for row in outcome_class_metrics(rows).values()), 3)
        self.assertEqual(binary_market_metrics(rows, "o25")["matches"], 1)


class ScorelineBaselineComparisonTests(unittest.TestCase):
    def test_identical_rates_produce_a_valid_paired_comparison(self):
        rows = [
            {"final": [0, 0], "p": {"lh": 1.5, "la": 1.2}},
            {"final": [1, 0], "p": {"lh": 1.5, "la": 1.2}},
            {"final": [2, 1], "p": {"lh": 1.5, "la": 1.2}},
            {"final": [1, 1], "p": {"lh": 1.5, "la": 1.2}},
        ]
        result = scoreline_baseline_comparison(rows)
        self.assertEqual(result["matches"], 4)
        self.assertEqual(result["excluded"], 0)
        self.assertIsNotNone(result["delta_ci_95"])
        self.assertAlmostEqual(
            result["mean_delta_dc_minus_independent"],
            result["dixon_coles_nll"] - result["independent_poisson_nll"],
            places=3,
        )
        self.assertEqual(
            result["dc_better"] + result["independent_better"] + result["ties"], 4
        )

    def test_scoreline_baseline_excludes_out_of_grid_and_invalid_rates(self):
        rows = [
            {"final": [8, 0], "p": {"lh": 1.5, "la": 1.2}},
            {"final": [1, 0], "p": {"lh": 0, "la": 1.2}},
            {"final": [1, 0], "p": {"lh": float("nan"), "la": 1.2}},
            {"final": [1, 0], "p": {"lh": 1.5, "la": 1.2}},
            {"final": None, "p": {"lh": 1.5, "la": 1.2}},
        ]
        result = scoreline_baseline_comparison(rows)
        self.assertEqual(result["matches"], 1)
        self.assertEqual(result["excluded"], 3)

    def test_scoreline_baseline_requires_no_unpaired_claim_with_one_match(self):
        result = scoreline_baseline_comparison([
            {"final": [0, 0], "p": {"lh": 1.5, "la": 1.2}}
        ])
        self.assertIsNone(result["delta_ci_95"])
        self.assertEqual(result["interpretation"], "no_clear_difference")


if __name__ == "__main__":
    unittest.main(verbosity=2)
