import os
import json
import re
import time
import feedparser
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"

FEED_URL = "https://www.skysports.com/rss/12040"
STATE_FILE = "state_sky.json"
MAX_POSTS = 2
DELAY_BETWEEN_POSTS = 30 * 60  # 30 دقیقه


def clean_html(raw_html):
    return re.sub("<.*?>", "", raw_html or "")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_posted_id": None}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def rewrite_with_gemini(title, summary):
    prompt = f"""شما یک دستیار خبرنگار ورزشی فارسی‌زبان هستید.
متن خبر زیر ممکن است به هر زبانی (انگلیسی یا هر زبان دیگری) نوشته شده باشد.
ابتدا زبان متن را تشخیص بده، سپس آن را به فارسی روان خلاصه و بازنویسی کن
(نه ترجمه کلمه‌به‌کلمه، بلکه بازنویسی کامل با کلمات خودت، حداکثر ۴ خط).
در پایان چیزی درباره منبع ننویس، فقط خلاصه خبر را بده.

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
    last_posted_id = state.get("last_posted_id")

    feed = feedparser.parse(FEED_URL)
    source_name = feed.feed.get("title", "Sky Sports")

    new_entries = []
    for entry in feed.entries:
        uid = entry.get("id", entry.get("link"))
        if uid == last_posted_id:
            break
        title = entry.get("title", "")
        summary = clean_html(entry.get("summary", ""))
        link = entry.get("link", "")
        new_entries.append((uid, title, summary, link))

    if not new_entries:
        print("هیچ خبر جدیدی پیدا نشد.")
        return

    to_post = new_entries[:MAX_POSTS]
    to_post.reverse()

    newest_uid_posted = None
    for i, (uid, title, summary, link) in enumerate(to_post):
        try:
            rewritten = rewrite_with_gemini(title, summary)
            message = f"🌍 Sky Sports\n\n{rewritten}\n\n📰 منبع: {source_name}\n🔗 {link}"
            send_to_telegram(message)
            print(f"پست شد: {title}")
            newest_uid_posted = uid
            if i < len(to_post) - 1:
                time.sleep(DELAY_BETWEEN_POSTS)
        except Exception as e:
            print(f"خطا در پردازش/ارسال خبر: {e}")

    if newest_uid_posted:
        state["last_posted_id"] = new_entries[0][0]
        save_state(state)


if __name__ == "__main__":
    main()
