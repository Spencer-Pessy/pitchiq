import difflib, json, math, os, re, time, unicodedata, urllib.request, urllib.error
from collections import defaultdict
from datetime import datetime, timezone, timedelta

KEY = os.environ["FOOTBALL_DATA_KEY"]
COMPS = ["PL", "PD", "SA", "BL1", "FL1", "CL"]
BASE = "https://api.football-data.org/v4"


def get(path):
    req = urllib.request.Request(BASE + path, headers={"X-Auth-Token": KEY})
    for _ in range(3):
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
for i, c in enumerate(COMPS):
    d = get(f"/competitions/{c}/matches")
    if d:
        for m in d.get("matches", []):
            m["_c"] = c
            m["_cn"] = d["competition"]["name"]
            matches.append(m)
    if i < len(COMPS) - 1:
        time.sleep(7)  # free plan allows 10 calls per minute


def tname(t):
    return t.get("shortName") or t.get("name") or "?"


def goals(m):
    ft = m["score"]["fullTime"]
    return ft["home"], ft["away"]


# League tables
tables = {}
for c in COMPS:
    time.sleep(7)
    d = get(f"/competitions/{c}/standings")
    if not d:
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
             "a": x.get("assists"), "pen": x.get("penalties"), "m": x.get("playedMatches")}
            for x in sc.get("scorers", [])]
    time.sleep(7)


fin = sorted(
    [m for m in matches if m["status"] == "FINISHED" and goals(m)[0] is not None],
    key=lambda m: m["utcDate"],
)

# league averages
tot = defaultdict(lambda: [0, 0, 0])
for m in fin:
    hg, ag = goals(m)
    for k in (m["_c"], "ALL"):
        tot[k][0] += hg
        tot[k][1] += ag
        tot[k][2] += 1


def avgs(c):
    k = "ALL" if c == "CL" or tot[c][2] < 20 else c
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
    rows = [r for r in hist[tid] if r[0] == home]
    n = len(rows)
    gf = (sum(r[1] for r in rows) + K * prior_for) / (n + K)
    ga = (sum(r[2] for r in rows) + K * prior_against) / (n + K)
    form = "".join(r[3] for r in hist[tid][-5:])
    return {"gf": round(gf, 2), "ga": round(ga, 2), "elo": int(elo[tid]), "form": form, "out": 0}


def ppg(form):
    f = form[-5:]
    if not f:
        return 1.5
    return sum(3 if c == "W" else 1 if c == "D" else 0 for c in f) / len(f)


def pois(l, k):
    return math.exp(-l) * l ** k / math.factorial(k)


def tau(i, j, a, b, r):
    if i == 0 and j == 0:
        return 1 - a * b * r
    if i == 0 and j == 1:
        return 1 + a * r
    if i == 1 and j == 0:
        return 1 + b * r
    if i == 1 and j == 1:
        return 1 - r
    return 1


def predict(s):
    H, A = s["h"], s["a"]
    LH, LA = max(s["lh"], .3), max(s["la"], .3)
    lh = H["gf"] * A["ga"] / LH
    la = A["gf"] * H["ga"] / LA
    e = (H["elo"] - A["elo"]) / 400
    lh *= 1.15 ** e * (1 + (ppg(H["form"]) - 1.5) * .04)
    la *= 1.15 ** -e * (1 + (ppg(A["form"]) - 1.5) * .04)
    lh, la = max(lh, .05), max(la, .05)
    rlh, rla = lh, la
    lh, la = lh * CAL["kh"], la * CAL["ka"]
    N = 8
    m, t = {}, 0
    for i in range(N):
        for j in range(N):
            m[i, j] = pois(lh, i) * pois(la, j) * tau(i, j, lh, la, -.1)
            t += m[i, j]
    r = dict(ph=0, pd=0, pa=0, o25=0, bt=0)
    for (i, j), p in m.items():
        p /= t
        if i > j:
            r["ph"] += p
        elif i == j:
            r["pd"] += p
        else:
            r["pa"] += p
        if i + j > 2:
            r["o25"] += p
        if i and j:
            r["bt"] += p
    r["lh"], r["la"] = lh, la
    r["rlh"], r["rla"] = rlh, rla
    return {k: round(v, 4) for k, v in r.items()}


