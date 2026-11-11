"""Competition-aware data grouping helpers for PitchIQ."""

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
    if country in {"world", "international"}:
        return True

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
    return any(term in name for term in international_terms)
