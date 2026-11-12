import unittest

from pitchiq_odds import active_sport_keys, market_events, require_nonempty_snapshot


class ActiveSportValidationTests(unittest.TestCase):
    def test_returns_only_active_sport_keys(self):
        self.assertEqual(
            active_sport_keys([
                {"key": "soccer_epl", "active": True},
                {"key": "soccer_old", "active": False},
            ]),
            {"soccer_epl"},
        )

    def test_rejects_malformed_discovery_payloads(self):
        for payload in (None, {}, ["bad"], [{"key": "soccer_epl"}],
                        [{"key": "", "active": True}], [{"key": "x", "active": 1}]):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                active_sport_keys(payload)


class SnapshotPublicationGuardTests(unittest.TestCase):
    def test_accepts_nonempty_snapshot_for_active_requested_competition(self):
        events = [{"home": "Arsenal", "away": "Chelsea", "odds": [2.0, 3.5, 4.0]}]
        self.assertEqual(
            require_nonempty_snapshot({"soccer_epl"}, {"soccer_epl", "soccer_uefa_champs_league"}, events),
            events,
        )

    def test_rejects_when_no_requested_competition_is_active(self):
        with self.assertRaises(ValueError):
            require_nonempty_snapshot({"soccer_nba"}, {"soccer_epl"}, [])

    def test_rejects_empty_or_invalid_event_collection(self):
        for events in ([], None, {}):
            with self.subTest(events=events), self.assertRaises(ValueError):
                require_nonempty_snapshot({"soccer_epl"}, {"soccer_epl"}, events)


class OddsPublisherIntegrationGuardTests(unittest.TestCase):
    def test_publisher_invokes_nonempty_guard_before_overwriting_snapshot(self):
        from pathlib import Path
        source = Path("odds.py").read_text(encoding="utf-8")
        guard = "events = require_nonempty_snapshot(active, WANT, events)"
        write = 'with open("odds.json", "w", encoding="utf-8") as f:'
        self.assertIn(guard, source)
        self.assertLess(source.index(guard), source.index(write))


class OddsMarketValidationTests(unittest.TestCase):
    def test_averages_three_way_prices_in_home_draw_away_order(self):
        events = market_events([{
            "home_team": "Arsenal", "away_team": "Chelsea",
            "commence_time": "2026-11-22T15:00:00Z",
            "bookmakers": [
                {"markets": [{"key": "h2h", "outcomes": [
                    {"name": "Arsenal", "price": 1.8},
                    {"name": "Draw", "price": 3.7},
                    {"name": "Chelsea", "price": 4.5},
                ]}]},
                {"markets": [{"key": "h2h", "outcomes": [
                    {"name": "Arsenal", "price": 2.0},
                    {"name": "Draw", "price": 3.9},
                    {"name": "Chelsea", "price": 4.3},
                ]}]},
            ],
        }])
        self.assertEqual(events[0]["odds"], [1.9, 3.8, 4.4])

    def test_valid_empty_response_is_allowed(self):
        self.assertEqual(market_events([]), [])

    def test_skips_events_without_complete_three_way_market(self):
        self.assertEqual(market_events([{
            "home_team": "Arsenal", "away_team": "Chelsea",
            "commence_time": "2026-11-22T15:00:00Z", "bookmakers": [],
        }]), [])

    def test_rejects_malformed_event_and_nested_shapes(self):
        cases = [
            [None],
            [{"home_team": "Arsenal", "away_team": "Chelsea",
              "commence_time": "not-a-date", "bookmakers": []}],
            [{"home_team": "Arsenal", "away_team": "Chelsea",
              "commence_time": "2026-11-22T15:00:00", "bookmakers": []}],
            [{"home_team": "Arsenal", "away_team": "Chelsea",
              "commence_time": "2026-11-22T15:00:00Z", "bookmakers": {}}],
            [{"home_team": "Arsenal", "away_team": "Chelsea",
              "commence_time": "2026-11-22T15:00:00Z",
              "bookmakers": [{"markets": "bad"}]}],
            [{"home_team": "Arsenal", "away_team": "Chelsea",
              "commence_time": "2026-11-22T15:00:00Z",
              "bookmakers": [{"markets": [{"key": "h2h", "outcomes": "bad"}]}]}],
        ]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                market_events(payload)

    def test_rejects_duplicate_outcomes_within_one_bookmaker_market(self):
        payload = [{
            "home_team": "Arsenal", "away_team": "Chelsea",
            "commence_time": "2026-11-22T15:00:00Z",
            "bookmakers": [{"markets": [{"key": "h2h", "outcomes": [
                {"name": "Arsenal", "price": 1.8},
                {"name": "Arsenal", "price": 1.9},
                {"name": "Draw", "price": 3.7},
                {"name": "Chelsea", "price": 4.5},
            ]}]}],
        }]
        with self.assertRaisesRegex(ValueError, "duplicate outcome"):
            market_events(payload)

    def test_rejects_invalid_prices_instead_of_publishing_partial_data(self):
        for price in (True, 1, 1000, float("nan"), float("inf"), "2.0", None):
            payload = [{
                "home_team": "Arsenal", "away_team": "Chelsea",
                "commence_time": "2026-11-22T15:00:00Z",
                "bookmakers": [{"markets": [{"key": "h2h", "outcomes": [
                    {"name": "Arsenal", "price": price},
                    {"name": "Draw", "price": 3.7},
                    {"name": "Chelsea", "price": 4.5},
                ]}]}],
            }]
            with self.subTest(price=price), self.assertRaises(ValueError):
                market_events(payload)


if __name__ == "__main__":
    unittest.main()

class OddsWorkflowActivationTests(unittest.TestCase):
    def test_odds_workflow_is_enabled_and_skips_safely_without_api_key(self):
        from pathlib import Path
        workflow = Path(".github/workflows/odds.yml").read_text(encoding="utf-8")
        self.assertNotIn("if: ${{ false }}", workflow)
        self.assertIn('cron: "23 7 * * *"', workflow)
        self.assertIn("ODDS_API_KEY is not configured; no odds request was made.", workflow)
        self.assertIn("ODDS_FREE_TIER_CONFIRMED", workflow)
        self.assertIn("Free-tier use has not been confirmed in repository Variables or Secrets; no odds request was made.", workflow)
        self.assertIn('vars.ODDS_FREE_TIER_CONFIRMED || secrets.ODDS_FREE_TIER_CONFIRMED', workflow)
        self.assertIn("steps.credentials.outputs.available == 'true'", workflow)
        self.assertIn("group: pitchiq-odds", workflow)

