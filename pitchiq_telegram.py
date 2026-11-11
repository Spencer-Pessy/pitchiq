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


def clean_seen_urls(value, limit=200):
    """Return a bounded list of non-empty URL strings from persisted history."""
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value
            if isinstance(item, str) and item.strip()][-limit:]


def snapshot_published_pick(record):
    """Freeze the exact pre-match pick and probabilities that were published."""
    if not valid_forecast(record):
        return None
    match_id = record.get("id")
    if isinstance(match_id, bool) or not isinstance(match_id, (str, int)) or not str(match_id).strip():
        return None
    probabilities = record["p"]
    values = {key: float(probabilities[key]) for key in ("ph", "pd", "pa")}
    index = max(range(3), key=lambda i: values[("ph", "pd", "pa")[i]])
    return {
        "id": str(match_id), "h": record["h"], "a": record["a"],
        "comp": record["comp"], "utc": record["utc"], "p": values,
        "pick_index": index
    }


def clean_pick_state(value):
    """Validate the small persistent ledger of published picks."""
    if not isinstance(value, dict):
        value = {}
    pending, seen = [], set()
    raw_pending = value.get("pending", [])
    if isinstance(raw_pending, list):
        for item in raw_pending:
            if not isinstance(item, dict):
                continue
            snap = snapshot_published_pick(item)
            if snap is None or snap["id"] in seen:
                continue
            # Preserve the original stored pick, never recompute it from a new forecast.
            if item.get("pick_index") not in (0, 1, 2):
                continue
            snap["pick_index"] = item["pick_index"]
            pending.append(snap)
            seen.add(snap["id"])
    raw_ids = value.get("sent_ids", [])
    sent_ids = []
    if isinstance(raw_ids, list):
        for item in raw_ids:
            if isinstance(item, (str, int)) and not isinstance(item, bool) and str(item).strip():
                key = str(item)
                if key not in sent_ids:
                    sent_ids.append(key)
    return {"version": 1, "pending": pending[-300:], "sent_ids": sent_ids[-500:]}


def resolve_published_picks(state, predictions):
    """Match only previously published IDs to valid final scores."""
    state = clean_pick_state(state)
    by_id = {}
    for record in predictions if isinstance(predictions, list) else []:
        if isinstance(record, dict) and record.get("id") is not None:
            by_id[str(record["id"])] = record
    completed, pending = [], []
    for snap in state["pending"]:
        current = by_id.get(snap["id"])
        final = current.get("final") if isinstance(current, dict) else None
        if not valid_final(final):
            pending.append(snap)
            continue
        actual = 0 if final[0] > final[1] else 1 if final[0] == final[1] else 2
        completed.append({
            **snap, "final": list(final), "actual_index": actual,
            "correct": snap["pick_index"] == actual
        })
    state["pending"] = pending
    return completed, state


def pick_label(snapshot):
    return ("Home win: " + snapshot["h"], "Draw", "Away win: " + snapshot["a"])[snapshot["pick_index"]]
