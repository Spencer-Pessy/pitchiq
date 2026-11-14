"""Cached, quota-aware historical head-to-head enrichment for PitchIQ."""

from datetime import datetime, timezone, timedelta

CACHE_SCHEMA = 1
H2H_REFRESH_HOURS = 24
H2H_REQUESTS_PER_REFRESH = 5


def _parse_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def normalize_h2h_cache(value):
    if not isinstance(value, dict):
        value = {}
    entries = value.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    clean = {}
    for key, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        matches = entry.get("matches")
        clean[str(key)] = {
            "home_team_id": entry.get("home_team_id"),
            "away_team_id": entry.get("away_team_id"),
            "attempted_at": entry.get("attempted_at"),
            "fetched_at": entry.get("fetched_at"),
            "matches": [row for row in matches if isinstance(row, dict)] if isinstance(matches, list) else [],
        }
    return {"schema": CACHE_SCHEMA, "entries": clean}


def _entry_is_fresh(entry, now, refresh_hours=H2H_REFRESH_HOURS):
    # A failed request also gets a cooldown, preventing repeated forbidden or
    # unavailable endpoints from consuming the free request allowance every run.
    stamp = _parse_time(entry.get("attempted_at")) or _parse_time(entry.get("fetched_at"))
    return stamp is not None and now - stamp < timedelta(hours=refresh_hours)


def refresh_h2h_cache(fixtures, cache, fetch, now=None, max_requests=H2H_REQUESTS_PER_REFRESH):
    """Refresh a small number of nearest upcoming fixtures, retaining stale data on failure."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cache = normalize_h2h_cache(cache)
    entries = cache["entries"]
    candidates = []
    for fixture in fixtures if isinstance(fixtures, list) else []:
        if not isinstance(fixture, dict) or fixture.get("status") not in ("SCHEDULED", "TIMED"):
            continue
        fixture_id = fixture.get("id")
        home_id = (fixture.get("homeTeam") or {}).get("id")
        away_id = (fixture.get("awayTeam") or {}).get("id")
        kickoff = _parse_time(fixture.get("utcDate"))
        if not isinstance(fixture_id, int) or isinstance(fixture_id, bool):
            continue
        if home_id is None or away_id is None or home_id == away_id or kickoff is None or kickoff <= now:
            continue
        if _entry_is_fresh(entries.get(str(fixture_id), {}), now):
            continue
        candidates.append((kickoff, fixture_id, home_id, away_id))
    candidates.sort(key=lambda item: item[0])

    requested = 0
    for _kickoff, fixture_id, home_id, away_id in candidates[:max(0, int(max_requests))]:
        key = str(fixture_id)
        previous = entries.get(key, {})
        entry = {
            "home_team_id": home_id,
            "away_team_id": away_id,
            "attempted_at": now.isoformat(),
            "fetched_at": previous.get("fetched_at"),
            "matches": previous.get("matches", []),
        }
        # Team IDs are part of the cache identity; never reuse another pairing.
        if entry["home_team_id"] != previous.get("home_team_id") or entry["away_team_id"] != previous.get("away_team_id"):
            entry["matches"] = []
            entry["fetched_at"] = None
        requested += 1
        try:
            payload = fetch(fixture_id)
        except Exception:
            payload = None
        rows = payload.get("matches") if isinstance(payload, dict) else None
        if isinstance(rows, list):
            entry["matches"] = [row for row in rows if isinstance(row, dict)]
            entry["fetched_at"] = now.isoformat()
        entries[key] = entry
    return cache, requested


def cached_h2h_matches(cache, fixture_id, home_team_id=None, away_team_id=None):
    entry = normalize_h2h_cache(cache)["entries"].get(str(fixture_id), {})
    if home_team_id is not None and entry.get("home_team_id") != home_team_id:
        return []
    if away_team_id is not None and entry.get("away_team_id") != away_team_id:
        return []
    return entry.get("matches", [])
