"""Offline unit tests for the PitchIQ probability model."""
import math
import unittest

from pitchiq_model import ppg, pois, predict, tau
from model_metrics import evaluate, input_diagnostics, binary_market_metrics



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


    def test_binary_market_metrics_score_probabilities_and_calibration(self):
        rows = [
            {"final": [2, 0], "p": {"o25": 0.8, "bt": 0.2}},
            {"final": [1, 1], "p": {"o25": 0.2, "bt": 0.8}},
            {"final": [1, 0], "p": {"o25": 0.5, "bt": 0.5}},
        ]
        over = binary_market_metrics(rows, "o25")
        btts = binary_market_metrics(rows, "bt")
        self.assertEqual(over["matches"], 3)
        self.assertAlmostEqual(over["accuracy"], 2 / 3, places=4)
        self.assertAlmostEqual(over["brier"], 0.11, places=4)
        self.assertAlmostEqual(over["expected_calibration_error"], 0.3, places=4)
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
             "inputs": {"schema": 1, "home": {"venue_matches": 4, "form": "LLL"},
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

    def test_input_diagnostics_ignores_malformed_snapshots(self):
        result = input_diagnostics([
            {"final": [1, 0], "p": {"ph": 0.6, "pd": 0.2, "pa": 0.2},
             "inputs": {"schema": 99, "home": {"venue_matches": 3}}},
        ])
        self.assertEqual(result["snapshot_forecasts"], 0)
        self.assertEqual(result["missing_or_invalid_snapshots"], 1)
        self.assertTrue(all(row["matches"] == 0
                            for row in result["groups"]["home_venue_sample"]))



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


if __name__ == "__main__":
    unittest.main(verbosity=2)
