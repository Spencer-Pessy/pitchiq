"""Competition-aware data grouping helpers for PitchIQ."""

from datetime import datetime
import math
import re
import unicodedata

INTERNATIONAL_COMPETITIONS = frozenset({"WC", "EC"})
def validate_competition_fixtures(payload, competition_code):
    """Validate a football-data.org fixture response before it enters the updater."""
    if not isinstance(payload, dict):
        raise ValueError("response must be an object")
    competition = payload.get("competition")
    if (not isinstance(competition, dict)
            or not isinstance(competition.get("name"), str)
            or not competition["name"].strip()):
        raise ValueError("competition name is missing")
    fixtures = payload.get("matches")
    if not isinstance(fixtures, list):
        raise ValueError("matches must be a list")

    require_team_ids = is_club_competition(competition_code)
    for index, fixture in enumerate(fixtures):
        label = f"{competition_code} fixture #{index + 1}"
        if not isinstance(fixture, dict):
            raise ValueError(f"{label} must be an object")
        fixture_id = fixture.get("id")
        if not isinstance(fixture_id, int) or isinstance(fixture_id, bool):
            raise ValueError(f"{label} has an invalid fixture ID")
        status = fixture.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ValueError(f"{label} has no valid status")
        kickoff = fixture.get("utcDate")
        if not isinstance(kickoff, str):
            raise ValueError(f"{label} has no kickoff timestamp")
        try:
            parsed_kickoff = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{label} has an invalid kickoff timestamp") from error
        if parsed_kickoff.tzinfo is None or parsed_kickoff.utcoffset() is None:
            raise ValueError(f"{label} kickoff timestamp must include a timezone")

        for side in ("homeTeam", "awayTeam"):
            team = fixture.get(side)
            if not isinstance(team, dict):
                raise ValueError(f"{label} is missing {side}")
            team_name = team.get("shortName") or team.get("name") or team.get("tla")
            if not isinstance(team_name, str) or not team_name.strip():
                raise ValueError(f"{label} has no display name for {side}")
            team_id = team.get("id")
            if require_team_ids and (not isinstance(team_id, int) or isinstance(team_id, bool)):
                raise ValueError(f"{label} has no valid team ID for {side}")

        score = fixture.get("score")
        full_time = score.get("fullTime") if isinstance(score, dict) else None
        if status == "FINISHED":
            if not isinstance(full_time, dict):
                raise ValueError(f"{label} is finished but has no full-time score")
            for side in ("home", "away"):
                value = full_time.get(side)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f"{label} has an invalid finished {side} score")
        elif full_time is not None:
            if not isinstance(full_time, dict):
                raise ValueError(f"{label} full-time score must be an object or null")
            for side in ("home", "away"):
                value = full_time.get(side)
                if value is not None and (
                    not isinstance(value, int) or isinstance(value, bool) or value < 0
                ):
                    raise ValueError(f"{label} has an invalid {side} score")

    return fixtures




def is_club_competition(code):
    """Return whether a competition belongs in the club forecast pipeline."""
    return code not in INTERNATIONAL_COMPETITIONS

_TEAM_NAME_STOPWORDS = {
    "fc", "cf", "afc", "ac", "as", "ssc", "sc", "sv", "vfb", "vfl", "fsv",
    "rb", "1", "de", "the", "club", "calcio", "fk", "sk", "us", "ud",
    "cd", "rc", "rcd", "bsc", "tsg", "if",
}


