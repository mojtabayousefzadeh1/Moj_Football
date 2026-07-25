import os
import json
import re
import time
import feedparser
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]

FEED_URL = "https://www.varzesh3.com/rss/domesticfootball"
STATE_FILE = "state_varzesh3.json"
MAX_POSTS = 3
DELAY_BETWEEN_POSTS = 23 * 60  # 23 دقیقه

EXCLUDE_KEYWORDS = [
    "فوتسال", "والیبال", "بسکتبال", "کشتی", "هندبال", "تنیس",
    "کاراته", "تکواندو", "وزنه‌برداری", "وزنه برداری",
    "شنا", "دوومیدانی", "بدمینتون", "بولینگ", "بیلیارد",
    "زنان", "بانوان", "دختران",
]


def is_football_news(title, summary):
    text = (title + " " + summary).lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in text:
            return False
    return True


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
    source_name = feed.feed.get("title", "ورزش سه")

    new_entries = []
    for entry in feed.entries:
        uid = entry.get("id", entry.get("link"))
        if uid == last_posted_id:
            break
        title = entry.get("title", "")
        summary = clean_html(entry.get("summary", ""))
        link = entry.get("link", "")
        if is_football_news(title, summary):
            new_entries.append((uid, title, summary, link))

    if not new_entries:
        print("هیچ خبر فوتبالی جدیدی پیدا نشد.")
        return

    to_post = new_entries[:MAX_POSTS]
    to_post.reverse()

    newest_uid_posted = None
    for i, (uid, title, summary, link) in enumerate(to_post):
        try:
            message = f"🇮🇷 ورزش سه\n\n<b>{title}</b>\n\n{summary}\n\n📰 منبع: {source_name}\n🔗 {link}"
            send_to_telegram(message)
            print(f"پست شد: {title}")
            newest_uid_posted = uid
            if i < len(to_post) - 1:
                time.sleep(DELAY_BETWEEN_POSTS)
        except Exception as e:
            print(f"خطا در ارسال: {e}")

    if newest_uid_posted:
        state["last_posted_id"] = new_entries[0][0]
        save_state(state)


if __name__ == "__main__":
    main()
