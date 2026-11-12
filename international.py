"""Refresh national-team fixtures from OpenFootball and ESPN's public scoreboard.

OpenFootball supplies a CC0 World Cup archive. ESPN's unauthenticated site
scoreboard is an additional broad fixture source for friendlies and selected
confederation competitions. ESPN's endpoint is unofficial/undocumented, so
failures are isolated per competition and the last published snapshot is kept
if every ESPN request fails.
"""
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

SOURCE = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
SOURCE_LABEL = "OpenFootball worldcup.json (CC0)"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
ESPN_LEAGUES = (
    ("fifa.friendly", "International Friendlies"),
    ("fifa.friendly.w", "Women's International Friendlies"),
    ("fifa.wwc", "FIFA Women's World Cup"),
    ("fifa.wworldq.uefa", "FIFA Women's World Cup Qualifying - UEFA"),
    ("uefa.w.nations", "UEFA Women's Nations League"),
    ("uefa.weuro", "UEFA Women's European Championship"),
    ("fifa.shebelieves", "SheBelieves Cup"),
    ("concacaf.w.gold", "CONCACAF W Gold Cup"),
    ("conmebol.america.femenina", "Copa America Femenina"),
    ("uefa.nations", "UEFA Nations League"),
    ("caf.nations_qual", "Africa Cup of Nations Qualification"),
    ("concacaf.nations.league", "CONCACAF Nations League"),
    ("fifa.worldq", "FIFA World Cup Qualifying"),
    ("fifa.world", "FIFA World Cup"),
)

WOMENS_ESPN_LEAGUES = frozenset({
    "fifa.friendly.w",
    "fifa.wwc",
    "fifa.wworldq.uefa",
    "uefa.w.nations",
    "uefa.weuro",
    "fifa.shebelieves",
    "concacaf.w.gold",
    "conmebol.america.femenina",
})


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
            "source": SOURCE_LABEL,
            "gender": "men",
        })
    if not output:
        raise ValueError("OpenFootball dataset contained no valid fixtures")
    return sorted(output, key=lambda item: item["utc"])


