"""Build a separate historical Elo-strength snapshot for men's national teams.

This is a research input only. It does not generate match probabilities or feed
club forecasts / Telegram picks. The upstream CSV is CC0 and contains men's
full internationals; it also includes some non-FIFA representative teams.
"""
import csv
import hashlib
import io
import json
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone

SOURCE_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
SOURCE_LICENSE = "CC0 1.0"
OUTPUT = "international_ratings.json"
MINIMUM_MATCHES = 10000
INITIAL_RATING = 1500.0
K_FACTOR = 20.0
HOME_ADVANTAGE = 65.0


def parse_results(csv_text, today=None):
    """Parse and validate the source CSV; return chronological full-time results."""
    today = today or date.today()
    reader = csv.DictReader(io.StringIO(csv_text))
    required = {
        "date", "home_team", "away_team", "home_score", "away_score",
        "tournament", "neutral",
    }
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError("International results CSV is missing required columns")

    rows, seen = [], set()
    invalid = 0
    for raw in reader:
        try:
            match_date = date.fromisoformat((raw.get("date") or "").strip())
            home = (raw.get("home_team") or "").strip()
            away = (raw.get("away_team") or "").strip()
            home_score = int(raw.get("home_score"))
            away_score = int(raw.get("away_score"))
            neutral_text = (raw.get("neutral") or "").strip().upper()
            if neutral_text not in ("TRUE", "FALSE"):
                raise ValueError("invalid neutral flag")
            if not home or not away or home.casefold() == away.casefold():
                raise ValueError("invalid team names")
            if home_score < 0 or away_score < 0 or match_date > today:
                raise ValueError("invalid score or future match date")
            tournament = (raw.get("tournament") or "Unknown").strip() or "Unknown"
            key = (match_date.isoformat(), home.casefold(), away.casefold(), tournament.casefold())
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "date": match_date.isoformat(),
                "home": home,
                "away": away,
                "home_score": home_score,
                "away_score": away_score,
                "tournament": tournament,
                "neutral": neutral_text == "TRUE",
            })
        except (TypeError, ValueError):
            invalid += 1

    rows.sort(key=lambda row: (row["date"], row["home"].casefold(), row["away"].casefold()))
    if not rows:
        raise ValueError("International results source contained no valid completed matches")
    return rows, invalid


def tournament_weight(tournament):
    """Conservative match-importance weights for the Elo research baseline."""
    name = (tournament or "").casefold()
    if "friendly" in name:
        return 0.75
    if "qualification" in name or "qualifying" in name:
        return 1.10
    if "world cup" in name and "qualification" not in name and "qualifying" not in name:
        return 1.50
    if any(term in name for term in (
        "european championship", "uefa euro", "copa america",
        "african cup of nations", "asian cup", "gold cup",
        "nations league", "confederation cup",
    )):
        return 1.25
    return 1.0


def build_ratings(matches):
    """Replay results chronologically; return end-of-sample Elo and team counts."""
    ratings = defaultdict(lambda: INITIAL_RATING)
    counts = defaultdict(int)
    last_played = {}

    for match in sorted(matches, key=lambda row: (row["date"], row["home"].casefold(), row["away"].casefold())):
        home, away = match["home"], match["away"]
        home_rating, away_rating = ratings[home], ratings[away]
        venue_bonus = 0.0 if match["neutral"] else HOME_ADVANTAGE
        expected_home = 1.0 / (1.0 + 10.0 ** (-((home_rating + venue_bonus - away_rating) / 400.0)))
        if match["home_score"] > match["away_score"]:
            actual_home = 1.0
        elif match["home_score"] == match["away_score"]:
            actual_home = 0.5
        else:
            actual_home = 0.0
        change = K_FACTOR * tournament_weight(match["tournament"]) * (actual_home - expected_home)
        ratings[home] = home_rating + change
        ratings[away] = away_rating - change
        counts[home] += 1
        counts[away] += 1
        last_played[home] = match["date"]
        last_played[away] = match["date"]

    teams = [
        {
            "team": team,
            "elo": round(ratings[team], 2),
            "matches": counts[team],
            "last_match": last_played[team],
        }
        for team in sorted(ratings, key=str.casefold)
    ]
    return teams


def build_snapshot(csv_text, fetched_at=None, today=None):
    today = today or date.today()
    matches, invalid = parse_results(csv_text, today=today)
    if len(matches) < MINIMUM_MATCHES:
        raise ValueError(f"Only {len(matches)} valid matches; refusing an incomplete history snapshot")
    data_through = matches[-1]["date"]
    latest = date.fromisoformat(data_through)
    return {
        "version": 1,
        "updated": fetched_at or datetime.now(timezone.utc).isoformat(),
        "data_through": data_through,
        "freshness_days": (today - latest).days,
        "stale": (today - latest).days > 120,
        "source": "Mart Jürisoo international_results.csv",
        "source_url": SOURCE_URL,
        "source_checksum": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
        "license": SOURCE_LICENSE,
        "scope": "Men's full internationals; source also contains some non-FIFA representative teams",
        "matches_processed": len(matches),
        "invalid_rows_skipped": invalid,
        "method": {
            "name": "chronological Elo research baseline",
            "initial_rating": INITIAL_RATING,
            "k_factor": K_FACTOR,
            "home_advantage_points": HOME_ADVANTAGE,
            "neutral_venue_home_advantage": 0,
            "note": "Ratings are strength priors only, not calibrated 1X2 probabilities",
        },
        "ready_for_forecasts": False,
        "readiness_note": "Do not publish predictions until a separate chronological out-of-sample model and calibration review is completed.",
        "teams": build_ratings(matches),
    }


def main():
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "PitchIQ/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"International results source returned HTTP {response.status}")
        csv_text = response.read().decode("utf-8-sig")
    snapshot = build_snapshot(csv_text)
    try:
        with open(OUTPUT, "r", encoding="utf-8") as existing_file:
            existing = json.load(existing_file)
    except (OSError, ValueError):
        existing = {}
    if existing.get("source_checksum") == snapshot["source_checksum"]:
        print("International historical source is unchanged; preserving the existing snapshot.")
        return
    with open(OUTPUT, "w", encoding="utf-8") as output:
        json.dump(snapshot, output, ensure_ascii=False, separators=(",", ":"))
    print("International historical matches processed:", snapshot["matches_processed"])
    print("National teams / representative sides rated:", len(snapshot["teams"]))
    print("History through:", snapshot["data_through"])
    print("Snapshot stale:", snapshot["stale"])
    print("Forecasts enabled:", snapshot["ready_for_forecasts"])


if __name__ == "__main__":
    main()
