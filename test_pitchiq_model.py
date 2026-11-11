"""Offline unit tests for the PitchIQ probability model."""
import math
import unittest

from pitchiq_model import ppg, pois, predict, tau
from model_metrics import evaluate



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
        self.assertAlmostEqual(result["home_goals_mae"], 0.2, places=4)
        self.assertAlmostEqual(result["away_goals_mae"], 0.1, places=4)

    def test_invalid_or_incomplete_records_are_skipped(self):
        result = evaluate([{"final": None, "p": {}}, {"final": [1, 0], "p": {"ph": 0.5}}])
        self.assertEqual(result["matches"], 0)
        self.assertIsNone(result["accuracy"])

    def test_probabilities_must_be_valid(self):
        result = evaluate([{"final": [1, 0], "p": {"ph": 0.8, "pd": 0.8, "pa": 0.1}}])
        self.assertEqual(result["matches"], 0)


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
        self.assertAlmostEqual(tau(0, 0, 1.5, 1.2, -0.1), 1.15)
        self.assertAlmostEqual(tau(0, 1, 1.5, 1.2, -0.1), 0.85)
        self.assertAlmostEqual(tau(1, 0, 1.5, 1.2, -0.1), 0.88)
        self.assertAlmostEqual(tau(1, 1, 1.5, 1.2, -0.1), 1.1)
        self.assertEqual(tau(2, 2, 1.5, 1.2, -0.1), 1)

    def test_three_way_probabilities_sum_to_one(self):
        result = predict(self.stats)
        self.assertAlmostEqual(result["ph"] + result["pd"] + result["pa"], 1.0, delta=0.001)

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
