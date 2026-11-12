import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from pitchiq_news import (
    canonical_url, clean_summary, format_digest, parse_feed, select_new_stories,
)


NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


class PitchIQNewsValidationTests(unittest.TestCase):
    def test_only_https_bbc_football_article_links_are_accepted(self):
        self.assertEqual(
            canonical_url("https://www.bbc.co.uk/sport/football/articles/abc?at_medium=RSS#top"),
            "https://www.bbc.co.uk/sport/football/articles/abc",
        )
        self.assertEqual(canonical_url("http://www.bbc.co.uk/sport/football/articles/abc"), "")
        self.assertEqual(canonical_url("https://example.com/sport/football/articles/abc"), "")
        self.assertEqual(canonical_url("https://www.bbc.co.uk/sport/tennis/articles/abc"), "")
        self.assertEqual(canonical_url("javascript:alert(1)"), "")

    def test_summary_markup_is_removed_and_text_is_bounded(self):
        self.assertEqual(clean_summary("<p>Arsenal &amp; City</p>"), "Arsenal & City")
        self.assertEqual(len(clean_summary("x" * 400)), 260)

    def test_feed_parser_filters_old_future_and_non_bbc_items(self):
        xml = b"""<?xml version="1.0"?><rss><channel>
          <item><title>Recent match report</title><link>https://www.bbc.co.uk/sport/football/articles/one?x=1</link><description><![CDATA[<p>Latest <b>report</b>.</p>]]></description><pubDate>Thu, 12 Nov 2026 11:00:00 GMT</pubDate></item>
          <item><title>Old report</title><link>https://www.bbc.co.uk/sport/football/articles/old</link><pubDate>Mon, 09 Nov 2026 00:00:00 GMT</pubDate></item>
          <item><title>Future report</title><link>https://www.bbc.co.uk/sport/football/articles/future</link><pubDate>Fri, 13 Nov 2026 00:00:00 GMT</pubDate></item>
          <item><title>Wrong site</title><link>https://example.com/sport/football/articles/no</link><pubDate>Thu, 12 Nov 2026 11:00:00 GMT</pubDate></item>
        </channel></rss>"""
        stories = parse_feed(xml, now=NOW)
        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0]["title"], "Recent match report")
        self.assertEqual(stories[0]["summary"], "Latest report.")
        self.assertEqual(stories[0]["url"], "https://www.bbc.co.uk/sport/football/articles/one")

    def test_feed_parser_requires_timezone_aware_now(self):
        with self.assertRaises(ValueError):
            parse_feed(b"<rss><channel/></rss>", now=datetime(2026, 11, 12))

    def test_selection_deduplicates_tracking_urls_and_existing_seen_urls(self):
        stories = [
            {"url": "https://www.bbc.co.uk/sport/football/articles/a?ref=rss", "title": "A"},
            {"url": "https://www.bbc.co.uk/sport/football/articles/a", "title": "A duplicate"},
            {"url": "https://www.bbc.co.uk/sport/football/articles/b", "title": "B"},
        ]
        selected = select_new_stories(stories, ["https://www.bbc.co.uk/sport/football/articles/b"])
        self.assertEqual([item["url"] for item in selected],
                         ["https://www.bbc.co.uk/sport/football/articles/a"])

    def test_digest_credits_source_and_keeps_direct_article_links(self):
        message = format_digest([{
            "title": "A headline", "summary": "A short summary",
            "url": "https://www.bbc.co.uk/sport/football/articles/a",
        }])
        self.assertIn("PITCHIQ FOOTBALL NEWS", message)
        self.assertIn("BBC Sport", message)
        self.assertIn("A short summary", message)
        self.assertIn("https://www.bbc.co.uk/sport/football/articles/a", message)

    def test_disabled_publisher_exits_before_network_or_telegram(self):
        from pitchiq_news import main
        with patch.dict(os.environ, {"PITCHIQ_NEWS_ENABLED": "false"}, clear=True), \
             patch("pitchiq_news.fetch_feed", side_effect=AssertionError("network must not run")), \
             patch("pitchiq_news.send_digest", side_effect=AssertionError("Telegram must not run")):
            main()


class PitchIQNewsWorkflowTests(unittest.TestCase):
    def test_news_workflow_is_enabled_for_the_news_channel_and_keeps_a_separate_target(self):
        from pathlib import Path
        workflow = Path(".github/workflows/telegram-news.yml").read_text(encoding="utf-8")
        self.assertIn("cron: '43 */4 * * *'", workflow)
        self.assertIn('PITCHIQ_NEWS_ENABLED: "true"', workflow)
        self.assertIn('TELEGRAM_NEWS_CHAT_ID: "@pitchiq_picks"', workflow)
        self.assertIn("group: pitchiq-telegram-news", workflow)
        self.assertNotIn("TELEGRAM_CHAT_ID:", workflow)
        self.assertIn("never rerun the Telegram send step", workflow)
        self.assertIn("cp daily/news_seen.json /tmp/pitchiq-news-seen.json", workflow)
        self.assertIn("cp /tmp/pitchiq-news-seen.json daily/news_seen.json", workflow)
        self.assertNotIn("cp -a daily/. /tmp/pitchiq-news/", workflow)
        self.assertNotIn("cp -a /tmp/pitchiq-news/. daily/", workflow)

    def test_existing_news_history_is_preserved_as_a_list(self):
        import json
        from pathlib import Path
        history = json.loads(Path("daily/news_seen.json").read_text(encoding="utf-8"))
        self.assertIsInstance(history, list)
        self.assertTrue(all(isinstance(url, str) for url in history))


if __name__ == "__main__":
    unittest.main()
