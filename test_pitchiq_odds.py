import unittest

from pitchiq_odds import active_sport_keys, market_events


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
