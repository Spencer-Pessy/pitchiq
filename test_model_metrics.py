import math
import unittest

from model_metrics import (
    _final_score,
    _forecast_available_datetime,
    baseline_comparison,
    binary_market_metrics,
    expected_goals_calibration,
    outcome_class_metrics,
    paired_bootstrap_interval,
    scoreline_baseline_comparison,
    wilson_interval,
)


def forecast(match_id, kickoff, made, final, probabilities=None, odds=None, goals=None):
    probabilities = probabilities or {"ph": 0.6, "pd": 0.2, "pa": 0.2,
                                      "lh": 1.2, "la": 0.8, "o25": 0.55, "bt": 0.5}
    return {
        "id": match_id,
        "utc": kickoff,
        "made": made,
        "final": final,
        "code": "PL",
        "p": probabilities,
        "odds": odds,
    }


class ForecastValidationTests(unittest.TestCase):
    def test_final_score_accepts_only_nonnegative_integer_scores(self):
        self.assertEqual(_final_score({"final": [2, "1"]}), (2, 1))
        for value in ([True, 0], [1.5, 0], [-1, 0], [float("nan"), 0],
                      [1], None, "1-0"):
            with self.subTest(value=value):
                self.assertIsNone(_final_score({"final": value}))

    def test_legacy_forecast_timestamp_falls_back_to_kickoff(self):
        row = {"utc": "2026-01-02T12:00:00Z"}
        self.assertEqual(
            _forecast_available_datetime(row).isoformat(),
            "2026-01-02T12:00:00+00:00",
        )

    def test_wilson_interval_handles_boundaries_and_invalid_counts(self):
        self.assertEqual(wilson_interval(0, 10)[0], 0.0)
        self.assertEqual(wilson_interval(10, 10)[1], 1.0)
        self.assertIsNone(wilson_interval(11, 10))
        self.assertIsNone(wilson_interval(0, 0))


class ProbabilityMetricTests(unittest.TestCase):
    def test_outcome_class_metrics_use_completed_valid_forecasts(self):
        rows = [
            forecast(1, "2026-01-01T10:00:00Z", "2026-01-01T08:00:00Z", [2, 0]),
            forecast(2, "2026-01-02T10:00:00Z", "2026-01-01T08:00:00Z", [0, 1],
                     probabilities={"ph": 0.2, "pd": 0.3, "pa": 0.5}),
            forecast(3, "2026-01-03T10:00:00Z", "2026-01-01T08:00:00Z", [True, 0]),
        ]
        result = outcome_class_metrics(rows)
        self.assertEqual(result["home"]["matches"], 2)
        self.assertEqual(result["home"]["observed_rate"], 0.5)
        self.assertEqual(result["away"]["matches"], 2)
        self.assertIsNotNone(result["draw"]["brier"])

    def test_binary_market_metrics_score_over_25_and_btts(self):
        rows = [
            forecast(1, "2026-01-01T10:00:00Z", "2026-01-01T08:00:00Z", [2, 1]),
            forecast(2, "2026-01-02T10:00:00Z", "2026-01-01T08:00:00Z", [0, 0],
                     probabilities={"ph": 0.5, "pd": 0.3, "pa": 0.2,
                                    "lh": 1.0, "la": 0.8, "o25": 0.2, "bt": 0.1}),
        ]
        over = binary_market_metrics(rows, "o25")
        btts = binary_market_metrics(rows, "bt")
        self.assertEqual(over["matches"], 2)
        self.assertEqual(over["accuracy"], 1.0)
        self.assertEqual(btts["matches"], 2)
        self.assertEqual(btts["accuracy"], 1.0)

    def test_paired_bootstrap_is_deterministic_and_order_invariant(self):
        values = [0.1, -0.2, 0.05, 0.3, -0.1]
        self.assertEqual(
            paired_bootstrap_interval(values),
            paired_bootstrap_interval(list(reversed(values))),
        )
        self.assertIsNone(paired_bootstrap_interval([0.1]))


class NoLookAheadEvaluationTests(unittest.TestCase):
    def test_rolling_baseline_excludes_results_not_yet_available(self):
        first = forecast(
            10, "2026-01-01T10:00:00Z", "2026-01-01T08:00:00Z", [1, 0]
        )
        second = forecast(
            11, "2026-01-02T10:00:00Z", "2026-01-01T12:59:00Z", [0, 1]
        )
        result = baseline_comparison([first, second])
        # The first result is not considered available until 13:00 UTC.
        # Both forecasts therefore use the uniform, smoothed prior.
        self.assertEqual(result["rolling_prior"]["matches"], 2)
        self.assertAlmostEqual(result["rolling_prior"]["brier"], 2 / 3, places=4)

    def test_rolling_baseline_includes_a_result_once_the_three_hour_buffer_passes(self):
        first = forecast(
            10, "2026-01-01T10:00:00Z", "2026-01-01T08:00:00Z", [1, 0]
        )
        second = forecast(
            11, "2026-01-02T10:00:00Z", "2026-01-01T13:00:00Z", [0, 1]
        )
        result = baseline_comparison([first, second])
        # At 13:00 UTC the first result enters the information set for forecast 2.
        self.assertAlmostEqual(result["rolling_prior"]["brier"], (2 / 3 + 0.875) / 2, places=4)


class GoalAndScorelineDiagnosticsTests(unittest.TestCase):
    def test_expected_goals_calibration_groups_home_and_away_rates(self):
        rows = [forecast(1, "2026-01-01T10:00:00Z", "2026-01-01T08:00:00Z", [2, 1])]
        result = expected_goals_calibration(rows)
        self.assertEqual(result["home"][2]["matches"], 1)
        self.assertEqual(result["away"][1]["matches"], 1)
        self.assertEqual(result["home"][2]["mean_actual"], 2.0)

    def test_scoreline_baseline_compares_models_on_same_completed_sample(self):
        rows = [
            forecast(1, "2026-01-01T10:00:00Z", "2026-01-01T08:00:00Z", [1, 0]),
            forecast(2, "2026-01-02T10:00:00Z", "2026-01-01T08:00:00Z", [2, 2],
                     probabilities={"ph": 0.4, "pd": 0.3, "pa": 0.3,
                                    "lh": 1.6, "la": 1.1, "o25": 0.6, "bt": 0.5}),
        ]
        result = scoreline_baseline_comparison(rows)
        self.assertEqual(result["matches"], 2)
        self.assertEqual(result["excluded"], 0)
        self.assertIn(result["interpretation"], ("dixon_coles_better", "independent_poisson_better",
                                                   "no_clear_difference"))


if __name__ == "__main__":
    unittest.main()
