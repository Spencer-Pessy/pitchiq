"""Pure PitchIQ forecasting functions.

No network, filesystem, or environment access: safe to import in automated tests.
"""
import math


def ppg(form):
    """Points per game from the last five W/D/L results."""
    form = (form or "")[-5:]
    if not form:
        return 1.5
    return sum(3 if c == "W" else 1 if c == "D" else 0 for c in form) / len(form)


def pois(rate, goals):
    """Poisson probability of scoring exactly 'goals' at the given rate."""
    return math.exp(-rate) * rate ** goals / math.factorial(goals)


def tau(home_goals, away_goals, home_rate, away_rate, rho):
    """Dixon-Coles low-score adjustment."""
    if home_goals == 0 and away_goals == 0:
        return 1 - home_rate * away_rate * rho
    if home_goals == 0 and away_goals == 1:
        return 1 + home_rate * rho
    if home_goals == 1 and away_goals == 0:
        return 1 + away_rate * rho
    if home_goals == 1 and away_goals == 1:
        return 1 - rho
    return 1


def predict(stats, calibration=None, use_elo=True, use_form=True):
    """Return probabilities; optional ablations disable Elo and/or recent form."""
    calibration = calibration or {"kh": 1.0, "ka": 1.0}
    home, away = stats["h"], stats["a"]
    league_home = max(stats["lh"], 0.3)
    league_away = max(stats["la"], 0.3)

    home_rate = home["gf"] * away["ga"] / league_home
    away_rate = away["gf"] * home["ga"] / league_away
    elo_difference = (home["elo"] - away["elo"]) / 400 if use_elo else 0.0

    home_form = ppg(home["form"]) if use_form else 1.5
    away_form = ppg(away["form"]) if use_form else 1.5
    home_absences = float(home.get("out", 0) or 0)
    away_absences = float(away.get("out", 0) or 0)
    home_rate *= 1.15 ** elo_difference * (1 + (home_form - 1.5) * 0.04) * (1 - 0.04 * home_absences)
    away_rate *= 1.15 ** -elo_difference * (1 + (away_form - 1.5) * 0.04) * (1 - 0.04 * away_absences)
    home_rate, away_rate = max(home_rate, 0.05), max(away_rate, 0.05)

    raw_home_rate, raw_away_rate = home_rate, away_rate
    home_rate *= calibration["kh"]
    away_rate *= calibration["ka"]

    grid_size = 8
    matrix, total = {}, 0.0
    for home_goals in range(grid_size):
        for away_goals in range(grid_size):
            probability = (
                pois(home_rate, home_goals)
                * pois(away_rate, away_goals)
                * tau(home_goals, away_goals, home_rate, away_rate, -0.1)
            )
            matrix[home_goals, away_goals] = probability
            total += probability

    result = {"ph": 0.0, "pd": 0.0, "pa": 0.0, "o25": 0.0, "bt": 0.0}
    for (home_goals, away_goals), probability in matrix.items():
        probability /= total
        if home_goals > away_goals:
            result["ph"] += probability
        elif home_goals == away_goals:
            result["pd"] += probability
        else:
            result["pa"] += probability
        if home_goals + away_goals > 2:
            result["o25"] += probability
        if home_goals > 0 and away_goals > 0:
            result["bt"] += probability

    result["lh"], result["la"] = home_rate, away_rate
    result["rlh"], result["rla"] = raw_home_rate, raw_away_rate
    return {key: round(value, 4) for key, value in result.items()}
