import glob, json, os, re, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pitchiq_telegram import (parse_kickoff, valid_forecast, valid_final, clean_seen_urls,
                              snapshot_published_pick, clean_pick_state, resolve_published_picks, pick_label)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT = os.environ.get("TELEGRAM_CHAT_ID")
SITE = "https://spencer-pessy.github.io/pitchiq/?ref=telegram"

with open("predictions.json") as f:
    raw_preds = json.load(f)
preds = list(raw_preds.values()) if isinstance(raw_preds, dict) else []

now = datetime.now(timezone.utc)
lim = now + timedelta(hours=36)


def when(p):
    return parse_kickoff(p.get("utc"))


def call(method, data, ctype):
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data, headers={"Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def load_pick_state():
    try:
        with open("daily/published_picks.json", encoding="utf-8") as f:
            return clean_pick_state(json.load(f))
    except Exception:
        return clean_pick_state({})


def save_pick_state(state):
    os.makedirs("daily", exist_ok=True)
    with open("daily/published_picks.json", "w", encoding="utf-8") as f:
        json.dump(clean_pick_state(state), f, ensure_ascii=False, indent=2)


pick_state = load_pick_state()
RESULTS_ONLY = os.environ.get("PITCHIQ_RESULTS_ONLY") == "1"
completed_picks, resolved_state = resolve_published_picks(pick_state, preds)
# Results are sent only by the dedicated results workflow. This prevents the
# daily picks workflow from sending a result and then failing before saving it.
if completed_picks and RESULTS_ONLY:
    result_lines = ["✅ PitchIQ — Results for our published picks", now.strftime("%a %d %b") + " · Full-time scores", ""]
    for item in completed_picks:
        mark = "✓ CORRECT" if item["correct"] else "✗ MISSED"
        result_lines += [
            f'{item["h"]} {item["final"][0]}–{item["final"][1]} {item["a"]}',
            f'   Pick: {pick_label(item)} ({round(item["p"][("ph", "pd", "pa")[item["pick_index"]]] * 100)}%) · {mark}',
            f'   {item["comp"]}', ""
        ]
    result_lines += ["These are the results of the exact picks previously published by PitchIQ.",
                     "Original probabilities are preserved. Model estimates, not guarantees."]
    result_message = "\n".join(result_lines)
    print(result_message)
    if TOKEN and CHAT:
        response = call("sendMessage", json.dumps({"chat_id": CHAT, "text": result_message,
                           "disable_web_page_preview": True}).encode(), "application/json")
        if not response.get("ok"):
            raise RuntimeError("Telegram did not confirm the results message.")
        pick_state = resolved_state
    else:
        print("(Dry run: results remain pending because Telegram credentials are unavailable.)")
        pick_state = clean_pick_state(pick_state)


if RESULTS_ONLY:
    save_pick_state(pick_state)
    print("Results-only check complete; no new picks or news posts were requested.")
    raise SystemExit(0)

up = [p for p in preds if valid_forecast(p) and snapshot_published_pick(p) is not None
      and not p.get("final") and now < when(p) < lim]
if not up:
    print("No eligible matches in the next 36 hours; no Telegram post will be sent.")
    save_pick_state(pick_state)
    raise SystemExit(0)

rows = []
for p in up:
    if str(p.get('id')) in pick_state['sent_ids']:
        continue
    v = [p["p"]["ph"], p["p"]["pd"], p["p"]["pa"]]
    i = v.index(max(v))
    pick = ["Home win: " + p["h"], "Draw", "Away win: " + p["a"]][i]
    rows.append((v[i], p, pick))
if not rows:
    print("No new eligible picks remain after duplicate filtering; no Telegram post will be sent.")
    save_pick_state(pick_state)
    raise SystemExit(0)

rows.sort(key=lambda r: -r[0])
top = rows[:3]
for _, record, _ in top:
    snap = snapshot_published_pick(record)
    if snap and snap["id"] not in pick_state["sent_ids"]:
        pick_state["pending"].append(snap)
        pick_state["sent_ids"].append(snap["id"])
pick_state = clean_pick_state(pick_state)

# ---------- message text ----------
lines = [f"⚽ PitchIQ - Top {len(top)} pick{'s' if len(top) > 1 else ''}", now.strftime("%a %d %b") + " (times in UTC)", ""]
for k, (c, p, pick) in enumerate(top, 1):
    lines += [f"{k}. {p['h']} vs {p['a']}",
              f"   {p['comp']} · {when(p).strftime('%H:%M')}",
              f"   Model: {pick} {round(c * 100)}%", ""]
# Keep the public Telegram record consistent with the Results tab: only
# picks already published by this bot and settled in the persistent ledger.
published_results = pick_state["results"]
if published_results:
    hit = sum(item["correct"] is True for item in published_results)
    total = len(published_results)
    lines.append(
        f"Published-pick record: {hit} of {total} results right ({round(hit / total * 100)}%)."
    )
lines += ["Full forecasts: " + SITE, "Model estimates, not tips or guarantees. 18+ only."]
text = "\n".join(lines)
print(text)


# ---------- picture ----------
from PIL import Image, ImageDraw, ImageFont
def font(bold, size):
    names = ["DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf"] if bold else ["DejaVuSansCondensed.ttf", "DejaVuSans.ttf"]
    for n in names:
        for path in glob.glob("/usr/share/fonts/**/" + n, recursive=True):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


W, H = 1080, 1920
RED, INK, MUT, PAN = (225, 6, 0), (244, 244, 244), (156, 156, 156), (18, 18, 18)
im = Image.new("RGB", (W, H), (0, 0, 0))
d = ImageDraw.Draw(im)
d.rectangle([0, 0, W, 16], fill=RED)
d.rectangle([0, H - 16, W, H], fill=RED)


def fit(text, maxw, size, bold=True):
    f = font(bold, size)
    while d.textlength(text, font=f) > maxw and size > 24:
        size -= 4
        f = font(bold, size)
    return f


def center(y, text, f, fill=INK):
    d.text((W / 2, y), text, font=f, fill=fill, anchor="ms")


try:
    logo = Image.open("icon-192.png").convert("RGB").resize((160, 160))
    mask = Image.new("L", (160, 160), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, 159, 159], fill=255)
    im.paste(logo, (W // 2 - 80, 70), mask)
except Exception as e:
    print("logo skipped:", e)

fw = font(True, 56)
wa, wb = d.textlength("PITCH", font=fw), d.textlength("IQ", font=fw)
x0 = (W - wa - 16 - wb) / 2
d.text((x0, 300), "PITCH", font=fw, fill=INK, anchor="ls")
d.text((x0 + wa + 16, 300), "IQ", font=fw, fill=RED, anchor="ls")
center(410, f"TOP {len(top)} PICKS" if len(top) > 1 else "TOP PICK", font(True, 84))
center(462, now.strftime("%A %d %B").upper() + " · TIMES IN UTC", font(False, 34), MUT)

for k, (c, p, pick) in enumerate(top):
    y = 520 + k * 420
    d.rectangle([60, y, 1020, y + 390], fill=PAN)
    d.rectangle([60, y, 70, y + 390], fill=RED)
    d.text((100, y + 130), str(k + 1), font=font(True, 120), fill=RED, anchor="ls")
    d.text((210, y + 60), f"{p['comp']} · {when(p).strftime('%H:%M')}".upper(), font=font(False, 30), fill=MUT, anchor="ls")
    t = f"{p['h']} vs {p['a']}".upper()
    d.text((210, y + 125), t, font=fit(t, 780, 60), fill=INK, anchor="ls")
    t = pick.upper()
    d.text((100, y + 230), t, font=fit(t, 600, 46), fill=INK, anchor="ls")
    d.text((990, y + 240), f"{round(c * 100)}%", font=font(True, 110), fill=RED, anchor="rs")
    d.text((100, y + 320), "Model confidence", font=font(False, 32), fill=MUT, anchor="ls")

center(1830, "spencer-pessy.github.io/pitchiq", font(True, 42))
center(1878, "Model estimates, not guarantees. 18+ only.", font(False, 28), (111, 111, 111))
os.makedirs("daily", exist_ok=True)
im.save("daily/top3.png", optimize=True)
print("picture saved: daily/top3.png")

# ---------- send ----------
if not (TOKEN and CHAT):
    print("\n(Dry run: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set, nothing sent.)")
    raise SystemExit


def send_photo():
    b = "----pitchiq" + os.urandom(8).hex()

    def part(name, value):
        return f'--{b}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")

    with open("daily/top3.png", "rb") as f:
        img = f.read()
    body = (part("chat_id", CHAT) + part("caption", text[:1000]) +
            f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="top3.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
            + img + f"\r\n--{b}--\r\n".encode())
    return call("sendPhoto", body, f"multipart/form-data; boundary={b}")


delivered = False
try:
    photo_response = send_photo()
    delivered = bool(photo_response.get("ok"))
    print("Telegram photo post:", delivered)
    if not delivered:
        print("Telegram did not confirm photo delivery; trying text fallback.")
except Exception as e:
    print("Photo failed, sending text only:", e)

if not delivered:
    try:
        text_response = call("sendMessage", json.dumps({"chat_id": CHAT, "text": text, "disable_web_page_preview": True}).encode(), "application/json")
        delivered = bool(text_response.get("ok"))
        print("Telegram text post:", delivered)
    except Exception as e:
        print("Telegram text fallback failed:", e)
        raise SystemExit(1)
    if not delivered:
        raise RuntimeError("Telegram did not confirm either the photo or text pick post.")

# Only record picks after Telegram confirms that the post was delivered.
save_pick_state(pick_state)
