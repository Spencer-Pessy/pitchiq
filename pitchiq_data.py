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
    standings_failed = sorted(set(standings_failed))
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
