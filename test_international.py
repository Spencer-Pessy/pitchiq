import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from international import (
    deduplicate, fetch_espn_fixtures, normalize_espn_event, normalize_matches, parse_kickoff, ESPN_LEAGUES,
    merge_failed_league_fixtures,
    summarize_espn_coverage,
)


class InternationalFeedTests(unittest.TestCase):
    def test_concacaf_nations_league_uses_valid_espn_slug(self):
        self.assertIn(("concacaf.nations.league", "CONCACAF Nations League"), ESPN_LEAGUES)

    def test_supported_senior_womens_national_team_competitions_are_listed(self):
        expected = {
            ("fifa.wwc", "FIFA Women's World Cup"),
            ("fifa.wworldq.uefa", "FIFA Women's World Cup Qualifying - UEFA"),
            ("uefa.w.nations", "UEFA Women's Nations League"),
            ("uefa.weuro", "UEFA Women's European Championship"),
            ("fifa.shebelieves", "SheBelieves Cup"),
            ("concacaf.w.gold", "CONCACAF W Gold Cup"),
            ("conmebol.america.femenina", "Copa America Femenina"),
        }
        self.assertTrue(expected.issubset(set(ESPN_LEAGUES)))

    def test_timezone_is_converted_to_utc(self):
        self.assertEqual(parse_kickoff("2026-06-11", "13:00 UTC-6"), "2026-06-11T19:00:00+00:00")
        self.assertEqual(parse_kickoff("2026-06-11", "20:00 UTC+3"), "2026-06-11T17:00:00+00:00")

    def test_invalid_calendar_dates_and_out_of_range_utc_offsets_are_rejected(self):
        self.assertIsNone(parse_kickoff("2026-02-30", "13:00 UTC"))
        self.assertIsNone(parse_kickoff("not-a-date", "13:00 UTC"))
        self.assertIsNone(parse_kickoff("2026-06-11", "13:00 UTC+14:30"))
        self.assertIsNone(parse_kickoff("2026-06-11", "13:00 UTC-15"))

    def test_invalid_or_missing_kickoff_is_rejected(self):
        self.assertIsNone(parse_kickoff("2026-06-11", "TBD"))
        self.assertIsNone(parse_kickoff("2026-06-11", "25:70 UTC+2"))

    def test_normalizes_national_world_cup_fixtures(self):
        payload = {
            "name": "World Cup 2026",
            "matches": [
                {"date": "2026-06-11", "time": "13:00 UTC-6",
                 "team1": "Mexico", "team2": "South Africa",
                 "score": {"ft": [2, 0]}, "ground": "Mexico City"},
                {"date": "2026-06-12", "time": "15:00 UTC-4",
                 "team1": "Canada", "team2": "Qatar", "score": {}},
                {"date": "2026-06-13", "time": "TBD",
                 "team1": "Missing Time", "team2": "Fixture"},
            ],
        }
        rows = normalize_matches(payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "FT")
        self.assertEqual(rows[0]["score"], [2, 0])
        self.assertEqual(rows[0]["utc"], "2026-06-11T19:00:00+00:00")
        self.assertEqual(rows[1]["status"], "NS")
        self.assertIsNone(rows[1]["score"])
        self.assertEqual(rows[0]["source"], "OpenFootball worldcup.json (CC0)")

    def test_normalizes_espn_upcoming_event(self):
        event = {
            "id": "12345",
            "date": "2026-11-14T16:00:00Z",
            "status": {"type": {"state": "pre", "name": "STATUS_SCHEDULED"}},
            "competitions": [{
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": "Japan"}, "score": ""},
                    {"homeAway": "away", "team": {"displayName": "Brazil"}, "score": ""},
                ],
                "venue": {"fullName": "National Stadium"},
            }],
            "leagues": [{"name": "International Friendly"}],
        }
        row = normalize_espn_event(event, "fifa.friendly", "International Friendlies")
        self.assertEqual(row["id"], "espn-fifa.friendly-12345")
        self.assertEqual(row["h"], "Japan")
        self.assertEqual(row["a"], "Brazil")
        self.assertEqual(row["status"], "NS")
        self.assertIsNone(row["score"])
        self.assertEqual(row["utc"], "2026-11-14T16:00:00+00:00")
        self.assertEqual(row["source"], "ESPN public scoreboard (unofficial)")

    def test_openfootball_rejects_invalid_full_time_score_values(self):
        payload = {
            "name": "World Cup 2026",
            "matches": [
                {"date": "2026-06-11", "time": "13:00 UTC-6",
                 "team1": "A", "team2": "B", "score": {"ft": [-1, 2]}},
                {"date": "2026-06-12", "time": "13:00 UTC-6",
                 "team1": "C", "team2": "D", "score": {"ft": [True, 1]}},
                {"date": "2026-06-13", "time": "13:00 UTC-6",
                 "team1": "E", "team2": "F", "score": {"ft": ["2", 1]}},
            ],
        }
        rows = normalize_matches(payload)
        self.assertEqual([row["status"] for row in rows], ["NS", "NS", "NS"])
        self.assertTrue(all(row["score"] is None for row in rows))

    def test_espn_rejects_negative_scores(self):
        event = {
            "id": "negative-score",
            "date": "2026-11-14T16:00:00Z",
            "status": {"type": {"state": "post", "name": "STATUS_FINAL", "description": "Final"}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"name": "Japan"}, "score": "-1"},
                {"homeAway": "away", "team": {"name": "Brazil"}, "score": "1"},
            ]}],
        }
        row = normalize_espn_event(event, "fifa.friendly", "International Friendlies")
        self.assertEqual(row["status"], "FT")
        self.assertIsNone(row["score"])

    def test_normalizes_espn_final_score_and_status(self):
        event = {
            "id": "987",
            "date": "2026-11-14T16:00:00Z",
            "status": {"type": {"state": "post", "name": "STATUS_FINAL", "description": "Final"}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"name": "Japan"}, "score": "2"},
                {"homeAway": "away", "team": {"name": "Brazil"}, "score": "1"},
            ]}],
        }
        row = normalize_espn_event(event, "fifa.friendly", "International Friendlies")
        self.assertEqual(row["status"], "FT")
        self.assertEqual(row["score"], [2, 1])

    def test_live_periods_are_not_mislabeled(self):
        base = {
            "id": "live-1",
            "date": "2026-11-14T16:00:00Z",
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"name": "Kenya"}, "score": "0"},
                {"homeAway": "away", "team": {"name": "Uganda"}, "score": "0"},
            ]}],
        }
        first_half = dict(base, status={"type": {"state": "in", "period": 1, "name": "STATUS_FIRST_HALF"}})
        half_time = dict(base, status={"type": {"state": "in", "name": "STATUS_HALFTIME"}})
        second_half = dict(base, status={"type": {"state": "in", "period": 2, "name": "STATUS_SECOND_HALF"}})
        self.assertEqual(normalize_espn_event(first_half, "fifa.friendly", "Friendlies")["status"], "1H")
        self.assertEqual(normalize_espn_event(half_time, "fifa.friendly", "Friendlies")["status"], "HT")
        self.assertEqual(normalize_espn_event(second_half, "fifa.friendly", "Friendlies")["status"], "2H")

    def test_postponed_match_is_not_marked_final(self):
        event = {
            "id": "postponed-1",
            "date": "2026-11-14T16:00:00Z",
            "status": {"type": {"state": "pre", "name": "STATUS_POSTPONED", "description": "Postponed"}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"name": "Kenya"}},
                {"homeAway": "away", "team": {"name": "Uganda"}},
            ]}],
        }
        row = normalize_espn_event(event, "fifa.friendly", "Friendlies")
        self.assertEqual(row["status"], "PST")
        self.assertIsNone(row["score"])

    def test_cancelled_post_event_with_numeric_scores_has_no_result(self):
        event = {
            "id": "cancelled-post-1",
            "date": "2026-11-14T16:00:00Z",
            "status": {"type": {
                "state": "post", "name": "STATUS_CANCELED",
                "description": "Canceled",
            }},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"name": "Kenya"}, "score": "2"},
                {"homeAway": "away", "team": {"name": "Uganda"}, "score": "1"},
            ]}],
        }
        row = normalize_espn_event(event, "fifa.friendly", "Friendlies")
        self.assertEqual(row["status"], "CANC")
        self.assertIsNone(row["score"])

    def test_rejects_malformed_espn_event(self):
        self.assertIsNone(normalize_espn_event({}, "fifa.friendly", "Friendlies"))
        self.assertIsNone(normalize_espn_event({
            "id": "1", "date": "2026-11-14T16:00:00Z",
            "competitions": [{"competitors": []}],
        }, "fifa.friendly", "Friendlies"))

    def test_deduplicates_identical_fixture_rows(self):
        row = {"utc": "2026-11-14T16:00:00+00:00", "h": "Japan", "a": "Brazil", "id": "a"}
        duplicate = dict(row, id="b")
        self.assertEqual([x["id"] for x in deduplicate([row, duplicate])], ["a"])

    def test_request_pacing_applies_to_non_200_responses(self):
        class UnavailableResponse:
            status = 503
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        calls = []
        def unavailable_opener(request, timeout):
            calls.append(request.full_url)
            return UnavailableResponse()

        with patch("international.time.sleep") as sleep:
            fixtures, successful = fetch_espn_fixtures(
                now=datetime(2026, 11, 12, tzinfo=timezone.utc),
                opener=unavailable_opener,
            )
        self.assertEqual(fixtures, [])
        self.assertEqual(successful, [])
        self.assertEqual(len(calls), 7 * len(ESPN_LEAGUES))
        self.assertEqual(sleep.call_count, len(calls) - 1)

    def test_world_cup_archive_is_explicitly_mens(self):
        payload = {
            "name": "World Cup 2026",
            "matches": [{
                "date": "2026-06-11", "time": "13:00 UTC-6",
                "team1": "Mexico", "team2": "South Africa", "score": {},
            }],
        }
        row = normalize_matches(payload)[0]
        self.assertEqual(row["gender"], "men")

    def test_all_configured_womens_espn_competitions_are_labeled_women(self):
        event = {
            "id": "women-1",
            "date": "2026-11-14T16:00:00Z",
            "status": {"type": {"state": "pre", "name": "STATUS_SCHEDULED"}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"name": "Kenya"}},
                {"homeAway": "away", "team": {"name": "Uganda"}},
            ]}],
        }
        womens_slugs = {
            "fifa.friendly.w", "fifa.wwc", "fifa.wworldq.uefa",
            "uefa.w.nations", "uefa.weuro", "fifa.shebelieves",
            "concacaf.w.gold", "conmebol.america.femenina",
        }
        for slug, label in ESPN_LEAGUES:
            with self.subTest(slug=slug):
                row = normalize_espn_event(event, slug, label)
                expected = "women" if slug in womens_slugs else "men"
                self.assertEqual(row["gender"], expected)

    def test_deduplication_keeps_distinct_mens_and_womens_fixture_streams(self):
        base = {"utc": "2026-11-14T16:00:00+00:00", "h": "Kenya", "a": "Uganda"}
        rows = deduplicate([
            dict(base, id="men", gender="men"),
            dict(base, id="women", gender="women"),
        ])
        self.assertEqual({row["gender"] for row in rows}, {"men", "women"})

    def test_rejects_malformed_or_empty_openfootball_source(self):
        with self.assertRaises(ValueError):
            normalize_matches({"matches": []})
        with self.assertRaises(ValueError):
            normalize_matches({"response": []})