def build_head_to_head(matches, home_team_id, away_team_id, before_utc, limit=5):
    """Summarize completed meetings before kickoff from the upcoming home team's perspective."""
    empty = {"played": 0, "home_wins": 0, "draws": 0, "away_wins": 0,
             "home_goals": 0, "away_goals": 0, "meetings": []}
    if home_team_id is None or away_team_id is None or home_team_id == away_team_id:
        return empty
    cutoff = datetime.fromisoformat(str(before_utc).replace("Z", "+00:00"))
    rows = []
    for match in matches:
        if match.get("status") != "FINISHED":
            continue
        try:
            kickoff = datetime.fromisoformat(str(match.get("utcDate", "")).replace("Z", "+00:00"))
            if kickoff >= cutoff:
                continue
            actual_home = match.get("homeTeam", {}).get("id")
            actual_away = match.get("awayTeam", {}).get("id")
            if not ((actual_home == home_team_id and actual_away == away_team_id) or
                    (actual_home == away_team_id and actual_away == home_team_id)):
                continue
            scores = match.get("score", {}).get("fullTime", {})
            hg, ag = scores.get("home"), scores.get("away")
            if not isinstance(hg, int) or isinstance(hg, bool) or not isinstance(ag, int) or isinstance(ag, bool):
                continue
            home_goals, away_goals = (hg, ag) if actual_home == home_team_id else (ag, hg)
            rows.append({
                "utc": kickoff.isoformat(),
                "comp": match.get("_cn") or match.get("competition", {}).get("name") or "Competition unavailable",
                "home": match.get("homeTeam", {}).get("shortName") or match.get("homeTeam", {}).get("name") or "Home",
                "away": match.get("awayTeam", {}).get("shortName") or match.get("awayTeam", {}).get("name") or "Away",
                "score": [hg, ag],
                "home_team_goals": home_goals, "away_team_goals": away_goals,
            })
        except (TypeError, ValueError, AttributeError):
            continue
    rows.sort(key=lambda row: row["utc"], reverse=True)
    meetings = rows[:max(0, int(limit))]
    hw = sum(row["home_team_goals"] > row["away_team_goals"] for row in meetings)
    aw = sum(row["home_team_goals"] < row["away_team_goals"] for row in meetings)
    return {
        "played": len(meetings), "home_wins": hw, "draws": len(meetings) - hw - aw,
        "away_wins": aw,
        "home_goals": sum(row["home_team_goals"] for row in meetings),
        "away_goals": sum(row["away_team_goals"] for row in meetings),
        "meetings": meetings,
    }


def normalize_team_name(value):
    """Normalize harmless spelling, punctuation, accents and club suffixes."""
    if not isinstance(value, str):
        return ""
    value = value.translate(str.maketrans({
        "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
        "ß": "ss", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
        "ð": "d", "Ð": "D", "þ": "th", "Þ": "TH",
    }))
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9 ]", " ", value)
    return " ".join(word for word in value.split() if word not in _TEAM_NAME_STOPWORDS)


def same_team_name(left, right):
    """Match team names conservatively; ambiguous fuzzy matches are rejected."""
    a, b = normalize_team_name(left), normalize_team_name(right)
    return bool(a and b and a == b)



def goal_average_keys(code):
    """Return aggregation buckets without mixing international and club goals."""
    if code in INTERNATIONAL_COMPETITIONS:
        return code, "INTL"
    return code, "CLUB"


def average_bucket(code, counts):
    """Choose a stable goal-average bucket for a competition."""
    count = counts.get(code, 0)
    if code in INTERNATIONAL_COMPETITIONS and count < 20:
        return "INTL"
    if code == "CL" or count < 20:
        return "CLUB"
    return code


def build_feed_health(fixture_counts, standings_codes, published_match_count, standings_failed=()):
    """Summarize source coverage without exposing credentials or raw responses."""
    fixture_counts = dict(sorted(fixture_counts.items()))
    standings_codes = sorted(set(standings_codes))
    # World Cup and EURO are tournament feeds, not domestic league tables.
    # Their lack of a TOTAL standings table is expected, not a source failure.
    standings_failed = sorted(set(standings_failed) - INTERNATIONAL_COMPETITIONS)
    return {
        "fixture_competitions": len(fixture_counts),
        "fixture_counts": fixture_counts,
        "fixture_total": sum(fixture_counts.values()),
        "international_fixture_total": sum(
            count for code, count in fixture_counts.items()
            if code in INTERNATIONAL_COMPETITIONS
        ),
        "standings_available": standings_codes,
        "standings_competitions": len(standings_codes),
        "standings_failed": standings_failed,
        "standings_failures": len(standings_failed),
        "published_match_count": published_match_count,
    }


