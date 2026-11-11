"""Evaluation metrics for completed PitchIQ 1X2 forecasts."""
import json
import math
import sys


def _diagnostic_group(rows, label):
    count = len(rows)
    hits = 0
    brier = 0.0
    home_error = away_error = 0.0
    goal_count = 0
    for item, actual, probs in rows:
        hits += probs.index(max(probs)) == actual
        brier += sum((value - (1 if index == actual else 0)) ** 2
                     for index, value in enumerate(probs))
        final = item["final"]
        prediction = item.get("p") or {}
        try:
            home_error += abs(float(prediction["lh"]) - float(final[0]))
            away_error += abs(float(prediction["la"]) - float(final[1]))
            goal_count += 1
        except (KeyError, TypeError, ValueError):
            pass
    return {
        "band": label,
        "matches": count,
        "accuracy": round(hits / count, 4) if count else None,
        "brier": round(brier / count, 4) if count else None,
        "home_goals_mae": round(home_error / goal_count, 4) if goal_count else None,
        "away_goals_mae": round(away_error / goal_count, 4) if goal_count else None,
    }


def input_diagnostics(predictions):
    """Evaluate completed forecasts against their saved pre-match input samples."""
    valid = []
    completed = 0
    for item in predictions:
        final = item.get("final")
        probs = item.get("p") or {}
        if not isinstance(final, list) or len(final) != 2:
            continue
        completed += 1
        inputs = item.get("inputs")
        if not isinstance(inputs, dict) or inputs.get("schema") != 1:
            continue
        try:
            home, away = float(final[0]), float(final[1])
            p = [float(probs[key]) for key in ("ph", "pd", "pa")]
            if (not all(math.isfinite(x) for x in [home, away] + p)
                    or min(home, away) < 0 or any(x < 0 or x > 1 for x in p)
                    or abs(sum(p) - 1.0) > 0.02):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        actual = 0 if home > away else 1 if home == away else 2
        valid.append((item, actual, p))

    dimensions = {
        "home_venue_sample": [
            ("0–2", lambda n: 0 <= n <= 2), ("3–5", lambda n: 3 <= n <= 5),
            ("6–10", lambda n: 6 <= n <= 10), ("11+", lambda n: n >= 11),
        ],
        "away_venue_sample": [
            ("0–2", lambda n: 0 <= n <= 2), ("3–5", lambda n: 3 <= n <= 5),
            ("6–10", lambda n: 6 <= n <= 10), ("11+", lambda n: n >= 11),
        ],
        "home_form_points": [
            ("0–4", lambda n: 0 <= n <= 4), ("5–9", lambda n: 5 <= n <= 9),
            ("10–12", lambda n: 10 <= n <= 12), ("13–15", lambda n: 13 <= n <= 15),
        ],
        "away_form_points": [
            ("0–4", lambda n: 0 <= n <= 4), ("5–9", lambda n: 5 <= n <= 9),
            ("10–12", lambda n: 10 <= n <= 12), ("13–15", lambda n: 13 <= n <= 15),
        ],
    }
    results = {}
    for dimension, bands in dimensions.items():
        side = "home" if dimension.startswith("home_") else "away"
        grouped = []
        for item, actual, probs in valid:
            team = item["inputs"].get(side) or {}
            if dimension.endswith("venue_sample"):
                value = team.get("venue_matches")
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            else:
                form = team.get("form")
                if not isinstance(form, str) or any(char not in "WDL" for char in form):
                    continue
                value = sum({"W": 3, "D": 1, "L": 0}[char] for char in form)
            grouped.append((value, (item, actual, probs)))
        results[dimension] = [
            _diagnostic_group([row for value, row in grouped if predicate(value)], label)
            for label, predicate in bands
        ]
    return {
        "completed_forecasts": completed,
        "snapshot_forecasts": len(valid),
        "missing_or_invalid_snapshots": completed - len(valid),
        "groups": results,
    }


