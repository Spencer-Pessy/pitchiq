import ast
import unittest
from pathlib import Path

from pitchiq_data import is_club_competition


class UpdateRequestPacingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("update.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_request_pacing_runs_before_every_network_attempt(self):
        get_node = next(
            node for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "get"
        )
        retry_loop = next(node for node in get_node.body if isinstance(node, ast.For))
        first = retry_loop.body[0]
        self.assertIsInstance(first, ast.Expr)
        self.assertIsInstance(first.value, ast.Call)
        self.assertEqual(getattr(first.value.func, "id", None), "_pace_api_request")
        self.assertIn("urlopen", ast.unparse(retry_loop))
        self.assertIn("REQUEST_INTERVAL_SECONDS = 7.0", self.source)

    def test_old_loop_specific_sleeps_are_removed(self):
        self.assertNotIn("time.sleep(7)", self.source)

    def test_pacer_uses_monotonic_clock(self):
        pacer = next(
            node for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_pace_api_request"
        )
        pacer_source = ast.unparse(pacer)
        self.assertIn("time.monotonic()", pacer_source)
        self.assertIn("time.sleep(remaining)", pacer_source)

    def test_pacer_waits_for_full_seven_second_interval(self):
        pacer = next(
            node for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_pace_api_request"
        )

        class FakeTime:
            now = 0.0
            sleeps = []

            @classmethod
            def monotonic(cls):
                return cls.now

            @classmethod
            def sleep(cls, seconds):
                cls.sleeps.append(seconds)
                cls.now += seconds

        namespace = {
            "time": FakeTime,
            "REQUEST_INTERVAL_SECONDS": 7.0,
            "_last_api_request_at": None,
        }
        module = ast.Module(body=[pacer], type_ignores=[])
        exec(compile(module, "<pacer-test>", "exec"), namespace)

        namespace["_pace_api_request"]()
        self.assertEqual(FakeTime.sleeps, [])
        FakeTime.now += 2.0
        namespace["_pace_api_request"]()
        self.assertEqual(FakeTime.sleeps, [5.0])
        FakeTime.now += 7.0
        namespace["_pace_api_request"]()
        self.assertEqual(FakeTime.sleeps, [5.0])

    def test_public_and_research_ledgers_are_normalized_before_processing(self):
        self.assertIn("clean_prediction_ledger(json.load(f))", self.source)
        self.assertIn('p.get("final") is None and p.get("id") in byid', self.source)

    def test_calibration_uses_validated_club_history_and_excludes_internationals(self):
        self.assertIn("goal_rate_calibration", self.source)
        self.assertIn('is_club_competition(p.get("code"))', self.source)
        self.assertIn('"valid results"', self.source)

    def test_international_competitions_stay_out_of_club_forecast_pipeline(self):
        self.assertFalse(is_club_competition("WC"))
        self.assertFalse(is_club_competition("EC"))
        self.assertTrue(is_club_competition("PL"))
        self.assertTrue(is_club_competition("CL"))
        self.assertIn('if not is_club_competition(m.get("_c")):', self.source)
        self.assertIn('is_club_competition(p.get("code"))', self.source)

    def test_scheduled_jobs_are_staggered_away_from_hour_boundaries(self):
        update_workflow = Path(".github/workflows/update.yml").read_text(encoding="utf-8")
        odds_workflow = Path(".github/workflows/odds.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "7,37 * * * *"', update_workflow)
        self.assertIn('cron: "23 7 * * *"', odds_workflow)
        self.assertNotIn("if: ${{ false }}", odds_workflow)
        self.assertIn("ODDS_API_KEY is not configured; no odds request was made.", odds_workflow)


if __name__ == "__main__":
    unittest.main()
