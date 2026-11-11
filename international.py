"""Refresh national-team World Cup fixtures from OpenFootball's CC0 dataset.

No API key or paid service is required. The source is community-maintained and
currently covers World Cup tournament fixtures/results, not all friendlies or
qualifiers. The main football-data.org feed separately covers WC and EURO.
"""
import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta

SOURCE = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
SOURCE_LABEL = "OpenFootball worldcup.json (CC0)"


def parse_kickoff(day, time_text):
    """Convert Football.TXT time such as '13:00 UTC-6' into a UTC ISO timestamp."""
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?:\s+UTC([+-])(\d{1,2})(?::?(\d{2}))?)?", str(time_text or "").strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    sign = -1 if match.group(3) == "-" else 1
    offset_hours = int(match.group(4) or 0)
    offset_minutes = int(match.group(5) or 0)
    if offset_hours > 14 or offset_minutes > 59:
        return None
    local = datetime.fromisoformat(day).replace(
        hour=hour, minute=minute,
        tzinfo=timezone(sign * timedelta(hours=offset_hours, minutes=offset_minutes)),
    )
    return local.astimezone(timezone.utc).isoformat()


def normalize_matches(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
        raise ValueError("OpenFootball response has no matches list")
    output = []
    for index, match in enumerate(payload["matches"]):
        if not isinstance(match, dict):
            continue
        day = match.get("date")
        home, away = match.get("team1"), match.get("team2")
        kickoff = parse_kickoff(day, match.get("time"))
        if not day or not home or not away or not kickoff:
            continue
        score_data = match.get("score") or {}
        full_time = score_data.get("ft")
        score = full_time if isinstance(full_time, list) and len(full_time) == 2 else None
        output.append({
            "id": f"openfootball-wc2026-{index}-{day}",
            "comp": payload.get("name") or "FIFA World Cup 2026",
            "country": "World",
            "utc": kickoff,
            "status": "FT" if score is not None else "NS",
            "h": home,
            "a": away,
            "score": score,
            "venue": match.get("ground") or "",
        })
    if not output:
        raise ValueError("OpenFootball dataset contained no valid fixtures")
    return sorted(output, key=lambda item: item["utc"])


def fetch_dataset():
    request = urllib.request.Request(SOURCE, headers={"User-Agent": "PitchIQ/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"OpenFootball returned HTTP {response.status}")
        payload = json.load(response)
    return payload


def main():
    fixtures = normalize_matches(fetch_dataset())
    snapshot = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE_LABEL,
        "source_url": SOURCE,
        "scope": "2026 FIFA World Cup tournament only; not a full international calendar",
        "fixtures": fixtures,
    }
    with open("international.json", "w", encoding="utf-8") as output:
        json.dump(snapshot, output, ensure_ascii=False)
    print("OpenFootball World Cup fixtures stored:", len(fixtures))


if __name__ == "__main__":
    main()