def team_venue_stats(history, home, prior_for, prior_against, elo, shrink=6, form_limit=5):
    """Build venue-shrunk scoring inputs and disclose their supporting samples."""
    rows = [row for row in history if row[0] == home]
    count = len(rows)
    gf = (sum(row[1] for row in rows) + shrink * prior_for) / (count + shrink)
    ga = (sum(row[2] for row in rows) + shrink * prior_against) / (count + shrink)
    recent = history[-form_limit:] if form_limit else []
    return {
        "gf": round(gf, 2),
        "ga": round(ga, 2),
        "elo": int(elo),
        "form": "".join(row[3] for row in recent),
        "out": 0,
        "venue_matches": count,
        "form_matches": len(recent),
        "form_scope": "all_venues",
    }


def player_goals_per_appearance(goals, appearances):
    """Return goals per appearance, or None when source data is incomplete."""
    try:
        goals = float(goals)
        appearances = float(appearances)
    except (TypeError, ValueError):
        return None
    if goals < 0 or appearances <= 0:
        return None
    return round(goals / appearances, 3)



def player_rate_stats(goals, assists, appearances):
    """Return per-appearance scoring and contribution rates when data is valid."""
    gpm = player_goals_per_appearance(goals, appearances)
    apm = player_goals_per_appearance(assists, appearances)
    gapm = None if gpm is None or apm is None else round(gpm + apm, 3)
    return {"gpm": gpm, "apm": apm, "gapm": gapm}

def is_international_fixture(item):
    """Identify senior/national-team fixtures from API-Football responses."""
    league = item.get("league") or {}
    teams = item.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}

    # Explicit team metadata is the strongest signal when supplied.
    if home.get("national") is True and away.get("national") is True:
        return True
    if home.get("national") is False or away.get("national") is False:
        return False

    name = str(league.get("name") or "").strip().casefold()
    country = str(league.get("country") or "").strip().casefold()
    if "club" in name:
        return False

    international_terms = (
        "world cup", "euro championship", "european championship",
        "africa cup of nations", "afc asian cup", "asian cup",
        "copa america", "gold cup", "nations league", "gulf cup",
        "ofc nations cup", "cosafa cup", "cecafa", "arab cup",
        "olympics men", "olympics women", "friendlies", "fifa series",
        "african nations championship", "asean championship",
        "caribbean cup", "baltic cup", "kirin cup", "saff championship",
        "shebelieves cup", "finalissima",
    )
    # A global competition label alone is not enough: API-Football also
    # tags some women's club tournaments as World/International.
    if country in {"world", "international"}:
        return any(term in name for term in international_terms)
    return any(term in name for term in international_terms)


def forecast_input_snapshot(stats, calibration=None):
    """Capture the exact inputs and calibration used for a new forecast."""
    team_fields = ("gf", "ga", "elo", "form", "out", "venue_matches", "form_matches", "form_scope")
    def team_snapshot(team):
        return {key: team.get(key) for key in team_fields if key in team}
    return {
        "schema": 2,
        "home": team_snapshot(stats.get("h", {})),
        "away": team_snapshot(stats.get("a", {})),
        "league_home": stats.get("lh"),
        "league_away": stats.get("la"),
        "calibration": {
            "kh": (calibration or {}).get("kh", 1.0),
            "ka": (calibration or {}).get("ka", 1.0),
        },
    }