def normalize_espn_event(event, league_slug, league_label):
    """Convert one ESPN site scoreboard event into PitchIQ's fixture schema."""
    if not isinstance(event, dict) or not event.get("id") or not event.get("date"):
        return None
    competitions = event.get("competitions") or []
    if not competitions or not isinstance(competitions[0], dict):
        return None
    competitors = competitions[0].get("competitors") or []
    home = next((x for x in competitors if x.get("homeAway") == "home"), None)
    away = next((x for x in competitors if x.get("homeAway") == "away"), None)
    if not home or not away:
        return None
    home_name = (home.get("team") or {}).get("displayName") or (home.get("team") or {}).get("name")
    away_name = (away.get("team") or {}).get("displayName") or (away.get("team") or {}).get("name")
    if not home_name or not away_name:
        return None
    try:
        kickoff = datetime.fromisoformat(str(event["date"]).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None

    status_type = (event.get("status") or {}).get("type") or {}
    state = status_type.get("state")
    detail = " ".join(
        str(status_type.get(k) or "")
        for k in ("name", "description", "detail", "shortDetail")
    ).lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", detail).strip()

    # Do not turn every live event into 2H: ESPN's period and status text
    # distinguish first half, half-time, second half and extra time.
    if any(word in normalized for word in ("postponed", "delayed")):
        status = "PST"
    elif any(word in normalized for word in ("cancelled", "canceled")):
        status = "CANC"
    elif "abandoned" in normalized:
        status = "ABD"
    elif "suspended" in normalized:
        status = "SUSP"
    elif state == "post":
        status = "PEN" if "penalt" in normalized else "AET" if "extra time" in normalized else "FT"
    elif state == "in":
        period = status_type.get("period")
        if "half time" in normalized or "halftime" in normalized:
            status = "HT"
        elif "penalt" in normalized:
            status = "P"
        elif "extra time" in normalized or period in (3, 4):
            status = "ET"
        elif "second half" in normalized or "2nd half" in normalized or period == 2:
            status = "2H"
        elif "first half" in normalized or "1st half" in normalized or period == 1:
            status = "1H"
        else:
            status = "LIVE"
    else:
        status = "NS"

    def score_value(team):
        raw = team.get("score")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    home_score, away_score = score_value(home), score_value(away)
    score = [home_score, away_score] if state == "post" and home_score is not None and away_score is not None else None
    league_name = ((event.get("leagues") or [{}])[0]).get("name") or league_label
    venue = (competitions[0].get("venue") or {}).get("fullName") or ""
    return {
        "id": f"espn-{league_slug}-{event['id']}",
        "comp": league_name,
        "country": "International",
        "utc": kickoff,
        "status": status,
        "h": home_name,
        "a": away_name,
        "score": score,
        "venue": venue,
        "source": "ESPN public scoreboard (unofficial)",
        "gender": "women" if league_slug in WOMENS_ESPN_LEAGUES else "men",
    }


def fetch_espn_fixtures(now=None, opener=urllib.request.urlopen):
    """Fetch a rolling seven-day international window using one-day scoreboard queries."""
    now = now or datetime.now(timezone.utc)
    days = [(now.date() + timedelta(days=offset)).strftime("%Y%m%d") for offset in range(-2, 5)]
    fixtures, successful = [], set()
    request_count = 0
    total_requests = len(days) * len(ESPN_LEAGUES)
    for day in days:
        for slug, label in ESPN_LEAGUES:
            request_count += 1
            url = f"{ESPN_BASE}/{slug}/scoreboard?dates={day}"
            request = urllib.request.Request(url, headers={"User-Agent": "PitchIQ/1.0"})
            try:
                with opener(request, timeout=20) as response:
                    if response.status != 200:
                        print(f"ESPN {slug} {day} unavailable: HTTP {response.status}")
                    else:
                        payload = json.load(response)
                        if isinstance(payload, dict) and isinstance(payload.get("events"), list):
                            successful.add(slug)
                            for event in payload["events"]:
                                row = normalize_espn_event(event, slug, label)
                                if row:
                                    fixtures.append(row)
                        else:
                            print(f"ESPN {slug} {day} returned an invalid scoreboard payload")
            except urllib.error.HTTPError as error:
                print(f"ESPN {slug} {day} unavailable: HTTP {error.code}")
            except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as error:
                print(f"ESPN {slug} {day} unavailable: {error}")
            finally:
                # Pace every attempted request, including HTTP errors and non-200 responses.
                if request_count < total_requests:
                    time.sleep(0.25)
    return deduplicate(fixtures), sorted(successful)


def deduplicate(fixtures):
    """Prefer the first source row for identical kickoff/team pairs."""
    seen, output = set(), []
    for item in sorted(fixtures, key=lambda row: row["utc"]):
        key = (item["utc"], item.get("gender", "men"), item["h"].casefold(), item["a"].casefold())
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output



def merge_failed_league_fixtures(fetched, successful_leagues, previous_fixtures, now=None):
    """Keep still-relevant last-known fixtures for ESPN leagues whose requests failed."""
    now = now or datetime.now(timezone.utc)
    lower, upper = now - timedelta(days=2), now + timedelta(days=4)
    successful = set(successful_leagues)
    retained = []
    for item in previous_fixtures if isinstance(previous_fixtures, list) else []:
        if not isinstance(item, dict):
            continue
        fixture_id = str(item.get("id") or "")
        slug = next((value for value, _label in ESPN_LEAGUES
                     if fixture_id.startswith("espn-" + value + "-")), None)
        if slug is None or slug in successful:
            continue
        try:
            kickoff = datetime.fromisoformat(str(item.get("utc", "")).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if kickoff.tzinfo is None or kickoff.utcoffset() is None or not lower <= kickoff <= upper:
            continue
        retained.append(item)
    return deduplicate(list(fetched or []) + retained)


def fetch_dataset():
    request = urllib.request.Request(SOURCE, headers={"User-Agent": "PitchIQ/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"OpenFootball returned HTTP {response.status}")
        payload = json.load(response)
    return payload


def main():
    world_cup = normalize_matches(fetch_dataset())
    espn, successful_leagues = fetch_espn_fixtures()
    if not successful_leagues:
        print("All ESPN scoreboard requests failed; leaving the last published international.json untouched.")
        return
    previous_fixtures = []
    try:
        with open("international.json", encoding="utf-8") as previous:
            previous_fixtures = json.load(previous).get("fixtures", [])
    except (OSError, ValueError, TypeError):
        pass
    # A successful empty response means that league has no fixtures. A failed
    # request means unknown: preserve its still-relevant last-known fixtures.
    espn = merge_failed_league_fixtures(
        espn, successful_leagues, previous_fixtures
    )
    fixtures = deduplicate(world_cup + espn)
    snapshot = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "source": "OpenFootball CC0 archive + ESPN public scoreboard",
        "source_url": SOURCE,
        "scope": "World Cup archive plus rolling international friendlies and selected confederation competitions; ESPN coverage is unofficial and may be incomplete",
        "sources": {
            "openfootball_world_cup": len(world_cup),
            "espn_fixtures": len(espn),
            "espn_leagues_checked": list(ESPN_LEAGUES[i][0] for i in range(len(ESPN_LEAGUES))),
            "espn_leagues_successful": successful_leagues,
        },
        "fixtures": fixtures,
    }
    with open("international.json", "w", encoding="utf-8") as output:
        json.dump(snapshot, output, ensure_ascii=False)
    print("International fixtures stored:", len(fixtures))
    print("ESPN leagues responding:", ", ".join(successful_leagues))
    print("ESPN fixtures stored:", len(espn))


if __name__ == "__main__":
    main()
