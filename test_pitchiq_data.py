import unittest

from pitchiq_data import (
    INTERNATIONAL_COMPETITIONS,
    average_bucket,
    goal_average_keys,
    build_feed_health,
)


class CompetitionDataTests(unittest.TestCase):
    def test_world_cup_and_euro_are_international(self):
        self.assertEqual(INTERNATIONAL_COMPETITIONS, frozenset({"WC", "EC"}))

    def test_international_results_get_separate_and_shared_buckets(self):
        self.assertEqual(goal_average_keys("WC"), ("WC", "INTL", "ALL"))
        self.assertEqual(goal_average_keys("EC"), ("EC", "INTL", "ALL"))

    def test_club_results_never_enter_international_bucket(self):
        self.assertEqual(goal_average_keys("PL"), ("PL", "ALL"))

    def test_small_international_sample_uses_international_prior(self):
        counts = {"WC": 8, "EC": 6, "INTL": 14, "ALL": 120}
        self.assertEqual(average_bucket("WC", counts), "INTL")
        self.assertEqual(average_bucket("EC", counts), "INTL")

    def test_large_international_sample_uses_own_competition(self):
        self.assertEqual(average_bucket("WC", {"WC": 24, "INTL": 40}), "WC")

    def test_champions_league_keeps_existing_combined_prior_rule(self):
        self.assertEqual(average_bucket("CL", {"CL": 40, "ALL": 200}), "ALL")

    def test_small_club_competition_keeps_existing_fallback(self):
        self.assertEqual(average_bucket("PL", {"PL": 12, "ALL": 100}), "ALL")

    def test_feed_health_reports_competition_coverage(self):
        health = build_feed_health(
            {"PL": 30, "WC": 4, "EC": 2},
            {"PL", "WC"},
            18,
        )
        self.assertEqual(health["fixture_competitions"], 3)
        self.assertEqual(health["fixture_total"], 36)
        self.assertEqual(health["international_fixture_total"], 6)
        self.assertEqual(health["standings_competitions"], 2)
        self.assertEqual(health["published_match_count"], 18)
        self.assertEqual(health["fixture_counts"], {"EC": 2, "PL": 30, "WC": 4})

    def test_feed_health_handles_no_standings_or_fixtures(self):
        health = build_feed_health({}, set(), 0)
        self.assertEqual(health["fixture_total"], 0)
        self.assertEqual(health["international_fixture_total"], 0)
        self.assertEqual(health["standings_available"], [])


if __name__ == "__main__":
    unittest.main()
