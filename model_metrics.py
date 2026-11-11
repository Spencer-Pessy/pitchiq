"""Evaluation metrics for completed PitchIQ 1X2 forecasts."""
import json
import math
import random
import sys

from pitchiq_model import predict as model_predict



def wilson_interval(successes, total, z=1.96):
    """Return a two-sided Wilson score interval for a binomial proportion."""
    if total <= 0 or successes < 0 or successes > total:
        return None
    proportion = successes / total
    z_squared = z * z
    denominator = 1 + z_squared / total
    center = (proportion + z_squared / (2 * total)) / denominator
    margin = z * math.sqrt(
        (proportion * (1 - proportion) + z_squared / (4 * total)) / total
    ) / denominator
    return [round(max(0.0, center - margin), 4),
            round(min(1.0, center + margin), 4)]


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
    """Evaluate completed forecasts against saved, versioned pre-match inputs."""
    valid = []
    completed = 0
    for item in predictions:
        final = item.get("final")
        probs = item.get("p") or {}
        if not isinstance(final, list) or len(final) != 2:
            continue
        completed += 1
        inputs = item.get("inputs")
        if not isinstance(inputs, dict) or inputs.get("schema") not in (1, 2):
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

    def form_points(form):
        if not isinstance(form, str) or not 1 <= len(form) <= 5:
            return None
        if any(char not in "WDL" for char in form):
            return None
        return sum({"W": 3, "D": 1, "L": 0}[char] for char in form)

    def summarize(label, rows):
        result = _diagnostic_group(rows, label)
        result["group"] = label
        result["interpretation"] = "monitoring_only" if len(rows) < 10 else "reviewable"
        return result

    bands = {
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
    groups = {}
    for dimension, dimension_bands in bands.items():
        side = "home" if dimension.startswith("home_") else "away"
        is_venue = dimension.endswith("venue_sample")
        values = []
        for item, actual, probs in valid:
            team = item["inputs"].get(side) or {}
            try:
                value = int(team["venue_matches"]) if is_venue else form_points(team.get("form"))
            except (KeyError, TypeError, ValueError):
                continue
            if value is None or (is_venue and value < 0):
                continue
            values.append((value, (item, actual, probs)))
        groups[dimension] = [
            summarize(label, [row for value, row in values if predicate(value)])
            for label, predicate in dimension_bands
        ]

    venue_rows = []
    form_rows = []
    for item, actual, probs in valid:
        home = item["inputs"].get("home") or {}
        away = item["inputs"].get("away") or {}
        try:
            home_n, away_n = int(home["venue_matches"]), int(away["venue_matches"])
            if home_n >= 0 and away_n >= 0:
                venue_rows.append((min(home_n, away_n), (item, actual, probs)))
        except (KeyError, TypeError, ValueError):
            pass
        home_form, away_form = form_points(home.get("form")), form_points(away.get("form"))
        if home_form is not None and away_form is not None:
            edge = "Home stronger" if home_form > away_form else "Away stronger" if away_form > home_form else "Even"
            form_rows.append((edge, (item, actual, probs)))

    venue_bands = [
        ("0–2", lambda n: 0 <= n <= 2),
        ("3–5", lambda n: 3 <= n <= 5),
        ("6+", lambda n: n >= 6),
    ]
    venue_support = [
        summarize(label, [row for value, row in venue_rows if predicate(value)])
        for label, predicate in venue_bands
    ]
    form_edge = [
        summarize(label, [row for edge, row in form_rows if edge == label])
        for label in ("Home stronger", "Even", "Away stronger")
    ]

    return {
        "completed_forecasts": completed,
        "snapshot_forecasts": len(valid),
        "missing_or_invalid_snapshots": completed - len(valid),
        "snapshot_matches": len(valid),
        "venue_support": venue_support,
        "form_edge": form_edge,
        "groups": groups,
    }


def outcome_class_metrics(predictions):
    """Measure one-vs-rest probability calibration for home/draw/away outcomes."""
    names = ("home", "draw", "away")
    rows = []
    for item in predictions:
        final = item.get("final")
        probs = item.get("p") or {}
        if not isinstance(final, list) or len(final) != 2:
            continue
        try:
            home, away = float(final[0]), float(final[1])
            values = [float(probs[key]) for key in ("ph", "pd", "pa")]
        except (KeyError, TypeError, ValueError):
            continue
        if (not all(math.isfinite(x) for x in [home, away] + values)
                or min(home, away) < 0 or any(x < 0 or x > 1 for x in values)
                or abs(sum(values) - 1.0) > 0.02):
            continue
        actual = 0 if home > away else 1 if home == away else 2
        rows.append((values, actual))

    result = {}
    for index, name in enumerate(names):
        samples = [(values[index], float(actual == index)) for values, actual in rows]
        count = len(samples)
        if not count:
            result[name] = {"matches": 0, "mean_probability": None,
                            "observed_rate": None, "brier": None,
                            "log_loss": None, "expected_calibration_error": None}
            continue
        brier = sum((probability - actual) ** 2 for probability, actual in samples) / count
        loss = sum(
            -math.log(max(probability, 1e-15)) if actual
            else -math.log(max(1 - probability, 1e-15))
            for probability, actual in samples
        ) / count
        bins = []
        for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
            upper = lower + 0.2
            subset = [(p, y) for p, y in samples
                      if lower <= p < upper or (upper == 1.0 and p == 1.0)]
            if subset:
                bins.append((len(subset),
                             sum(p for p, _ in subset) / len(subset),
                             sum(y for _, y in subset) / len(subset)))
        ece = sum(n * abs(mean_p - observed) for n, mean_p, observed in bins) / count
        result[name] = {
            "matches": count,
            "mean_probability": round(sum(p for p, _ in samples) / count, 4),
            "observed_rate": round(sum(y for _, y in samples) / count, 4),
            "brier": round(brier, 4),
            "log_loss": round(loss, 4),
            "expected_calibration_error": round(ece, 4),
        }
    return result



def paired_bootstrap_interval(differences, iterations=1000, seed=20261111):
    """Return a deterministic percentile 95% CI for a paired mean difference."""
    values = [float(value) for value in differences]
    if len(values) < 2 or not all(math.isfinite(value) for value in values):
        return None
    # Canonical ordering makes seeded intervals invariant to input row order.
    values.sort()
    rng = random.Random(seed)
    size = len(values)
    means = []
    for _ in range(iterations):
        means.append(sum(values[rng.randrange(size)] for _ in range(size)) / size)
    means.sort()
    lower = means[max(0, int(0.025 * iterations))]
    upper = means[min(iterations - 1, int(0.975 * iterations))]
    return [round(lower, 4), round(upper, 4)]


def ablation_comparison(predictions):
    """Replay versioned forecasts while disabling Elo and/or recent form."""
    variants = {
        "full_model": {"use_elo": True, "use_form": True},
        "without_elo": {"use_elo": False, "use_form": True},
        "without_form": {"use_elo": True, "use_form": False},
        "without_elo_or_form": {"use_elo": False, "use_form": False},
    }
    scored = {name: [] for name in variants}
    paired_deltas = {name: [] for name in variants if name != "full_model"}
    for item in predictions:
        final = item.get("final")
        snapshot = item.get("inputs")
        if (not isinstance(final, list) or len(final) != 2
                or not isinstance(snapshot, dict) or snapshot.get("schema") != 2):
            continue
        try:
            home_goals, away_goals = float(final[0]), float(final[1])
            stats = {
                "h": snapshot["home"], "a": snapshot["away"],
                "lh": float(snapshot["league_home"]),
                "la": float(snapshot["league_away"]),
            }
            calibration = snapshot["calibration"]
            actual = 0 if home_goals > away_goals else 1 if home_goals == away_goals else 2
            if (not all(math.isfinite(x) for x in (home_goals, away_goals, stats["lh"], stats["la"]))
                    or min(home_goals, away_goals) < 0):
                continue
            forecasts = {}
            for name, switches in variants.items():
                forecast = model_predict(stats, calibration, **switches)
                probabilities = [forecast[key] for key in ("ph", "pd", "pa")]
                if all(math.isfinite(value) for value in probabilities):
                    forecasts[name] = probabilities
                    scored[name].append((probabilities, actual))
            if "full_model" in forecasts:
                target = [1 if index == actual else 0 for index in range(3)]
                full_brier = sum((value - target[index]) ** 2
                                 for index, value in enumerate(forecasts["full_model"]))
                for name in paired_deltas:
                    if name in forecasts:
                        variant_brier = sum((value - target[index]) ** 2
                                            for index, value in enumerate(forecasts[name]))
                        paired_deltas[name].append(variant_brier - full_brier)
        except (KeyError, TypeError, ValueError):
            continue

    results = {name: _probability_scores(rows) for name, rows in scored.items()}
    full_brier = results["full_model"]["brier"]
    for name, row in results.items():
        row["brier_delta_vs_full"] = (
            round(row["brier"] - full_brier, 4)
            if row["brier"] is not None and full_brier is not None else None
        )
        row["brier_delta_ci_95"] = (
            paired_bootstrap_interval(paired_deltas[name])
            if name in paired_deltas else None
        )
    return {
        "matches": results["full_model"]["matches"],
        "variants": results,
        "note": "Controlled replay on schema-2 snapshots only; all variants use identical matches and the original saved calibration.",
    }


def binary_market_metrics(predictions, key):
    """Score a saved binary market probability against its completed outcome."""
    rows = []
    for item in predictions:
        final = item.get("final")
        value = (item.get("p") or {}).get(key)
        if not isinstance(final, list) or len(final) != 2:
            continue
        try:
            home, away, probability = float(final[0]), float(final[1]), float(value)
        except (TypeError, ValueError):
            continue
        if (not all(math.isfinite(x) for x in (home, away, probability))
                or min(home, away) < 0 or not 0 <= probability <= 1):
            continue
        actual = float(home + away > 2) if key == "o25" else float(home > 0 and away > 0)
        rows.append((probability, actual))

    count = len(rows)
    if not count:
        return {"matches": 0, "accuracy": None, "brier": None, "log_loss": None,
                "expected_calibration_error": None, "bins": []}

    bins = []
    for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
        upper = lower + 0.2
        subset = [(p, y) for p, y in rows if lower <= p < upper or (upper == 1.0 and p == 1.0)]
        if not subset:
            continue
        mean_probability = sum(p for p, _ in subset) / len(subset)
        observed_rate = sum(y for _, y in subset) / len(subset)
        bins.append({"lower": lower, "upper": upper, "matches": len(subset),
                     "mean_probability": round(mean_probability, 4),
                     "observed_rate": round(observed_rate, 4)})

    ece = sum(row["matches"] * abs(row["mean_probability"] - row["observed_rate"])
              for row in bins) / count
    brier = sum((p - y) ** 2 for p, y in rows) / count
    loss = sum(-math.log(max(p, 1e-15)) if y else -math.log(max(1 - p, 1e-15))
               for p, y in rows) / count
    hits = sum((p >= 0.5) == bool(y) for p, y in rows)
    return {"matches": count, "accuracy": round(hits / count, 4),
            "brier": round(brier, 4), "log_loss": round(loss, 4),
            "expected_calibration_error": round(ece, 4), "bins": bins}


def _probability_scores(rows):
    """Summarize (probabilities, actual outcome) rows on a common sample."""
    count = len(rows)
    if not count:
        return {"matches": 0, "accuracy": None, "brier": None, "log_loss": None}
    hits = brier = loss = 0.0
    for probabilities, actual in rows:
        hits += probabilities.index(max(probabilities)) == actual
        brier += sum((value - (index == actual)) ** 2
                     for index, value in enumerate(probabilities))
        loss -= math.log(max(probabilities[actual], 1e-15))
    return {"matches": count, "accuracy": round(hits / count, 4),
            "brier": round(brier / count, 4), "log_loss": round(loss / count, 4)}


def baseline_comparison(predictions):
    """Compare forecasts with a no-look-ahead rolling prior and de-vigged odds."""
    records = []
    for item in predictions:
        final = item.get("final")
        probs = item.get("p") or {}
        if not isinstance(final, list) or len(final) != 2:
            continue
        try:
            home, away = float(final[0]), float(final[1])
            model = [float(probs[key]) for key in ("ph", "pd", "pa")]
        except (KeyError, TypeError, ValueError):
            continue
        if (not all(math.isfinite(x) for x in [home, away] + model)
                or min(home, away) < 0 or any(x < 0 or x > 1 for x in model)
                or abs(sum(model) - 1.0) > 0.02):
            continue
        actual = 0 if home > away else 1 if home == away else 2
        date = str(item.get("utc") or item.get("made") or "")
        market = None
        odds = item.get("odds")
        if isinstance(odds, list) and len(odds) == 3:
            try:
                prices = [float(value) for value in odds]
                if all(math.isfinite(value) and value > 1.0 for value in prices):
                    implied = [1.0 / value for value in prices]
                    total = sum(implied)
                    if total > 0:
                        market = [value / total for value in implied]
            except (TypeError, ValueError):
                pass
        records.append({"date": date, "actual": actual, "model": model, "market": market,
                        "competition": item.get("code") or item.get("comp") or "Other"})

    records.sort(key=lambda row: row["date"])
    counts = [1, 1, 1]
    prior_rows, competition_prior_rows, model_market_rows, market_rows = [], [], [], []
    model_market_brier_deltas, model_market_log_deltas = [], []
    model_prior_brier_deltas, model_prior_log_deltas = [], []
    competition_counts = {}
    index = 0
    while index < len(records):
        # Matches sharing a kickoff timestamp all receive the same prior;
        # none can learn from another result at that same kickoff.
        end = index + 1
        while end < len(records) and records[end]["date"] == records[index]["date"]:
            end += 1
        total = sum(counts)
        prior = [value / total for value in counts]
        for row in records[index:end]:
            prior_rows.append((prior, row["actual"]))
            code = str(row.get("competition") or "Other")
            comp_counts = competition_counts.get(code, [0, 0, 0])
            comp_total = sum(comp_counts)
            shrink = 5.0
            competition_prior = [
                (comp_counts[outcome] + shrink * prior[outcome]) / (comp_total + shrink)
                for outcome in range(3)
            ]
            competition_prior_rows.append((competition_prior, row["actual"]))
            target = [1 if outcome == row["actual"] else 0 for outcome in range(3)]
            model_brier = sum((value - target[i]) ** 2 for i, value in enumerate(row["model"]))
            prior_brier = sum((value - target[i]) ** 2 for i, value in enumerate(competition_prior))
            model_loss = -math.log(max(row["model"][row["actual"]], 1e-15))
            prior_loss = -math.log(max(competition_prior[row["actual"]], 1e-15))
            model_prior_brier_deltas.append(model_brier - prior_brier)
            model_prior_log_deltas.append(model_loss - prior_loss)
            if row["market"] is not None:
                model_market_rows.append((row["model"], row["actual"]))
                market_rows.append((row["market"], row["actual"]))
                market_brier = sum((value - target[i]) ** 2 for i, value in enumerate(row["market"]))
                market_loss = -math.log(max(row["market"][row["actual"]], 1e-15))
                model_market_brier_deltas.append(model_brier - market_brier)
                model_market_log_deltas.append(model_loss - market_loss)
        for row in records[index:end]:
            counts[row["actual"]] += 1
            code = str(row.get("competition") or "Other")
            competition_counts.setdefault(code, [0, 0, 0])[row["actual"]] += 1
        index = end

    prior_scores = _probability_scores(prior_rows)
    competition_prior_scores = _probability_scores(competition_prior_rows)
    market_scores = _probability_scores(market_rows)
    model_market_scores = _probability_scores(model_market_rows)
    return {
        "rolling_prior": prior_scores,
        "competition_rolling_prior": competition_prior_scores,
        "model_on_odds_sample": model_market_scores,
        "bookmaker_consensus": market_scores,
        "model_minus_bookmaker_brier": (
            round(model_market_scores["brier"] - market_scores["brier"], 4)
            if model_market_scores["brier"] is not None and market_scores["brier"] is not None else None
        ),
        "model_minus_bookmaker_log_loss": (
            round(model_market_scores["log_loss"] - market_scores["log_loss"], 4)
            if model_market_scores["log_loss"] is not None and market_scores["log_loss"] is not None else None
        ),
        "model_minus_bookmaker_brier_ci_95": paired_bootstrap_interval(model_market_brier_deltas),
        "model_minus_bookmaker_log_loss_ci_95": paired_bootstrap_interval(model_market_log_deltas),
        "model_minus_competition_prior_brier": (
            round(sum(model_prior_brier_deltas) / len(model_prior_brier_deltas), 4)
            if model_prior_brier_deltas else None
        ),
        "model_minus_competition_prior_brier_ci_95": paired_bootstrap_interval(model_prior_brier_deltas),
    }



def expected_goals_calibration(predictions):
    """Group saved expected-goal forecasts by predicted-goal band, per team."""
    edges = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, float("inf"))
    labels = ("0–0.49", "0.50–0.99", "1.00–1.49", "1.50–1.99",
              "2.00–2.49", "2.50–2.99", "3.00+")
    result = {}
    for side, key, score_index in (("home", "lh", 0), ("away", "la", 1)):
        groups = [[] for _ in labels]
        for item in predictions:
            final = item.get("final")
            probs = item.get("p") or {}
            if not isinstance(final, list) or len(final) != 2:
                continue
            try:
                predicted = float(probs[key])
                actual = float(final[score_index])
            except (KeyError, TypeError, ValueError):
                continue
            if (not math.isfinite(predicted) or not math.isfinite(actual)
                    or predicted < 0 or actual < 0):
                continue
            if predicted > 10 or actual > 30:
                continue
            for index, (lower, upper) in enumerate(zip(edges, edges[1:])):
                if lower <= predicted < upper:
                    groups[index].append((predicted, actual))
                    break
        result[side] = [
            {
                "band": label,
                "matches": len(rows),
                "mean_predicted": round(sum(x[0] for x in rows) / len(rows), 4) if rows else None,
                "mean_actual": round(sum(x[1] for x in rows) / len(rows), 4) if rows else None,
                "bias": round(sum(x[0] - x[1] for x in rows) / len(rows), 4) if rows else None,
                "mae": round(sum(abs(x[0] - x[1]) for x in rows) / len(rows), 4) if rows else None,
                "interpretation": "monitoring_only" if len(rows) < 10 else "reviewable",
            }
            for label, rows in zip(labels, groups)
        ]
    return result

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
        return {"matches": 0, "accuracy": None, "accuracy_ci_95": None, "brier": None, "log_loss": None,
                "chronological_split": [], "confidence_bins": [], "expected_calibration_error": None,
                "max_calibration_gap": None, "home_goals_mae": None, "away_goals_mae": None,
                "home_goals_bias": None, "away_goals_bias": None,\n                "expected_goals_calibration": expected_goals_calibration(predictions),
                "input_diagnostics": input_diagnostics(predictions),
                "binary_markets": {"o25": binary_market_metrics(predictions, "o25"),
                                   "btts": binary_market_metrics(predictions, "bt")},
                "outcome_classes": outcome_class_metrics(predictions),
                "baseline_comparison": baseline_comparison(predictions),
                "ablation_comparison": ablation_comparison(predictions)}

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

    populated_bins = [
        {"lower": lo, "upper": hi, "matches": len(confidences),
         "mean_confidence": round(sum(confidences) / len(confidences), 4),
         "accuracy": round(sum(outcomes) / len(outcomes), 4)}
        for lo, hi, confidences, outcomes in confidence_groups if confidences
    ]
    calibration_gaps = [abs(row["mean_confidence"] - row["accuracy"]) for row in populated_bins]
    calibration_error = sum(row["matches"] * gap for row, gap in zip(populated_bins, calibration_gaps)) / n
    return {
        "matches": n,
        "accuracy": round(correct / n, 4),
        "accuracy_ci_95": wilson_interval(correct, n),
        "chronological_split": chronological,
        "confidence_bins": populated_bins,
        "expected_calibration_error": round(calibration_error, 4),
        "max_calibration_gap": round(max(calibration_gaps), 4) if calibration_gaps else None,
        "brier": round(brier / n, 4),
        "log_loss": round(log_loss / n, 4),
        "goal_samples": goal_n,
        "home_goals_mae": round(home_mae / goal_n, 4) if goal_n else None,
        "away_goals_mae": round(away_mae / goal_n, 4) if goal_n else None,
        "home_goals_bias": round(home_bias / goal_n, 4) if goal_n else None,\n        "expected_goals_calibration": expected_goals_calibration(predictions),
        "away_goals_bias": round(away_bias / goal_n, 4) if goal_n else None,
        "input_diagnostics": input_diagnostics(predictions),
        "binary_markets": {"o25": binary_market_metrics(predictions, "o25"),
                           "btts": binary_market_metrics(predictions, "bt")},
        "outcome_classes": outcome_class_metrics(predictions),
        "baseline_comparison": baseline_comparison(predictions),
        "ablation_comparison": ablation_comparison(predictions),
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "predictions.json"
    with open(path, encoding="utf-8") as source:
        data = json.load(source)
    values = data.values() if isinstance(data, dict) else data
    print(json.dumps({**evaluate(list(values)), "input_diagnostics": input_diagnostics(list(values))}, indent=2))