def evaluate(predictions):
    """Calculate outcome accuracy, multiclass Brier/log loss and goal MAE."""
    records = []
    for item in predictions:
        final = item.get("final")
        probs = item.get("p") or {}
        if not isinstance(final, list) or len(final) != 2:
            continue
        try:
            home_goals, away_goals = float(final[0]), float(final[1])
            p = [float(probs[k]) for k in ("ph", "pd", "pa")]
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(x) for x in [home_goals, away_goals] + p):
            continue
        if min(home_goals, away_goals) < 0 or any(x < 0 or x > 1 for x in p):
            continue
        if abs(sum(p) - 1.0) > 0.02:
            continue
        actual = 0 if home_goals > away_goals else 1 if home_goals == away_goals else 2
        records.append((home_goals, away_goals, p, actual, probs, str(item.get('utc') or item.get('made') or '')))


    n = len(records)
    chronological = []
    ordered = sorted(records, key=lambda row: row[5])
    if n >= 2:
        midpoint = n // 2
        for label, subset in (("earlier", ordered[:midpoint]), ("later", ordered[midpoint:])):
            count = len(subset)
            hits = sum(row[2].index(max(row[2])) == row[3] for row in subset)
            subset_brier = sum(
                sum((value - (1 if index == row[3] else 0)) ** 2 for index, value in enumerate(row[2]))
                for row in subset
            ) / count
            subset_loss = sum(-math.log(max(row[2][row[3]], 1e-15)) for row in subset) / count
            chronological.append({
                "period": label, "matches": count,
                "accuracy": round(hits / count, 4),
                "brier": round(subset_brier, 4),
                "log_loss": round(subset_loss, 4),
            })
    if not n:
        return {"matches": 0, "accuracy": None, "brier": None, "log_loss": None,
                "chronological_split": [], "home_goals_mae": None, "away_goals_mae": None,
                "home_goals_bias": None, "away_goals_bias": None,
                "input_diagnostics": input_diagnostics(predictions)}

    correct = 0
    confidence_groups = [(lo, lo + 0.1, [], []) for lo in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)]
    brier = 0.0
    log_loss = 0.0
    home_mae = 0.0
    away_mae = 0.0
    home_bias = 0.0
    away_bias = 0.0
    goal_n = 0
    for home, away, p, actual, original, _date in records:
        hit = p.index(max(p)) == actual
        correct += hit
        confidence = max(p)
        for index, (lo, hi, confidences, outcomes) in enumerate(confidence_groups):
            # Include an exactly 100% forecast in the final 0.9–1.0 band.
            if lo <= confidence < hi or (index == len(confidence_groups) - 1 and confidence == 1.0):
                confidences.append(confidence)
                outcomes.append(float(hit))
                break
        brier += sum((value - (index == actual)) ** 2 for index, value in enumerate(p))
        log_loss -= math.log(max(p[actual], 1e-15))
        try:
            expected_home = float(original["lh"])
            expected_away = float(original["la"])
            if math.isfinite(expected_home) and math.isfinite(expected_away):
                home_mae += abs(expected_home - home)
                away_mae += abs(expected_away - away)
                home_bias += expected_home - home
                away_bias += expected_away - away
                goal_n += 1
        except (KeyError, TypeError, ValueError):
            pass

    return {
        "matches": n,
        "accuracy": round(correct / n, 4),
        "chronological_split": chronological,
        "confidence_bins": [
            {"lower": lo, "upper": hi, "matches": len(confidences),
             "mean_confidence": round(sum(confidences) / len(confidences), 4),
             "accuracy": round(sum(outcomes) / len(outcomes), 4)}
            for lo, hi, confidences, outcomes in confidence_groups if confidences
        ],
        "brier": round(brier / n, 4),
        "log_loss": round(log_loss / n, 4),
        "goal_samples": goal_n,
        "home_goals_mae": round(home_mae / goal_n, 4) if goal_n else None,
        "away_goals_mae": round(away_mae / goal_n, 4) if goal_n else None,
        "home_goals_bias": round(home_bias / goal_n, 4) if goal_n else None,
        "away_goals_bias": round(away_bias / goal_n, 4) if goal_n else None,
        "input_diagnostics": input_diagnostics(predictions),
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "predictions.json"
    with open(path, encoding="utf-8") as source:
        data = json.load(source)
    values = data.values() if isinstance(data, dict) else data
    print(json.dumps(evaluate(list(values)), indent=2))
