import os
import json
import re
import time
import calendar
import feedparser
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]

FEED_URL = "https://www.varzesh3.com/rss/domesticfootball"
STATE_FILE = "state_varzesh3.json"
MAX_AGE_HOURS = 8
CHANNEL_TAG = "@moj_football"

EXCLUDE_KEYWORDS = [
    "فوتسال", "والیبال", "بسکتبال", "کشتی", "هندبال", "تنیس",
    "کاراته", "تکواندو", "وزنه‌برداری", "وزنه برداری",
    "شنا", "دوومیدانی", "بدمینتون", "بولینگ", "بیلیارد",
    "زنان", "بانوان", "دختران",
    "جنگ", "موشک", "حمله", "تحریم", "پهپاد", "نظامی",
    "اسرائیل", "آمریکا", "ترامپ", "دیپلماسی", "سیاسی",
]

INCLUDE_KEYWORDS = [
    "فوتبال", "لیگ برتر", "جام حذفی", "تیم ملی", "دیدار", "بازیکن",
    "مربی", "سرمربی", "دروازه‌بان", "گل زد", "پنالتی", "داور",
    "استقلال", "پرسپولیس", "سپاهان", "تراکتور", "فولاد", "ذوب‌آهن",
    "ملوان", "گل‌گهر", "مس رفسنجان", "نساجی", "آلومینیوم", "پیکان",
    "خیبر", "چادرملو", "فجر سپاسی",
]


def is_football_news(title, summary):
    text = (title + " " + summary).lower()

    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in text:
            return False

    for kw in INCLUDE_KEYWORDS:
        if kw.lower() in text:
            return True

    return False


def clean_html(raw_html):
    return re.sub("<.*?>", "", raw_html or "")


def get_timestamp(entry):
    if entry.get("published_parsed"):
        return calendar.timegm(entry.published_parsed)
    if entry.get("updated_parsed"):
        return calendar.timegm(entry.updated_parsed)
    return 0


def extract_image(entry):
    # روش ۱: تگ media:content
    if hasattr(entry, "media_content") and entry.media_content:
        url = entry.media_content[0].get("url")
        if url:
            return url

    # روش ۲: تگ media:thumbnail
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        url = entry.media_thumbnail[0].get("url")
        if url:
            return url

    # روش ۳: enclosure (فایل ضمیمه)
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            enc_type = enc.get("type", "")
            if "image" in enc_type:
                return enc.get("href") or enc.get("url")

    # روش ۴: جستجوی مستقیم توی خود متن HTML خلاصه (fallback)
    raw_summary = entry.get("summary", "")
    img_match = re.search(r'<img[^>]+src="([^"]+)"', raw_summary)
    if img_match:
        return img_match.group(1)

    return None


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_posted_ts": 0}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def send_text(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()


def send_photo(photo_url, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": CHANNEL_ID,
        "photo": photo_url,
        "caption": caption[:1024],
        "parse_mode": "HTML",
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()


def main():
    state = load_state()
    last_posted_ts = state.get("last_posted_ts", 0)
    now_ts = calendar.timegm(time.gmtime())
    min_ts = now_ts - (MAX_AGE_HOURS * 3600)

    feed = feedparser.parse(FEED_URL)

    candidates = []
    for entry in feed.entries:
        ts = get_timestamp(entry)
        if ts > last_posted_ts and ts >= min_ts:
            title = entry.get("title", "")
            summary = clean_html(entry.get("summary", ""))
            if is_football_news(title, summary):
                image_url = extract_image(entry)
                candidates.append((ts, title, summary, image_url))

    if not candidates:
        print("هیچ خبر فوتبالی جدیدی (در بازه ۸ ساعت اخیر) پیدا نشد.")
        return

    candidates.sort(key=lambda x: x[0])
    ts, title, summary, image_url = candidates[0]

    try:
        message = f"<b>{title}</b>\n\n{summary}\n\n{CHANNEL_TAG}"
        if image_url:
            try:
                send_photo(image_url, message)
            except Exception as e:
                print(f"ارسال عکس ناموفق بود، فقط متن ارسال می‌شود: {e}")
                send_text(message)
        else:
            send_text(message)

        print(f"پست شد: {title} | عکس: {'بله' if image_url else 'خیر'}")
        state["last_posted_ts"] = ts
        save_state(state)
    except Exception as e:
        print(f"خطا در ارسال: {e}")


if __name__ == "__main__":
    main()
