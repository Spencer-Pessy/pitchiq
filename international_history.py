"""Build a separate historical Elo-strength snapshot for men's national teams.

This is a research input only. It does not generate match probabilities or feed
club forecasts / Telegram picks. The upstream CSV is CC0 and contains men's
full internationals; it also includes some non-FIFA representative teams.
"""
import csv
import hashlib
import io
import json
import math
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

SOURCE_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
SOURCE_LICENSE = "CC0 1.0"
OUTPUT = "international_ratings.json"
MINIMUM_MATCHES = 10000
INITIAL_RATING = 1500.0
K_FACTOR = 20.0
HOME_ADVANTAGE = 65.0
TEAM_REGISTRY_PATH = Path(__file__).with_name("international_team_registry.json")


def load_team_registry(path=TEAM_REGISTRY_PATH):
    """Load the explicitly sourced FIFA member-association names and source aliases."""
    with open(path, "r", encoding="utf-8") as registry_file:
        registry = json.load(registry_file)
    names = registry.get("fifa_member_associations")
    aliases = registry.get("source_aliases", {})
    if not isinstance(names, list) or len(names) != 211 or len(set(names)) != 211:
        raise ValueError("FIFA team registry must contain 211 unique member associations")
    if not isinstance(aliases, dict):
        raise ValueError("FIFA team registry aliases must be an object")
    official = {name.casefold(): name for name in names}
    alias_map = {alias.casefold(): target for alias, target in aliases.items()}
    if any(target not in names for target in aliases.values()):
        raise ValueError("FIFA team registry alias points to an unknown member association")
    return registry, official, alias_map


def classify_team(team, registry_data=None):
    """Classify source labels without assuming every historical side is a FIFA team."""
    if registry_data is None:
        registry_data = load_team_registry()
    registry, official, aliases = registry_data
    label = (team or "").strip()
    canonical = official.get(label.casefold())
    if canonical is None:
        target = aliases.get(label.casefold())
        canonical = official.get(target.casefold()) if target else None
    if canonical:
        return {
            "canonical_team": canonical,
            "association_status": "fifa_member_association",
            "forecast_eligible": False,
        }
    return {
        "canonical_team": None,
        "association_status": "non_fifa_or_unverified",
        "forecast_eligible": False,
    }


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
    """Replay results by date; all fixtures on one date share the same prior ratings."""
    ratings = defaultdict(lambda: INITIAL_RATING)
    counts = defaultdict(int)
    last_played = {}
    ordered = sorted(matches, key=lambda row: (row["date"], row["home"].casefold(), row["away"].casefold()))
    days = []
    for match in ordered:
        if not days or days[-1][0]["date"] != match["date"]:
            days.append([match])
        else:
            days[-1].append(match)

    for day_matches in days:
        prepared = []
        for match in day_matches:
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
            prepared.append((match, change))
        for match, change in prepared:
            home, away = match["home"], match["away"]
            ratings[home] += change
            ratings[away] -= change
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
    """Chronological date-grouped 80/20 holdout; calibration uses training dates only."""
    ordered = sorted(matches, key=lambda row: (row["date"], row["home"].casefold(), row["away"].casefold()))
    unique_dates = sorted({row["date"] for row in ordered})
    split_date_index = int(len(unique_dates) * 0.8)
    if split_date_index < 1 or len(unique_dates) - split_date_index < 2:
        raise ValueError("Not enough international match dates for a chronological Elo backtest")
    split_date = unique_dates[split_date_index]
    training = [row for row in ordered if row["date"] < split_date]
    testing = [row for row in ordered if row["date"] >= split_date]
    if len(training) < 10 or len(testing) < 5:
        raise ValueError("Not enough international results for a chronological Elo backtest")

    def grouped_by_date(rows):
        groups = []
        for row in rows:
            if not groups or groups[-1][0]["date"] != row["date"]:
                groups.append([row])
            else:
                groups[-1].append(row)
        return groups

    training_ratings = defaultdict(lambda: INITIAL_RATING)
    draw_counts = defaultdict(lambda: [0, 0])
    outcome_counts = [0, 0, 0]
    for day_matches in grouped_by_date(training):
        prepared = []
        for match in day_matches:
            expected = _elo_expected_score(training_ratings, match)
            venue_bonus = 0.0 if match["neutral"] else HOME_ADVANTAGE
            pre_match_gap = abs(
                training_ratings[match["home"]] + venue_bonus - training_ratings[match["away"]]
            )
            if match["home_score"] > match["away_score"]:
                outcome = 0
            elif match["home_score"] == match["away_score"]:
                outcome = 1
            else:
                outcome = 2
            key = ("neutral" if match["neutral"] else "home") + ":" + _elo_gap_bucket(pre_match_gap)
            draw_counts[key][0] += 1
            if outcome == 1:
                draw_counts[key][1] += 1
            outcome_counts[outcome] += 1
            prepared.append((match, expected))
        # Apply results only after every fixture on the date has used the same prior state.
        for match, expected in prepared:
            _elo_update(training_ratings, match, expected)

    training_count = len(training)
    global_draw_rate = outcome_counts[1] / training_count
    baseline = [(count + 1) / (training_count + 3) for count in outcome_counts]
    calibrated_draw = {
        key: (draws + 50.0 * global_draw_rate) / (count + 50.0)
        for key, (count, draws) in draw_counts.items()
    }

    ratings = defaultdict(lambda: INITIAL_RATING)
    model_brier = model_log_loss = model_correct = 0.0
    baseline_brier = baseline_log_loss = baseline_correct = 0.0
    scored_holdout = []
    for day_matches in grouped_by_date(ordered):
        prepared = []
        for match in day_matches:
            expected = _elo_expected_score(ratings, match)
            outcome = 0 if match["home_score"] > match["away_score"] else 1 if match["home_score"] == match["away_score"] else 2
            if match["date"] >= split_date:
                venue_bonus = 0.0 if match["neutral"] else HOME_ADVANTAGE
                pre_match_gap = abs(ratings[match["home"]] + venue_bonus - ratings[match["away"]])
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
                scored_holdout.append((match, probabilities, baseline, outcome))
            prepared.append((match, expected))
        # Same-date results are applied together, after all same-date probabilities are scored.
        for match, expected in prepared:
            _elo_update(ratings, match, expected)

    def summarize_scored(rows):
        count = len(rows)
        if not count:
            return {"matches": 0}
        model_brier_sum = baseline_brier_sum = 0.0
        model_log_loss_sum = baseline_log_loss_sum = 0.0
        model_correct_count = baseline_correct_count = 0
        for match, probabilities, baseline_probabilities, outcome in rows:
            for index in range(3):
                target = 1.0 if index == outcome else 0.0
                model_brier_sum += (probabilities[index] - target) ** 2
                baseline_brier_sum += (baseline_probabilities[index] - target) ** 2
            model_log_loss_sum -= math.log(max(1e-15, probabilities[outcome]))
            baseline_log_loss_sum -= math.log(max(1e-15, baseline_probabilities[outcome]))
            model_correct_count += int(max(range(3), key=lambda i: probabilities[i]) == outcome)
            baseline_correct_count += int(max(range(3), key=lambda i: baseline_probabilities[i]) == outcome)
        return {
            "matches": count,
            "model": {
                "accuracy": round(model_correct_count / count, 5),
                "multiclass_brier": round(model_brier_sum / count, 5),
                "log_loss": round(model_log_loss_sum / count, 5),
            },
            "training_frequency_baseline": {
                "accuracy": round(baseline_correct_count / count, 5),
                "multiclass_brier": round(baseline_brier_sum / count, 5),
                "log_loss": round(baseline_log_loss_sum / count, 5),
            },
        }

    era_groups = defaultdict(list)
    competition_groups = defaultdict(list)
    major_terms = ("world cup", "european championship", "uefa euro", "copa america",
                   "african cup of nations", "asian cup", "gold cup", "nations league",
                   "confederation cup")
    for row in scored_holdout:
        year = int(row[0]["date"][:4])
        era = "before_2010" if year < 2010 else "2010s" if year < 2020 else "2020s"
        tournament = row[0]["tournament"].casefold()
        if "friendly" in tournament:
            competition_type = "friendlies"
        elif "qualification" in tournament or "qualifying" in tournament:
            competition_type = "qualifiers"
        elif any(term in tournament for term in major_terms):
            competition_type = "major_tournaments"
        else:
            competition_type = "other"
        era_groups[era].append(row)
        competition_groups[competition_type].append(row)
    holdout_slices = {
        "era": {key: summarize_scored(rows) for key, rows in sorted(era_groups.items())},
        "competition_type": {
            key: summarize_scored(rows) for key, rows in sorted(competition_groups.items())
        },
    }

    n = len(testing)
    return {
        "method": "date-grouped chronological 80/20 Elo holdout with training-only draw calibration",
        "training_matches": training_count,
        "test_matches": n,
        "holdout_start": testing[0]["date"],
        "holdout_end": testing[-1]["date"],
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
        "holdout_slices": holdout_slices,
        "draw_calibration_bins": {
            key: {"training_matches": count, "draws": draws}
            for key, (count, draws) in sorted(draw_counts.items())
        },
        "note": "Holdout probabilities use only prior-date Elo ratings and draw-rate bins learned from earlier training dates. All fixtures on the same date share the same pre-date ratings. Research diagnostic only; not a production forecast.",
    }


