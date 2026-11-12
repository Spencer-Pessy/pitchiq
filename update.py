import difflib, json, math, os, re, time, unicodedata, urllib.request, urllib.error
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pitchiq_model import predict as model_predict
from model_metrics import ablation_comparison, scoreline_baseline_comparison
from pitchiq_data import INTERNATIONAL_COMPETITIONS, is_club_competition, average_bucket, build_feed_health, goal_average_keys, player_rate_stats, team_venue_stats, forecast_input_snapshot, record_forward_evaluations, backfill_market_odds, goal_rate_calibration, clean_prediction_ledger, same_team_name, build_head_to_head

KEY = os.environ["FOOTBALL_DATA_KEY"]
COMPS = ["PL", "PD", "SA", "BL1", "FL1", "CL", "WC", "EC"]
BASE = "https://api.football-data.org/v4"


# Football-Data.org's free tier is limited to 10 requests per minute.
# Pace every network attempt centrally so standings, scorers, and retries
# cannot accidentally bypass the limit.
REQUEST_INTERVAL_SECONDS = 7.0
_last_api_request_at = None


def _pace_api_request():
    global _last_api_request_at
    if _last_api_request_at is not None:
        elapsed = time.monotonic() - _last_api_request_at
        remaining = REQUEST_INTERVAL_SECONDS - elapsed
        if remaining > 0:
            time.sleep(remaining)
    _last_api_request_at = time.monotonic()


def get(path):
    req = urllib.request.Request(BASE + path, headers={"X-Auth-Token": KEY})
    for _ in range(3):
        # This runs before every attempt, including retries after transient errors.
        _pace_api_request()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(65)
                continue
            print("error", path, e.code)
            return None
        except Exception as e:
            print("error", path, e)
            time.sleep(5)
    return None


matches = []
fixture_counts = {}
for i, c in enumerate(COMPS):
    d = get(f"/competitions/{c}/matches")
    # Never publish a partial/empty fixture feed when an API request failed.
    # A genuine empty list is valid; None means the request did not succeed.
    if d is None or not isinstance(d.get("matches"), list):
        raise SystemExit(
            f"Aborting update: fixture request failed for {c}. "
            "The previous data.json will be kept."
        )
    fixture_counts[c] = len(d.get("matches", []))
    for m in d.get("matches", []):
        m["_c"] = c
        m["_cn"] = d["competition"]["name"]
        matches.append(m)

def tname(t):
    return t.get("shortName") or t.get("name") or "?"


def goals(m):
    ft = m["score"]["fullTime"]
    return ft["home"], ft["away"]


# League tables
tables = {}
standings_failed = []
for c in COMPS:
    d = get(f"/competitions/{c}/standings")
    if not d or not isinstance(d.get("standings"), list):
        standings_failed.append(c)
        continue
    for st in d.get("standings", []):
        if st.get("type") == "TOTAL":
            tables[c] = {"name": d["competition"]["name"], "rows": [
                {"pos": r["position"], "team": tname(r["team"]), "p": r["playedGames"],
                 "w": r["won"], "d": r["draw"], "l": r["lost"], "gf": r["goalsFor"],
                 "ga": r["goalsAgainst"], "gd": r["goalDifference"], "pts": r["points"]}
                for r in st["table"]]}
            break
    sc = get(f"/competitions/{c}/scorers?limit=10")
    if sc and c in tables:
        tables[c]["scorers"] = [
            {"name": x["player"]["name"], "team": tname(x["team"]), "g": x.get("goals"),
             "a": x.get("assists"), "pen": x.get("penalties"), "m": x.get("playedMatches"),
             **player_rate_stats(x.get("goals"), x.get("assists"), x.get("playedMatches"))}
            for x in sc.get("scorers", [])]


fin = sorted(
    [m for m in matches if m["status"] == "FINISHED" and goals(m)[0] is not None],
    key=lambda m: m["utcDate"],
)

# league averages
tot = defaultdict(lambda: [0, 0, 0])
for m in fin:
    hg, ag = goals(m)
    for k in goal_average_keys(m["_c"]):
        tot[k][0] += hg
        tot[k][1] += ag
        tot[k][2] += 1


def avgs(c):
    k = average_bucket(c, {key: value[2] for key, value in tot.items()})
    n = tot[k][2]
    if n < 20:
        return 1.5, 1.2
    return tot[k][0] / n, tot[k][1] / n


# Elo and per-team history, built across all competitions in date order
elo = defaultdict(lambda: 1500.0)
hist = defaultdict(list)  # team id -> (was_home, goals_for, goals_against, result)
for m in fin:
    h, a = m["homeTeam"]["id"], m["awayTeam"]["id"]
    hg, ag = goals(m)
    res = 1 if hg > ag else 0.5 if hg == ag else 0
    exp = 1 / (1 + 10 ** ((elo[a] - (elo[h] + 60)) / 400))
    delta = 20 * (res - exp)
    elo[h] += delta
    elo[a] -= delta
    hist[h].append((True, hg, ag, "W" if res == 1 else "D" if res == 0.5 else "L"))
    hist[a].append((False, ag, hg, "L" if res == 1 else "D" if res == 0.5 else "W"))

K = 6  # shrink small samples toward the league average


def team_stats(tid, home, prior_for, prior_against):
    return team_venue_stats(hist[tid], home, prior_for, prior_against, elo[tid], shrink=K, form_limit=5)


