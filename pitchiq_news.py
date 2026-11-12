"""Opt-in, source-linked BBC football news digest for the PitchIQ news channel.

No paid API is used. This module is inert unless PITCHIQ_NEWS_ENABLED=true.
It never generates or rewrites reporting; it republishes short feed summaries
with direct BBC Sport links.
"""
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pitchiq_telegram import clean_seen_urls

FEED_URL = "https://feeds.bbci.co.uk/sport/football/rss.xml"
SEEN_PATH = Path("daily/news_seen.json")
MAX_AGE = timedelta(hours=36)
MAX_FUTURE = timedelta(hours=6)
MAX_STORIES = 3
MAX_MESSAGE_LENGTH = 3500
BBC_HOSTS = {"www.bbc.co.uk", "www.bbc.com"}


def canonical_url(value):
    """Remove tracking query/fragment while preserving a BBC article URL."""
    if not isinstance(value, str):
        return ""
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return ""
    if (parts.scheme != "https" or parts.hostname not in BBC_HOSTS
            or not parts.path.startswith("/sport/football/")):
        return ""
    return urlunsplit(("https", parts.netloc.lower(), parts.path, "", ""))


def clean_summary(value, limit=260):
    """Convert feed markup to a short plain-text excerpt."""
    if not isinstance(value, str):
        return ""
    value = re.sub(r"<[^>]*>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit].rstrip()


def parse_feed(xml_bytes, now=None):
    """Parse recent, valid BBC football RSS items; reject unrelated links."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    root = ET.fromstring(xml_bytes)
    stories = []
    for item in root.findall(".//item"):
        title = clean_summary(item.findtext("title"), 180)
        link = canonical_url(item.findtext("link"))
        published_text = item.findtext("pubDate")
        if not title or not link or not published_text:
            continue
        try:
            published = parsedate_to_datetime(published_text)
            if published.tzinfo is None or published.utcoffset() is None:
                continue
            published = published.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
        if published < now.astimezone(timezone.utc) - MAX_AGE:
            continue
        if published > now.astimezone(timezone.utc) + MAX_FUTURE:
            continue
        stories.append({
            "url": link,
            "title": title,
            "summary": clean_summary(item.findtext("description")),
            "published": published.isoformat(),
        })
    stories.sort(key=lambda story: story["published"], reverse=True)
    return stories


def select_new_stories(stories, seen_urls, limit=MAX_STORIES):
    """Select newest unseen stories, deduplicating by canonical BBC URL."""
    seen = set(clean_seen_urls(seen_urls))
    selected, selected_urls = [], set()
    for story in stories:
        url = canonical_url(story.get("url"))
        if not url or url in seen or url in selected_urls:
            continue
        selected.append({**story, "url": url})
        selected_urls.add(url)
        if len(selected) >= max(0, int(limit)):
            break
    return selected


def format_digest(stories):
    """Build one compact, plain-text Telegram post with source links."""
    if not stories:
        return ""
    lines = ["⚽ PITCHIQ FOOTBALL NEWS", "BBC Sport · Latest football headlines", ""]
    for index, story in enumerate(stories, 1):
        lines.append(f"{index}. {story['title']}")
        if story.get("summary"):
            lines.append(story["summary"])
        lines.append(story["url"])
        lines.append("")
    lines.append("Headlines and summaries credited to BBC Sport. Open each source for the full report.")
    message = "\n".join(lines).strip()
    if len(message) > MAX_MESSAGE_LENGTH:
        message = message[:MAX_MESSAGE_LENGTH - 1].rsplit("\n", 1)[0].rstrip()
    return message


def load_seen():
    try:
        return clean_seen_urls(json.loads(SEEN_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return []


def save_seen(urls):
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(
        json.dumps(clean_seen_urls(urls), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def fetch_feed():
    request = urllib.request.Request(
        FEED_URL,
        headers={"User-Agent": "PitchIQ-News/1.0 (+https://spencer-pessy.github.io/pitchiq/)"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def send_digest(message, token, chat_id):
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": "false",
    }).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.load(response)
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError("Telegram did not confirm the PitchIQ news digest")
    return result


def main():
    if os.environ.get("PITCHIQ_NEWS_ENABLED", "").strip().lower() != "true":
        print("PitchIQ news publisher is safely disabled; no feed request or Telegram post made.")
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_NEWS_CHAT_ID")
    if not token or not chat_id:
        print("News publisher is enabled but TELEGRAM_BOT_TOKEN or TELEGRAM_NEWS_CHAT_ID is missing.")
        return

    now = datetime.now(timezone.utc)
    stories = parse_feed(fetch_feed(), now=now)
    seen = load_seen()
    selected = select_new_stories(stories, seen)
    if not selected:
        print("No new eligible BBC football headlines; no Telegram post sent.")
        return

    message = format_digest(selected)
    print(message)
    response = send_digest(message, token, chat_id)
    # Persist only after Telegram confirms delivery. The workflow retries this
    # file publication without rerunning the publisher, avoiding ordinary
    # duplicate sends during Git push contention.
    save_seen([story["url"] for story in selected] + seen)
    print("Telegram news digest confirmed; message_id:", response.get("result", {}).get("message_id"))


if __name__ == "__main__":
    main()
