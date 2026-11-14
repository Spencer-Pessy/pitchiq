import unittest
from datetime import datetime, timezone, timedelta

from pitchiq_h2h import (
    cached_h2h_matches, normalize_h2h_cache, refresh_h2h_cache,
)


class H2HCacheTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)

    def fixture(self, fixture_id, kickoff, home=5, away=1):
        return {
            "id": fixture_id, "status": "TIMED", "utcDate": kickoff,
            "homeTeam": {"id": home}, "awayTeam": {"id": away},
        }

    def test_refreshes_nearest_five_upcoming_fixtures_only(self):
        fixtures = [
            self.fixture(4, "2026-11-18T18:00:00Z"),
            self.fixture(3, "2026-11-15T18:00:00Z"),
            self.fixture(2, "2026-11-14T18:00:00Z"),
            self.fixture(1, "2026-11-16T18:00:00Z"),
            self.fixture(5, "2026-11-12T18:00:00Z"),
            self.fixture(6, "2026-11-17T18:00:00Z"),
            self.fixture(7, "2026-11-19T18:00:00Z"),
        ]
        called = []
        def fetch(fixture_id):
            called.append(fixture_id)
            return {"matches": [{"id": fixture_id}]}
        cache, count = refresh_h2h_cache(fixtures, {}, fetch, self.now)
        self.assertEqual(count, 5)
        self.assertEqual(called, [2, 3, 1, 6, 4])
        self.assertEqual(cached_h2h_matches(cache, 2), [{"id": 2}])
        self.assertNotIn("7", cache["entries"])

    def test_successful_cache_is_not_refetched_within_24_hours(self):
        fixtures = [self.fixture(10, "2026-11-14T18:00:00Z")]
        cache, _ = refresh_h2h_cache(fixtures, {}, lambda _id: {"matches": [{"id": 7}]}, self.now)
        called = []
        cache, count = refresh_h2h_cache(
            fixtures, cache, lambda fixture_id: called.append(fixture_id), self.now + timedelta(hours=23)
        )
        self.assertEqual(count, 0)
        self.assertEqual(called, [])

    def test_failed_request_keeps_previous_data_and_uses_retry_cooldown(self):
        fixtures = [self.fixture(10, "2026-11-14T18:00:00Z")]
        original = {"schema": 1, "entries": {"10": {
            "home_team_id": 5, "away_team_id": 1,
            "attempted_at": None, "fetched_at": "2026-11-01T00:00:00+00:00",
            "matches": [{"id": 99}],
        }}}
        cache, count = refresh_h2h_cache(fixtures, original, lambda _id: None, self.now)
        self.assertEqual(count, 1)
        self.assertEqual(cached_h2h_matches(cache, 10), [{"id": 99}])
        calls = []
        _, count = refresh_h2h_cache(
            fixtures, cache, lambda fixture_id: calls.append(fixture_id), self.now + timedelta(hours=1)
        )
        self.assertEqual(count, 0)
        self.assertEqual(calls, [])

    def test_cache_is_not_reused_for_a_different_team_pair(self):
        fixtures = [self.fixture(10, "2026-11-14T18:00:00Z", home=8, away=9)]
        original = {"entries": {"10": {
            "home_team_id": 5, "away_team_id": 1,
            "matches": [{"id": 99}], "fetched_at": None, "attempted_at": None,
        }}}
        cache, _ = refresh_h2h_cache(fixtures, original, lambda _id: None, self.now)
        self.assertEqual(cached_h2h_matches(cache, 10, 8, 9), [])
        self.assertEqual(cache["entries"]["10"]["matches"], [])

    def test_malformed_cache_is_safely_normalized(self):
        self.assertEqual(normalize_h2h_cache(None), {"schema": 1, "entries": {}})
        self.assertEqual(cached_h2h_matches({"entries": {"1": "bad"}}, 1), [])


if __name__ == "__main__":
    unittest.main()
