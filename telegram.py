import json, os, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT = os.environ.get("TELEGRAM_CHAT_ID")
SITE = "https://spencer-pessy.github.io/pitchiq/?ref=telegram"

with open("predictions.json") as f:
    preds = json.load(f).values()

now = datetime.now(timezone.utc)
lim = now + timedelta(hours=36)


def when(p):
    return datetime.fromisoformat(p["utc"].replace("Z", "+00:00"))


up = [p for p in preds if not p.get("final") and now < when(p) < lim]
if not up:
    print("No matches in the next 36 hours; nothing sent.")
    raise SystemExit

rows = []
for p in up:
    v = [p["p"]["ph"], p["p"]["pd"], p["p"]["pa"]]
    i = v.index(max(v))
    pick = ["Home win: " + p["h"], "Draw", "Away win: " + p["a"]][i]
    rows.append((v[i], p, pick))
rows.sort(key=lambda r: -r[0])

lines = ["⚽ PitchIQ - Top 3 picks", now.strftime("%a %d %b") + " (times in UTC)", ""]
for k, (c, p, pick) in enumerate(rows[:3], 1):
    lines += [f"{k}. {p['h']} vs {p['a']}",
              f"   {p['comp']} · {when(p).strftime('%H:%M')}",
              f"   Model: {pick} {round(c * 100)}%", ""]

done = [p for p in preds if p.get("final")]
if done:
    hit = 0
    for p in done:
        v = [p["p"]["ph"], p["p"]["pd"], p["p"]["pa"]]
        a, b = p["final"]
        act = 0 if a > b else 1 if a == b else 2
        hit += v.index(max(v)) == act
    lines.append(f"Record so far: {hit} of {len(done)} results right ({round(hit / len(done) * 100)}%).")
lines += ["Full forecasts: " + SITE, "Model estimates, not tips or guarantees. 18+ only."]
text = "\n".join(lines)

print(text)
if not (TOKEN and CHAT):
    print("\n(Dry run: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set, nothing sent.)")
    raise SystemExit

req = urllib.request.Request(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data=json.dumps({"chat_id": CHAT, "text": text, "disable_web_page_preview": True}).encode(),
    headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print("Telegram says:", json.load(r).get("ok"))
except urllib.error.HTTPError as e:
    print("Telegram error:", e.code, e.read().decode()[:200])
    raise SystemExit(1)
