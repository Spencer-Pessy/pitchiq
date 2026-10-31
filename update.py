import json, os, time, urllib.request, urllib.error
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
with open("data.json", "w") as f:
    json.dump({"updated": now.isoformat(), "matches": out}, f, ensure_ascii=False)
print("matches written:", len(out))
