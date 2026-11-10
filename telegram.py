import glob, json, os, re, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from PIL import Image, ImageDraw, ImageFont

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT = os.environ.get("TELEGRAM_CHAT_ID")
SITE = "https://spencer-pessy.github.io/pitchiq/?ref=telegram"

with open("predictions.json") as f:
    preds = list(json.load(f).values())

now = datetime.now(timezone.utc)
lim = now + timedelta(hours=36)


def when(p):
    return datetime.fromisoformat(p["utc"].replace("Z", "+00:00"))


def call(method, data, ctype):
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data, headers={"Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def news_post():
    """No matches today: post a few football headlines (title + link only, from BBC Sport)."""
    FEEDS = [("news", "https://feeds.bbci.co.uk/sport/football/rss.xml", 3),
             ("gossip", "https://feeds.bbci.co.uk/sport/football/gossip/rss.xml", 2)]
    SKIP = re.compile(r"\b(dies|died|death|dead|funeral|tragedy|arrest\w*|charged|court|trial|police|abuse|assault|bet|betting|gambling|odds)\b", re.I)
    try:
        with open("daily/news_seen.json") as f:
            seen = json.load(f)
    except Exception:
        seen = []
    picked = {"news": [], "gossip": []}
    for kind, url, n in FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PitchIQ/1.0 (+https://spencer-pessy.github.io/pitchiq/)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                root = ET.fromstring(r.read())
        except Exception as e:
            print("feed failed:", url, e)
            continue
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").split("?")[0].strip()
            try:
                pub = parsedate_to_datetime(it.findtext("pubDate"))
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if not title or not link or link in seen or SKIP.search(title):
                continue
            if now - pub > timedelta(hours=36):
                continue
            if any(link == x[1] for v in picked.values() for x in v):
                continue
            picked[kind].append((title, link))
            if len(picked[kind]) >= n:
                break
    total = len(picked["news"]) + len(picked["gossip"])
    if total < 2:
        print("No matches and not enough fresh headlines; nothing sent.")
        return
    lines = ["📰 Football news - " + now.strftime("%a %d %b"), "Headlines from BBC Sport. Tap to read.", ""]
    for t, l in picked["news"]:
        lines += ["• " + t, "  " + l, ""]
    if picked["gossip"]:
        lines += ["🔁 Transfer talk (reports, not confirmed):", ""]
        for t, l in picked["gossip"]:
            lines += ["• " + t, "  " + l, ""]
    lines += ["PitchIQ forecasts return on match days: " + SITE,
              "Headlines are reported by BBC Sport; PitchIQ doesn't verify them."]
    msg = "\n".join(lines)
    print(msg)
    if not (TOKEN and CHAT):
        print("\n(Dry run: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set, nothing sent.)")
        return
    try:
        print("Telegram news post:", call("sendMessage", json.dumps({"chat_id": CHAT, "text": msg, "disable_web_page_preview": True}).encode(), "application/json").get("ok"))
    except urllib.error.HTTPError as e:
        print("Telegram error:", e.code, e.read().decode()[:200])
        raise SystemExit(1)
    for v in picked.values():
        seen += [l for _, l in v]
    os.makedirs("daily", exist_ok=True)
    with open("daily/news_seen.json", "w") as f:
        json.dump(seen[-200:], f)


up = [p for p in preds if not p.get("final") and now < when(p) < lim]
if not up:
    print("No matches in the next 36 hours; posting news instead.")
    news_post()
    raise SystemExit

rows = []
for p in up:
    v = [p["p"]["ph"], p["p"]["pd"], p["p"]["pa"]]
    i = v.index(max(v))
    pick = ["Home win: " + p["h"], "Draw", "Away win: " + p["a"]][i]
    rows.append((v[i], p, pick))
rows.sort(key=lambda r: -r[0])
top = rows[:3]

# ---------- message text ----------
lines = [f"⚽ PitchIQ - Top {len(top)} pick{'s' if len(top) > 1 else ''}", now.strftime("%a %d %b") + " (times in UTC)", ""]
for k, (c, p, pick) in enumerate(top, 1):
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


# ---------- picture ----------
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


try:
    print("Telegram photo post:", send_photo().get("ok"))
except Exception as e:
    print("Photo failed, sending text only:", e)
    try:
        r = call("sendMessage", json.dumps({"chat_id": CHAT, "text": text, "disable_web_page_preview": True}).encode(), "application/json")
        print("Telegram text post:", r.get("ok"))
    except urllib.error.HTTPError as e2:
        print("Telegram error:", e2.code, e2.read().decode()[:200])
        raise SystemExit(1)
