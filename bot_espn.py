import os
import json
import re
import time
import calendar
import feedparser
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"

FEED_URL = "https://www.espn.com/espn/rss/soccer/news"
STATE_FILE = "state_espn.json"
MAX_POSTS = 2
DELAY_BETWEEN_POSTS = 30 * 60  # 30 دقیقه
MAX_AGE_HOURS = 24

EXCLUDE_KEYWORDS = [
    "women's", "womens", "wsl", "nwsl", "female", "ladies",
    "women national team", "girls",
]


def clean_html(raw_html):
    return re.sub("<.*?>", "", raw_html or "")


def get_timestamp(entry):
    if entry.get("published_parsed"):
        return calendar.timegm(entry.published_parsed)
    if entry.get("updated_parsed"):
        return calendar.timegm(entry.updated_parsed)
    return 0


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_posted_id": None, "last_posted_ts": 0}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def rewrite_with_gemini(title, summary):
    prompt = f"""شما یک دستیار خبرنگار ورزشی فارسی‌زبان هستید.
متن خبر زیر را (به هر زبانی که هست) به فارسی روان خلاصه و بازنویسی کن
(نه ترجمه کلمه‌به‌کلمه، بلکه بازنویسی کامل با کلمات خودت، حداکثر ۴ خط).

مهم: خروجی تو باید فقط و فقط همون خلاصه فارسی باشه. هیچ توضیح اضافه‌ای درباره
زبان متن، مراحل کارت، یا هر چیز دیگه‌ای ننویس. مستقیم با خلاصه خبر شروع کن.

عنوان: {title}
متن: {summary}
"""
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(GEMINI_URL, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()


def main():
    state = load_state()
    last_posted_ts = state.get("last_posted_ts", 0)
    now_ts = calendar.timegm(time.gmtime())
    min_ts = now_ts - (MAX_AGE_HOURS * 3600)

    feed = feedparser.parse(FEED_URL)
    source_name = feed.feed.get("title", "ESPN")

    candidates = []
    for entry in feed.entries:
        ts = get_timestamp(entry)
        if ts > last_posted_ts and ts >= min_ts:
            title = entry.get("title", "")
            summary = clean_html(entry.get("summary", ""))
            text_lower = (title + " " + summary).lower()
            if any(kw in text_lower for kw in EXCLUDE_KEYWORDS):
                continue
            uid = entry.get("id", entry.get("link"))
            link = entry.get("link", "")
            candidates.append((ts, uid, title, summary, link))

    if not candidates:
        print("هیچ خبر جدیدی پیدا نشد.")
        return

    candidates.sort(key=lambda x: x[0])
    to_post = candidates[-MAX_POSTS:]

    newest_ts_posted = last_posted_ts
    for i, (ts, uid, title, summary, link) in enumerate(to_post):
        try:
            rewritten = rewrite_with_gemini(title, summary)
            message = f"🌍 ESPN\n\n{rewritten}\n\n📰 منبع: {source_name}\n🔗 {link}"
            send_to_telegram(message)
            print(f"پست شد: {title}")
            newest_ts_posted = max(newest_ts_posted, ts)
            if i < len(to_post) - 1:
                time.sleep(DELAY_BETWEEN_POSTS)
        except Exception as e:
            print(f"خطا در پردازش/ارسال خبر: {e}")

    state["last_posted_ts"] = newest_ts_posted
    save_state(state)


if __name__ == "__main__":
    main()