now = datetime.now(timezone.utc)
out = []
for m in matches:
    when = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
    if m["status"] == "FINISHED":
        if when < now - timedelta(hours=48):
            continue
    elif when > now + timedelta(days=7) or when < now - timedelta(hours=6):
        continue
    ah, aa = avgs(m["_c"])
    h, a = m["homeTeam"], m["awayTeam"]
    hg, ag = goals(m)
    out.append({
        "id": m["id"], "comp": m["_cn"], "code": m["_c"], "utc": m["utcDate"],
        "status": m["status"], "h": tname(h), "a": tname(a),
        "score": [hg, ag] if hg is not None else None,
        "s": {
            "h": team_stats(h["id"], True, ah, aa),
            "a": team_stats(a["id"], False, aa, ah),
            "lh": round(ah, 2), "la": round(aa, 2),
        },
    })

out.sort(key=lambda x: x["utc"])

# Odds (from odds.json, refreshed by a separate workflow)
STOP = {"fc", "cf", "afc", "ac", "as", "ssc", "sc", "sv", "vfb", "vfl", "fsv", "rb", "1", "de",
        "the", "club", "calcio", "fk", "sk", "us", "ud", "cd", "rc", "rcd", "bsc", "tsg", "if"}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(w for w in s.split() if w not in STOP)


def same(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    return a == b or a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75


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
CAL = {"kh": 1.0, "ka": 1.0}
try:
    with open("predictions.json") as f:
        _pp = [p for p in json.load(f).values() if p.get("final")]
except Exception:
    _pp = []
if len(_pp) >= 10:
    _n = len(_pp)
    _w = _n / (_n + 120)  # trust the data more as it grows
    _ph = sum(p["p"].get("rlh", p["p"]["lh"]) for p in _pp) / _n
    _pa = sum(p["p"].get("rla", p["p"]["la"]) for p in _pp) / _n
    _ah = sum(p["final"][0] for p in _pp) / _n
    _aa = sum(p["final"][1] for p in _pp) / _n
    CAL["kh"] = round(min(1.15, max(0.85, 1 + (_ah / _ph - 1) * _w)), 4)
    CAL["ka"] = round(min(1.15, max(0.85, 1 + (_aa / _pa - 1) * _w)), 4)
print("calibration:", CAL, "from", len(_pp), "results")

# Injuries (from injuries.json, refreshed by a separate workflow)
try:
    with open("injuries.json") as f:
        inj_data = json.load(f)
except Exception:
    inj_data = {"updated": None, "items": []}

for x in out:
    if x["status"] not in ("SCHEDULED", "TIMED") or not inj_data["items"]:
        continue
    m = mid[x["id"]]
    when = datetime.fromisoformat(x["utc"].replace("Z", "+00:00"))
    res = {}
    for side, key in (("h", "homeTeam"), ("a", "awayTeam")):
        names = [m[key].get("name"), tname(m[key])]
        res[side] = [{"n": i["player"], "r": i["reason"]} for i in inj_data["items"]
                     if abs((datetime.fromisoformat(i["date"].replace("Z", "+00:00")) - when).total_seconds()) < 36 * 3600
                     and any(same(i["team"], n) for n in names)][:8]
    if res["h"] or res["a"]:
        x["inj"] = res

with open("data.json", "w") as f:
    json.dump({"updated": now.isoformat(), "odds_updated": odds_data["updated"], "calib": CAL, "matches": out, "tables": tables}, f, ensure_ascii=False)
print("matches written:", len(out))

# Results tracker: save each prediction before kickoff, score it after full time
try:
    with open("predictions.json") as f:
        preds = json.load(f)
except Exception:
    preds = {}

for x in out:
    start = datetime.fromisoformat(x["utc"].replace("Z", "+00:00"))
    if x["status"] in ("SCHEDULED", "TIMED") and start > now:
        preds[str(x["id"])] = {
            "id": x["id"], "comp": x["comp"], "code": x["code"], "utc": x["utc"],
            "h": x["h"], "a": x["a"], "p": predict(x["s"]), "odds": x.get("odds"),
            "final": None, "made": now.isoformat(),
        }

byid = {m["id"]: m for m in fin}
for p in preds.values():
    if p["final"] is None and p["id"] in byid:
        hg, ag = goals(byid[p["id"]])
        p["final"] = [hg, ag]

with open("predictions.json", "w") as f:
    json.dump(preds, f, ensure_ascii=False)
print("predictions stored:", len(preds))
