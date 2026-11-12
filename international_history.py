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



def _elo_expected_score(ratings, match):
    home_rating = ratings[match["home"]]
    away_rating = ratings[match["away"]]
    venue_bonus = 0.0 if match["neutral"] else HOME_ADVANTAGE
    return 1.0 / (1.0 + 10.0 ** (-((home_rating + venue_bonus - away_rating) / 400.0)))


def _elo_update(ratings, match, expected_home):
    if match["home_score"] > match["away_score"]:
        actual_home = 1.0
    elif match["home_score"] == match["away_score"]:
        actual_home = 0.5
    else:
        actual_home = 0.0
    change = K_FACTOR * tournament_weight(match["tournament"]) * (actual_home - expected_home)
    ratings[match["home"]] += change
    ratings[match["away"]] -= change
    return 0 if actual_home == 1.0 else 1 if actual_home == 0.5 else 2


def _elo_gap_bucket(gap):
    for upper in (50, 100, 150, 200, 300, 500):
        if gap < upper:
            return f"0-{upper}"
    return "500+"


def backtest_elo(matches):
    """Chronological 80/20 holdout; draw calibration is fitted on training data only."""
    ordered = sorted(matches, key=lambda row: (row["date"], row["home"].casefold(), row["away"].casefold()))
    split = int(len(ordered) * 0.8)
    if split < 10 or len(ordered) - split < 5:
        raise ValueError("Not enough international results for a chronological Elo backtest")

    training_ratings = defaultdict(lambda: INITIAL_RATING)
    draw_counts = defaultdict(lambda: [0, 0])
    outcome_counts = [0, 0, 0]
    for match in ordered[:split]:
        expected = _elo_expected_score(training_ratings, match)
        outcome = _elo_update(training_ratings, match, expected)
        outcome_counts[outcome] += 1
        adjusted_gap = abs(training_ratings[match["home"]] - training_ratings[match["away"]])
        # The draw-rate bins are keyed by venue and the pre-match rating gap.
        venue_bonus = 0.0 if match["neutral"] else HOME_ADVANTAGE
        pre_match_gap = abs(
            (training_ratings[match["home"]] - (K_FACTOR * 0.0)) -
            (training_ratings[match["away"]] + (K_FACTOR * 0.0)) + venue_bonus
        )
        key = ("neutral" if match["neutral"] else "home") + ":" + _elo_gap_bucket(pre_match_gap)
        draw_counts[key][0] += 1
        if outcome == 1:
            draw_counts[key][1] += 1

    global_draw_rate = outcome_counts[1] / split
    baseline = [(count + 1) / (split + 3) for count in outcome_counts]
    calibrated_draw = {
        key: (draws + 50.0 * global_draw_rate) / (count + 50.0)
        for key, (count, draws) in draw_counts.items()
    }

    ratings = defaultdict(lambda: INITIAL_RATING)
    model_brier = model_log_loss = model_correct = 0.0
    baseline_brier = baseline_log_loss = baseline_correct = 0.0
    test_rows = []
    for index, match in enumerate(ordered):
        expected = _elo_expected_score(ratings, match)
        outcome = 0 if match["home_score"] > match["away_score"] else 1 if match["home_score"] == match["away_score"] else 2
        if index >= split:
            venue_bonus = 0.0 if match["neutral"] else HOME_ADVANTAGE
            pre_match_gap = abs(
                ratings[match["home"]] + venue_bonus - ratings[match["away"]]
            )
            key = ("neutral" if match["neutral"] else "home") + ":" + _elo_gap_bucket(pre_match_gap)
            draw_probability = calibrated_draw.get(key, global_draw_rate)
            draw_probability = min(0.45, max(0.05, draw_probability))
            conditional_home = (expected - 0.5 * draw_probability) / (1.0 - draw_probability)
            conditional_home = min(0.999, max(0.001, conditional_home))
            probabilities = [
                (1.0 - draw_probability) * conditional_home,
                draw_probability,
                (1.0 - draw_probability) * (1.0 - conditional_home),
            ]
            for outcome_index in range(3):
                target = 1.0 if outcome_index == outcome else 0.0
                model_brier += (probabilities[outcome_index] - target) ** 2
                baseline_brier += (baseline[outcome_index] - target) ** 2
            model_log_loss -= math.log(max(1e-15, probabilities[outcome]))
            baseline_log_loss -= math.log(max(1e-15, baseline[outcome]))
            model_correct += int(max(range(3), key=lambda i: probabilities[i]) == outcome)
            baseline_correct += int(max(range(3), key=lambda i: baseline[i]) == outcome)
            test_rows.append(match["date"])
        _elo_update(ratings, match, expected)

    n = len(test_rows)
    return {
        "method": "chronological 80/20 Elo holdout with training-only draw calibration",
        "training_matches": split,
        "test_matches": n,
        "holdout_start": test_rows[0],
        "holdout_end": test_rows[-1],
        "model": {
            "accuracy": round(model_correct / n, 5),
            "multiclass_brier": round(model_brier / n, 5),
            "log_loss": round(model_log_loss / n, 5),
        },
        "training_frequency_baseline": {
            "accuracy": round(baseline_correct / n, 5),
            "multiclass_brier": round(baseline_brier / n, 5),
            "log_loss": round(baseline_log_loss / n, 5),
        },
        "draw_calibration_bins": {
            key: {"training_matches": count, "draws": draws}
            for key, (count, draws) in sorted(draw_counts.items())
        },
        "note": "Holdout probabilities use only prior Elo ratings and draw-rate bins learned from the chronological training segment. Ratings update after each held-out result. Research diagnostic only; not a production forecast.",
    }


def build_snapshot(csv_text, fetched_at=None, today=None):
    today = today or date.today()
    matches, invalid = parse_results(csv_text, today=today)
    if len(matches) < MINIMUM_MATCHES:
        raise ValueError(f"Only {len(matches)} valid matches; refusing an incomplete history snapshot")
    data_through = matches[-1]["date"]
    latest = date.fromisoformat(data_through)
    return {
        "version": 2,
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
        "backtest": backtest_elo(matches),
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
    if existing.get("version") == snapshot["version"] and existing.get("source_checksum") == snapshot["source_checksum"]:
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
