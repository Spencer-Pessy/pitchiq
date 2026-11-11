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