def goal_rate_calibration(predictions, minimum_results=10, prior_strength=120,
                          lower=0.85, upper=1.15):
    """Estimate bounded goal-rate calibration from valid settled forecasts only."""
    rows = []
    for item in predictions if isinstance(predictions, (list, tuple)) else []:
        if not isinstance(item, dict):
            continue
        final = item.get("final")
        forecast = item.get("p")
        if not isinstance(final, (list, tuple)) or len(final) != 2 or not isinstance(forecast, dict):
            continue
        if any(isinstance(value, bool) for value in final):
            continue
        try:
            actual_home, actual_away = (float(value) for value in final)
            predicted_home = float(forecast.get("rlh", forecast.get("lh")))
            predicted_away = float(forecast.get("rla", forecast.get("la")))
        except (TypeError, ValueError, OverflowError):
            continue
        values = (actual_home, actual_away, predicted_home, predicted_away)
        if (not all(math.isfinite(value) for value in values)
                or actual_home < 0 or actual_away < 0
                or not actual_home.is_integer() or not actual_away.is_integer()
                or predicted_home <= 0 or predicted_away <= 0):
            continue
        rows.append(values)

    calibration = {"kh": 1.0, "ka": 1.0}
    count = len(rows)
    if count < minimum_results:
        return calibration, count

    weight = count / (count + prior_strength)
    mean_home_rate = sum(row[2] for row in rows) / count
    mean_away_rate = sum(row[3] for row in rows) / count
    mean_home_goals = sum(row[0] for row in rows) / count
    mean_away_goals = sum(row[1] for row in rows) / count
    calibration["kh"] = round(min(upper, max(lower,
        1 + (mean_home_goals / mean_home_rate - 1) * weight)), 4)
    calibration["ka"] = round(min(upper, max(lower,
        1 + (mean_away_goals / mean_away_rate - 1) * weight)), 4)
    return calibration, count



def clean_prediction_ledger(value):
    """Return a safe ID-keyed ledger, dropping only malformed non-record entries."""
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item for key, item in value.items()
        if isinstance(item, dict) and str(key).strip()
    }


def record_forward_evaluations(existing, fixtures, finished_scores, now, predict_fn, snapshot_fn):
    """Create immutable research forecasts and attach final scores when available.

    This separate ledger lets new model experiments start from already-published
    upcoming fixtures without rewriting the public prediction history.
    """
    ledger = clean_prediction_ledger(existing)
    for fixture in fixtures:
        if fixture.get("status") not in ("SCHEDULED", "TIMED"):
            continue
        key = str(fixture["id"])
        kickoff = datetime.fromisoformat(fixture["utc"].replace("Z", "+00:00"))
        if kickoff <= now or key in ledger:
            continue
        stats = fixture["s"]
        ledger[key] = {
            "id": fixture["id"], "comp": fixture["comp"], "code": fixture["code"],
            "utc": fixture["utc"], "h": fixture["h"], "a": fixture["a"],
            "p": predict_fn(stats), "inputs": snapshot_fn(stats),
            "final": None, "made": now.isoformat(), "evaluation_only": True,
        }

    for item in ledger.values():
        if item.get("final") is not None:
            continue
        score = finished_scores.get(item.get("id"), finished_scores.get(str(item.get("id"))))
        if score is not None:
            item["final"] = list(score)
    return ledger


def backfill_market_odds(predictions, odds_events, snapshot_updated, now, same_team, max_time_difference_hours=6):
    """Attach the first available pre-kickoff market snapshot without rewriting forecasts."""
    attached = 0
    try:
        snapshot_time = datetime.fromisoformat(str(snapshot_updated).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return attached
    if snapshot_time > now or not isinstance(odds_events, list):
        return attached
    for item in predictions.values():
        if item.get("odds") is not None:
            continue
        kickoff_text = item.get("utc")
        if not kickoff_text:
            continue
        try:
            kickoff = datetime.fromisoformat(kickoff_text.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if kickoff <= now or snapshot_time >= kickoff:
            continue
        for event in odds_events:
            try:
                event_time = datetime.fromisoformat(event["commence"].replace("Z", "+00:00"))
                prices = [float(value) for value in event["odds"]]
                if (len(prices) != 3
                        or abs((event_time - kickoff).total_seconds()) > max_time_difference_hours * 3600
                        or not all(value > 1.0 and value < 1000 for value in prices)):
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            if same_team(event.get("home"), item.get("h")) and same_team(event.get("away"), item.get("a")):
                item["odds"] = prices
                item["odds_updated"] = snapshot_time.isoformat()
                attached += 1
                break
    return attached
