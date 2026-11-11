"""Competition-aware data grouping helpers for PitchIQ."""

from datetime import datetime

INTERNATIONAL_COMPETITIONS = frozenset({"WC", "EC"})


def goal_average_keys(code):
    """Return aggregation buckets without mixing international and club goals."""
    if code in INTERNATIONAL_COMPETITIONS:
        return code, "INTL", "ALL"
    return code, "ALL"


def average_bucket(code, counts):
    """Choose a stable goal-average bucket for a competition."""
    count = counts.get(code, 0)
    if code in INTERNATIONAL_COMPETITIONS and count < 20:
        return "INTL"
    if code == "CL" or count < 20:
        return "ALL"
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


def record_forward_evaluations(existing, fixtures, finished_scores, now, predict_fn, snapshot_fn):
    """Create immutable research forecasts and attach final scores when available.

    This separate ledger lets new model experiments start from already-published
    upcoming fixtures without rewriting the public prediction history.
    """
    ledger = existing if isinstance(existing, dict) else {}
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
                if (abs((event_time - kickoff).total_seconds()) > max_time_difference_hours * 3600
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
