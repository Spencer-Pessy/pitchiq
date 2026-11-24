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
        self.assertIn("require_prediction_ledger(_prediction_data)", self.source)
        self.assertIn("cannot read existing predictions.json", self.source)
        self.assertIn("invalid existing predictions.json", self.source)
        self.assertIn("require_prediction_ledger(_evaluation_data)", self.source)
        self.assertIn("cannot read existing model_evaluation.json", self.source)
        self.assertIn("invalid existing model_evaluation.json", self.source)
        self.assertNotIn("except Exception:\n    evaluation = {}", self.source)
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


    def test_live_scores_refresh_is_recovered_by_explicit_watchdog_dispatch(self):
        live_workflow = Path(".github/workflows/live-scores.yml").read_text(encoding="utf-8")
        update_workflow = Path(".github/workflows/update.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "*/10 * * * *"', live_workflow)
        self.assertIn("actions: write", update_workflow)
        self.assertIn("gh workflow run pipeline-watchdog.yml --ref main", update_workflow)
        self.assertIn("gh workflow run pipeline-watchdog.yml --ref main", live_workflow)
        self.assertNotIn("workflow_run:", live_workflow)

    def test_results_publisher_is_dispatched_only_after_successful_data_publication(self):
        update_workflow = Path(".github/workflows/update.yml").read_text(encoding="utf-8")
        results_workflow = Path(".github/workflows/telegram-results.yml").read_text(encoding="utf-8")
        marker = "Trigger published-pick results after successful data publication"
        self.assertIn(marker, update_workflow)
        dispatch = update_workflow[update_workflow.index(marker):]
        self.assertIn("if: success()", dispatch[:400])
        self.assertIn("gh workflow run telegram-results.yml --ref main", dispatch)
        self.assertIn("workflow_dispatch:", results_workflow)
        self.assertIn("cron: '17 * * * *'", results_workflow)
        self.assertNotIn("workflow_run:", results_workflow)


    def test_telegram_picks_schedule_matches_approved_daily_blueprint(self):
        workflow = Path(".github/workflows/telegram.yml").read_text(encoding="utf-8")
        blueprint = Path("docs/MASTER_BLUEPRINT.md").read_text(encoding="utf-8")
        self.assertIn("cron: '0 8 * * *'", workflow)
        self.assertIn("Telegram picks: daily at 08:00 UTC", blueprint)

    def test_model_and_evaluation_changes_trigger_data_refresh(self):
        workflow = Path(".github/workflows/update.yml").read_text(encoding="utf-8")
        for path in ("pitchiq_model.py", "model_metrics.py"):
            self.assertIn(f"      - {path}", workflow)


    def test_configured_competitions_match_all_12_free_tier_codes(self):
        assignment = next(
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "COMPS"
                    for target in node.targets)
        )
        self.assertEqual(
            set(ast.literal_eval(assignment.value)),
            {"PL", "PD", "SA", "BL1", "FL1", "CL", "WC", "EC",
             "ELC", "DED", "PPL", "BSA"},
        )


if __name__ == "__main__":
    unittest.main()
