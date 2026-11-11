"""Offline unit tests for the PitchIQ probability model."""
import math
import unittest

from pitchiq_model import ppg, pois, predict, tau


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
