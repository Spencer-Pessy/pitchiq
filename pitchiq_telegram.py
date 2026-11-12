"""Validation helpers for Telegram publishing; no I/O or side effects."""
from datetime import datetime, timedelta


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


def valid_pick_index(value):
    """Accept only integer outcome indexes; bool is not a valid pick index."""
    return isinstance(value, int) and not isinstance(value, bool) and value in (0, 1, 2)


def clean_pick_state(value):
    """Validate the small persistent ledger of published picks."""
    if not isinstance(value, dict):
        value = {}
    # Settled results take precedence over pending entries for the same fixture.
    # This makes recovery from stale/merged ledger snapshots idempotent.
    results, result_ids = [], set()
    raw_results = value.get("results", [])
    if isinstance(raw_results, list):
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            snap = snapshot_published_pick(item)
            final = item.get("final")
            if (snap is None or snap["id"] in result_ids or not valid_final(final)
                    or not valid_pick_index(item.get("pick_index"))):
                continue
            actual = 0 if final[0] > final[1] else 1 if final[0] == final[1] else 2
            snap["pick_index"] = item["pick_index"]
            results.append({**snap, "final": list(final), "actual_index": actual,
                            "correct": snap["pick_index"] == actual})
            result_ids.add(snap["id"])

    pending, seen = [], set()
    raw_pending = value.get("pending", [])
    if isinstance(raw_pending, list):
        for item in raw_pending:
            if not isinstance(item, dict):
                continue
            snap = snapshot_published_pick(item)
            if snap is None or snap["id"] in seen or snap["id"] in result_ids:
                continue
            # Preserve the original stored pick, never recompute it from a new forecast.
            if not valid_pick_index(item.get("pick_index")):
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
    return {"version": 1, "pending": pending[-300:], "results": results[-100:], "sent_ids": sent_ids[-500:]}


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
    state["results"] = (state["results"] + completed)[-100:]
    return completed, state


def pick_label(snapshot):
    return ("Home win: " + snapshot["h"], "Draw", "Away win: " + snapshot["a"])[snapshot["pick_index"]]

def eligible_forecast(record, current_statuses, now, limit):
    """Allow a Telegram pick only when the latest fixture feed confirms it is scheduled."""
    if not valid_forecast(record) or record.get("final") is not None:
        return False
    if not isinstance(current_statuses, dict):
        return False
    match_id = record.get("id")
    if isinstance(match_id, bool) or not isinstance(match_id, (str, int)):
        return False
    if current_statuses.get(str(match_id)) not in ("SCHEDULED", "TIMED"):
        return False
    kickoff = parse_kickoff(record.get("utc"))
    if kickoff is None:
        return False
    try:
        return now < kickoff < limit
    except TypeError:
        return False

def current_fixture_statuses(data, now, max_age_hours=3):
    """Return fixture statuses only from a recent, timezone-aware data snapshot."""
    if not isinstance(data, dict):
        return {}
    updated = parse_kickoff(data.get("updated"))
    if updated is None:
        return {}
    try:
        age = now - updated
    except TypeError:
        return {}
    if age.total_seconds() < 0 or age > timedelta(hours=max_age_hours):
        return {}
    matches = data.get("matches")
    if not isinstance(matches, list):
        return {}
    return {
        str(match["id"]): match.get("status")
        for match in matches
        if isinstance(match, dict) and match.get("id") is not None
        and isinstance(match.get("status"), str)
    }