class ESPNRequestCoverageTests(unittest.TestCase):
    def test_reports_daily_request_success_separately_from_league_coverage(self):
        successful = [
            ("fifa.friendly", "20261112"),
            ("fifa.friendly", "20261113"),
            ("uefa.nations", "20261112"),
        ]
        result = summarize_espn_coverage(successful, 98)
        self.assertEqual(result["requests_checked"], 98)
        self.assertEqual(result["requests_successful"], 3)
        self.assertEqual(result["leagues_checked"], len(ESPN_LEAGUES))
        self.assertEqual(result["leagues_successful"], ["fifa.friendly", "uefa.nations"])

    def test_empty_successful_request_set_reports_zero_not_false_success(self):
        result = summarize_espn_coverage([], 98)
        self.assertEqual(result["requests_successful"], 0)
        self.assertEqual(result["leagues_successful"], [])


class FailedLeagueRetentionTests(unittest.TestCase):
    def test_partial_feed_failure_preserves_recent_fixtures_only_for_failed_leagues(self):
        now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
        previous = [
            {"id": "espn-uefa.nations-old", "utc": "2026-11-13T18:00:00+00:00",
             "h": "A", "a": "B", "gender": "men"},
            {"id": "espn-fifa.friendly-old", "utc": "2026-11-13T19:00:00+00:00",
             "h": "C", "a": "D", "gender": "men"},
            {"id": "espn-uefa.nations-expired", "utc": "2026-11-01T18:00:00+00:00",
             "h": "E", "a": "F", "gender": "men"},
        ]
        fetched = [
            {"id": "espn-fifa.friendly-new", "utc": "2026-11-14T18:00:00+00:00",
             "h": "G", "a": "H", "gender": "men"},
        ]
        result = merge_failed_league_fixtures(
            fetched, ["fifa.friendly"], previous, now=now
        )
        ids = {item["id"] for item in result}
        self.assertIn("espn-uefa.nations-old", ids)
        self.assertIn("espn-fifa.friendly-new", ids)
        self.assertNotIn("espn-fifa.friendly-old", ids)
        self.assertNotIn("espn-uefa.nations-expired", ids)

    def test_partial_daily_failure_preserves_only_the_failed_date(self):
        now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
        previous = [
            {"id": "espn-fifa.friendly-old-13", "utc": "2026-11-13T18:00:00+00:00",
             "h": "Kenya", "a": "Uganda", "gender": "men"},
            {"id": "espn-fifa.friendly-old-12", "utc": "2026-11-12T18:00:00+00:00",
             "h": "Ghana", "a": "Nigeria", "gender": "men"},
        ]
        result = merge_failed_league_fixtures(
            [], [("fifa.friendly", "20261112")], previous, now=now
        )
        ids = {item["id"] for item in result}
        self.assertIn("espn-fifa.friendly-old-13", ids)
        self.assertNotIn("espn-fifa.friendly-old-12", ids)

    def test_successful_empty_date_is_not_resurrected_from_old_snapshot(self):
        now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
        previous = [{
            "id": "espn-fifa.friendly-old-12", "utc": "2026-11-12T18:00:00+00:00",
            "h": "A", "a": "B", "gender": "men",
        }]
        result = merge_failed_league_fixtures(
            [], [("fifa.friendly", "20261112")], previous, now=now
        )
        self.assertEqual(result, [])

    def test_successful_empty_league_is_not_resurrected_from_old_snapshot(self):
        now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
        previous = [{
            "id": "espn-fifa.friendly-old", "utc": "2026-11-13T18:00:00+00:00",
            "h": "A", "a": "B", "gender": "men",
        }]
        result = merge_failed_league_fixtures([], ["fifa.friendly"], previous, now=now)
        self.assertEqual(result, [])

    def test_failed_league_fixtures_are_deduplicated_with_fetched_rows(self):
        now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
        previous = [{
            "id": "espn-uefa.nations-old", "utc": "2026-11-13T18:00:00+00:00",
            "h": "A", "a": "B", "gender": "men",
        }]
        fetched = [{
            "id": "espn-uefa.nations-new", "utc": "2026-11-13T18:00:00+00:00",
            "h": "A", "a": "B", "gender": "men",
        }]
        result = merge_failed_league_fixtures(fetched, [], previous, now=now)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "espn-uefa.nations-new")


if __name__ == "__main__":
    unittest.main()