now = datetime.now(timezone.utc)
out = []
for m in matches:
    # Keep World Cup/EURO source coverage and isolated history, but never
    # publish national-team fixtures through the club forecast feed.
    if not is_club_competition(m.get("_c")):
        continue
    when = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
    if m["status"] == "FINISHED":
        if when < now - timedelta(hours=48):
            continue
    elif when > now + timedelta(days=30) or when < now - timedelta(hours=6):
        continue
    ah, aa = avgs(m["_c"])
    h, a = m["homeTeam"], m["awayTeam"]
    hg, ag = goals(m)
    out.append({
        "id": m["id"], "comp": m["_cn"], "code": m["_c"], "utc": m["utcDate"],
        "status": m["status"], "h": tname(h), "a": tname(a),
        "score": [hg, ag] if hg is not None else None,
        "h2h": build_head_to_head(matches, h.get("id"), a.get("id"), m["utcDate"]),
        "s": {
            "h": team_stats(h["id"], True, ah, aa),
            "a": team_stats(a["id"], False, aa, ah),
            "lh": round(ah, 2), "la": round(aa, 2),
        },
    })

out.sort(key=lambda x: x["utc"])

# Odds matching uses conservative normalized exact names. Ambiguous aliases are skipped.

same = same_team_name


try:
    with open("odds.json") as f:
        odds_data = json.load(f)
except Exception:
    odds_data = {"updated": None, "events": []}

mid = {m["id"]: m for m in matches}
for x in out:
    if x["status"] not in ("SCHEDULED", "TIMED"):
        continue
    m = mid[x["id"]]
    when = datetime.fromisoformat(x["utc"].replace("Z", "+00:00"))
    hn = [m["homeTeam"].get("name"), tname(m["homeTeam"])]
    an = [m["awayTeam"].get("name"), tname(m["awayTeam"])]
    for ev in odds_data["events"]:
        t = datetime.fromisoformat(ev["commence"].replace("Z", "+00:00"))
        if abs((t - when).total_seconds()) > 6 * 3600:
            continue
        if any(same(ev["home"], n) for n in hn) and any(same(ev["away"], n) for n in an):
            x["odds"] = ev["odds"]
            break

# Self-calibration: compare past raw goal forecasts with real scores, adjust gently
try:
    with open("predictions.json") as f:
        _prediction_data = json.load(f)
    _pp = [p for p in _prediction_data.values() if isinstance(p, dict) and is_club_competition(p.get("code"))] if isinstance(_prediction_data, dict) else []
except Exception:
    _pp = []
CAL, _calibration_count = goal_rate_calibration(_pp)

print("calibration:", CAL, "from", _calibration_count, "valid results")


def predict(s):
    return model_predict(s, CAL)

# Results tracker: save each prediction before kickoff, score it after full time
try:
    with open("predictions.json") as f:
        preds = clean_prediction_ledger(json.load(f))
except Exception:
    preds = {}

# Attach the first available market snapshot to older upcoming forecasts.
# This never changes their saved probabilities, inputs, or original forecast time.
odds_backfilled = backfill_market_odds(
    preds, odds_data.get("events", []), odds_data.get("updated"), now, same
)
print("existing forecasts with first odds snapshot:", odds_backfilled)

for x in out:
    start = datetime.fromisoformat(x["utc"].replace("Z", "+00:00"))
    key = str(x["id"])
    if x["status"] in ("SCHEDULED", "TIMED") and start > now and key not in preds:
        # Freeze the first pre-kickoff forecast. Later refreshes must not rewrite
        # the probability snapshot or its timestamp in the public results ledger.
        preds[key] = {
            "id": x["id"], "comp": x["comp"], "code": x["code"], "utc": x["utc"],
            "h": x["h"], "a": x["a"], "p": predict(x["s"]), "odds": x.get("odds"),
            "odds_updated": odds_data.get("updated") if x.get("odds") is not None else None,
            "inputs": forecast_input_snapshot(x["s"], CAL),
            "final": None, "made": now.isoformat(),
        }

byid = {m["id"]: m for m in fin}
for p in preds.values():
    if p.get("final") is None and p.get("id") in byid:
        hg, ag = goals(byid[p["id"]])
        p["final"] = [hg, ag]

with open("predictions.json", "w") as f:
    json.dump(preds, f, ensure_ascii=False)
print("predictions stored:", len(preds))

# Maintain a separate forward-only research ledger. Existing public forecasts
# remain immutable; this ledger captures current inputs for already-listed fixtures.
try:
    with open("model_evaluation.json") as f:
        evaluation = clean_prediction_ledger(json.load(f))
except Exception:
    evaluation = {}
finished_scores = {str(match_id): goals(match) for match_id, match in byid.items()}
evaluation = record_forward_evaluations(
    evaluation, out, finished_scores, now, predict,
    lambda stats: forecast_input_snapshot(stats, CAL),
)
with open("model_evaluation.json", "w") as f:
    json.dump(evaluation, f, ensure_ascii=False)
evaluation_rows = list(evaluation.values())
evaluation_completed = sum(isinstance(row.get("final"), list) for row in evaluation_rows)
print("forward evaluation forecasts:", len(evaluation_rows), "completed:", evaluation_completed)

# Publish controlled ablation scores from the separate forward-only ledger.
# Scoreline baseline diagnostics use the immutable public pre-kickoff ledger.
with open("data.json", "w") as f:
    json.dump({
        "updated": now.isoformat(), "odds_updated": odds_data["updated"],
        "calib": CAL,
        "data_health": build_feed_health(fixture_counts, tables.keys(), len(out), standings_failed),
        "matches": out, "tables": tables,
        "model_evaluation": {
            "forecasts": len(evaluation_rows), "completed": evaluation_completed,
        },
        "ablation": ablation_comparison(evaluation_rows),
        "scoreline_baseline": scoreline_baseline_comparison(list(preds.values())),
    }, f, ensure_ascii=False)
print("matches written:", len(out))
