"""Evaluation metrics for completed PitchIQ 1X2 forecasts."""
import json
import math
import sys


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
        records.append((home_goals, away_goals, p, actual, probs))

    n = len(records)
    if not n:
        return {"matches": 0, "accuracy": None, "brier": None, "log_loss": None,
                "home_goals_mae": None, "away_goals_mae": None}

    correct = 0
    confidence_groups = [(lo, lo + 0.1, [], []) for lo in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)]
    brier = 0.0
    log_loss = 0.0
    home_mae = 0.0
    away_mae = 0.0
    goal_n = 0
    for home, away, p, actual, original in records:
        hit = p.index(max(p)) == actual
        correct += hit
        confidence = max(p)
        for lo, hi, confidences, outcomes in confidence_groups:
            if lo <= confidence < hi or (hi > 1 and confidence <= 1):
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
                goal_n += 1
        except (KeyError, TypeError, ValueError):
            pass

    return {
        "matches": n,
        "accuracy": round(correct / n, 4),
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
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "predictions.json"
    with open(path, encoding="utf-8") as source:
        data = json.load(source)
    values = data.values() if isinstance(data, dict) else data
    print(json.dumps(evaluate(list(values)), indent=2))
