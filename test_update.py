import ast
import unittest
from pathlib import Path


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

    def test_scheduled_jobs_are_staggered_away_from_hour_boundaries(self):
        update_workflow = Path(".github/workflows/update.yml").read_text(encoding="utf-8")
        odds_workflow = Path(".github/workflows/odds.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "7,37 * * * *"', update_workflow)
        self.assertIn('cron: "23 7 * * *"', odds_workflow)


if __name__ == "__main__":
    unittest.main()