def build_snapshot(csv_text, fetched_at=None, today=None):
    today = today or date.today()
    matches, invalid = parse_results(csv_text, today=today)
    if len(matches) < MINIMUM_MATCHES:
        raise ValueError(f"Only {len(matches)} valid matches; refusing an incomplete history snapshot")
    data_through = matches[-1]["date"]
    latest = date.fromisoformat(data_through)
    registry, official, aliases = load_team_registry()
    team_registry = (registry, official, aliases)
    rated_teams = build_ratings(matches)
    for team in rated_teams:
        team.update(classify_team(team["team"], team_registry))
    return {
        "version": 6,
        "updated": fetched_at or datetime.now(timezone.utc).isoformat(),
        "data_through": data_through,
        "freshness_days": (today - latest).days,
        "stale": (today - latest).days > 120,
        "source": "Mart Jürisoo international_results.csv",
        "source_url": SOURCE_URL,
        "source_checksum": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
        "team_registry_checksum": hashlib.sha256(json.dumps(registry, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
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
        "team_registry": {
            "source": registry["source"],
            "source_url": registry["source_url"],
            "source_checked": registry["source_checked"],
            "member_associations": len(registry["fifa_member_associations"]),
            "fifa_member_association_teams": sum(team["association_status"] == "fifa_member_association" for team in rated_teams),
            "non_fifa_or_unverified_teams": sum(team["association_status"] == "non_fifa_or_unverified" for team in rated_teams),
            "note": registry["source_note"],
            "forecast_policy": registry["forecast_policy"],
        },
        "readiness_note": "Do not publish predictions until a separate chronological out-of-sample model and calibration review is completed.",
        "teams": rated_teams,
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
    if (existing.get("version") == snapshot["version"]
            and existing.get("source_checksum") == snapshot["source_checksum"]
            and existing.get("team_registry_checksum") == snapshot["team_registry_checksum"]):
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
