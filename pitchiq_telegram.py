"""Validation helpers for Telegram publishing; no I/O or side effects."""
from datetime import datetime


def parse_kickoff(value):
    """Parse an ISO kickoff only when it includes an explicit timezone."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None and result.utcoffset() is not None else None


def valid_probabilities(value):
    """Require finite, bounded 1X2 probabilities that approximately sum to one."""
    if not isinstance(value, dict):
        return False
    keys = ("ph", "pd", "pa")
    numbers = []
    for key in keys:
        item = value.get(key)
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return False
        if not 0 <= item <= 1:
            return False
        numbers.append(float(item))
    return abs(sum(numbers) - 1.0) <= 0.02


def valid_forecast(record):
    """Check the minimum fields needed to safely publish a match forecast."""
    if not isinstance(record, dict):
        return False
    if not all(isinstance(record.get(k), str) and record[k].strip() for k in ("h", "a", "comp")):
        return False
    if parse_kickoff(record.get("utc")) is None:
        return False
    return valid_probabilities(record.get("p"))


def valid_final(value):
    """Accept only a two-team, non-negative integer final score."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    return all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in value)
