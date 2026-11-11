"""Strict validation and normalisation for bookmaker odds responses."""
from datetime import datetime
import math


def active_sport_keys(payload):
    """Return active sport keys, rejecting malformed discovery responses."""
    if not isinstance(payload, list):
        raise ValueError("sports response must be a list")
    keys = set()
    for index, sport in enumerate(payload):
        if not isinstance(sport, dict):
            raise ValueError(f"sports[{index}] must be an object")
        key = sport.get("key")
        active = sport.get("active")
        if not isinstance(key, str) or not key.strip() or not isinstance(active, bool):
            raise ValueError(f"sports[{index}] has invalid key/active fields")
        if active:
            keys.add(key)
    return keys


def _valid_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def market_events(payload):
    """Convert a valid odds endpoint response into three-way decimal prices.

    A malformed response raises ValueError so callers can preserve the last
    known-good snapshot instead of publishing a partial or misleading feed.
    """
    if not isinstance(payload, list):
        raise ValueError("odds response must be a list")
    events = []
    for index, event in enumerate(payload):
        if not isinstance(event, dict):
            raise ValueError(f"odds event {index} must be an object")
        home, away, commence = (
            event.get("home_team"), event.get("away_team"), event.get("commence_time")
        )
        if (not isinstance(home, str) or not home.strip()
                or not isinstance(away, str) or not away.strip()
                or home == away or not _valid_timestamp(commence)):
            raise ValueError(f"odds event {index} has invalid teams or kickoff")
        bookmakers = event.get("bookmakers", [])
        if not isinstance(bookmakers, list):
            raise ValueError(f"odds event {index} bookmakers must be a list")
        prices = {}
        for bookmaker_index, bookmaker in enumerate(bookmakers):
            if not isinstance(bookmaker, dict):
                raise ValueError(f"odds event {index} bookmaker {bookmaker_index} must be an object")
            markets = bookmaker.get("markets", [])
            if not isinstance(markets, list):
                raise ValueError(f"odds event {index} markets must be a list")
            for market in markets:
                if not isinstance(market, dict):
                    raise ValueError(f"odds event {index} market must be an object")
                if market.get("key") != "h2h":
                    continue
                outcomes = market.get("outcomes")
                if not isinstance(outcomes, list):
                    raise ValueError(f"odds event {index} h2h outcomes must be a list")
                for outcome in outcomes:
                    if not isinstance(outcome, dict):
                        raise ValueError(f"odds event {index} outcome must be an object")
                    name, price = outcome.get("name"), outcome.get("price")
                    if not isinstance(name, str) or not name.strip():
                        raise ValueError(f"odds event {index} outcome has invalid name")
                    if (isinstance(price, bool) or not isinstance(price, (int, float))
                            or not math.isfinite(price) or price <= 1 or price >= 1000):
                        raise ValueError(f"odds event {index} outcome has invalid decimal price")
                    prices.setdefault(name, []).append(float(price))
        home_prices = prices.get(home, [])
        away_prices = prices.get(away, [])
        draw_prices = prices.get("Draw", [])
        if home_prices and away_prices and draw_prices:
            events.append({
                "home": home,
                "away": away,
                "commence": commence,
                "odds": [
                    round(sum(home_prices) / len(home_prices), 2),
                    round(sum(draw_prices) / len(draw_prices), 2),
                    round(sum(away_prices) / len(away_prices), 2),
                ],
            })
    return events


def require_nonempty_snapshot(active_keys, wanted_keys, events):
    """Reject empty refreshes so the publisher keeps its last good snapshot."""
    active_wanted = set(active_keys).intersection(wanted_keys)
    if not active_wanted:
        raise ValueError("no requested competitions are currently active")
    if not isinstance(events, list) or not events:
        raise ValueError("no complete three-way odds events were returned")
    return events
