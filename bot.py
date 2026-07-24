import os
import json
import feedparser
import requests
import re

# ---------- تنظیمات از Secrets ----------
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# ---------- منابع خبری ----------
FEEDS = {
    "ایران": [
        "https://www.varzesh3.com/rss/domesticfootball",
    ],
    "خارجی": [
        "https://feeds.bbci.co.uk/sport/football/rss.xml",
        "https://www.skysports.com/rss/12040",
        "https://www.goal.com/en/feeds/news?fmt=rss",
    ],
}

POSTED_FILE = "posted.json"


def load_posted():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_posted(posted):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(posted), f, ensure_ascii=False)


def clean_html(raw_html):
    return re.sub("<.*?>", "", raw_html or "")


def translate_and_summarize(title, summary, source_name, link, category):
    prompt = f"""شما یک دستیار خبرنگار ورزشی فارسی‌زبان هستید.
متن خبر زیر را به فارسی روان خلاصه و بازنویسی کن (نه ترجمه کلمه به کلمه، بلکه بازنویسی کامل با کلمات خودت، حداکثر ۴ خط).
در پایان چیزی درباره منبع ننویس، فقط خلاصه خبر را بده.

عنوان: {title}
متن: {summary}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

    tag = "🇮🇷 ایران" if category == "ایران" else "🌍 جهان"
    message = f"{tag}\n\n{text}\n\n📰 منبع: {source_name}\n🔗 {link}"
    return message


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
    posted = load_posted()
    new_posted = set(posted)

    for category, urls in FEEDS.items():
        for feed_url in urls:
            try:
                feed = feedparser.parse(feed_url)
                source_name = feed.feed.get("title", feed_url)
            except Exception as e:
                print(f"خطا در خواندن فید {feed_url}: {e}")
                continue

            for entry in feed.entries[:2]:
                uid = entry.get("id", entry.get("link"))
                if uid in posted:
                    continue

                title = entry.get("title", "")
                summary = clean_html(entry.get("summary", ""))
                link = entry.get("link", "")

                try:
                    message = translate_and_summarize(
                        title, summary, source_name, link, category
                    )
                    send_to_telegram(message)
                    print(f"پست شد: {title}")
                    new_posted.add(uid)
                except Exception as e:
                    print(f"خطا در پردازش/ارسال خبر: {e}")

    save_posted(new_posted)


if __name__ == "__main__":
    main()
