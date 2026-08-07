import os
import json
import re
import time
import calendar
import html
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

# عبارت منبع خبر که وبسایت ورزش۳ در ابتدای متن‌ها می‌نویسد
# نمونه‌ها: به گزارش "ورزش سه"،  /  به گزارش "ورزش سه".  /  به گزارش «ورزش سه»،
SOURCE_PATTERN = re.compile(
    r'به\s*گزارش\s*["\u00ab\u2018\u201c]?\s*ورزش\s*(?:سه|3)\s*["\u00bb\u2019\u201d]?\s*[،.]?'
)
NEW_SOURCE_PHRASE = "به گزارش موج فوتبال،"


def is_football_news(title, summary):
    text = (title + " " + summary).lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in text:
            return False
    for kw in INCLUDE_KEYWORDS:
        if kw.lower() in text:
            return True
    return False


def is_video_content(link):
    return "video.varzesh3.com" in link or "/video/" in link


def clean_html(raw_html):
    return re.sub("<.*?>", "", raw_html or "")


def get_excerpt(entry):
    """خلاصه کوتاه خبر (تگ description/summary در RSS)."""
    return clean_html(entry.get("summary", ""))


def get_full_text(entry):
    """
    متن کامل خبر. اکثر فیدهای خبری فارسی این را در تگ
    <content:encoded> می‌گذارند که feedparser آن را در entry.content
    قرار می‌دهد. اگر این فیلد وجود نداشت، به‌جای آن از خلاصه استفاده
    می‌شود تا حداقل چیزی برای نمایش وجود داشته باشد.
    """
    if hasattr(entry, "content") and entry.content:
        value = entry.content[0].get("value", "")
        if value.strip():
            return clean_html(value)
    return clean_html(entry.get("summary", ""))


def replace_source(summary):
    """جایگزینی 'به گزارش "ورزش سه"،' با 'به گزارش موج فوتبال،'"""
    return SOURCE_PATTERN.sub(NEW_SOURCE_PHRASE, summary)


def get_timestamp(entry):
    if entry.get("published_parsed"):
        return calendar.timegm(entry.published_parsed)
    if entry.get("updated_parsed"):
        return calendar.timegm(entry.updated_parsed)
    return 0


def extract_image(entry):
    if hasattr(entry, "media_content") and entry.media_content:
        url = entry.media_content[0].get("url")
        if url:
            return url
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        url = entry.media_thumbnail[0].get("url")
        if url:
            return url
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if "image" in enc.get("type", ""):
                return enc.get("href") or enc.get("url")
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


def build_message(title, excerpt, full_text):
    """
    پیام نهایی: تیتر بولد + خلاصه به‌صورت متن عادی + متن کامل خبر
    به‌صورت نقل‌قول تاشو (expandable). منبع خبر داخل متن کامل
    از 'ورزش سه' به 'موج فوتبال' تغییر می‌کند.
    """
    fixed_full_text = replace_source(full_text)
    safe_title = html.escape(title)
    safe_excerpt = html.escape(excerpt)
    safe_full_text = html.escape(fixed_full_text)

    parts = [f"<b>{safe_title}</b>"]
    if safe_excerpt:
        parts.append(safe_excerpt)
    parts.append(f"<blockquote expandable>{safe_full_text}</blockquote>")
    parts.append(CHANNEL_TAG)

    return "\n\n".join(parts)


def trim_caption(message, limit=1024):
    """
    کپشن عکس تلگرام حداکثر ۱۰۲۴ کاراکتر است. اگر پیام طولانی‌تر باشد،
    آن را طوری کوتاه می‌کنیم که تگ blockquote سالم بسته بماند.
    """
    if len(message) <= limit:
        return message

    closing_tag = "</blockquote>"
    tail = f"...{closing_tag}\n\n{CHANNEL_TAG}"
    cut_length = limit - len(tail)
    return message[:cut_length] + tail


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
        "caption": trim_caption(caption),
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

    # --- DEBUG: این بلاک فقط برای تست ساختار فیده، بعد از تست حذفش کن ---
    if feed.entries:
        first = feed.entries[0]
        print("=== DEBUG: entry keys ===")
        print(list(first.keys()))
        print("=== DEBUG: summary (len=%d) ===" % len(first.get("summary", "")))
        print(first.get("summary", "")[:500])
        print("=== DEBUG: content ===")
        print(first.get("content", "ندارد"))
        print("=== DEBUG END ===")
    # --- پایان بلاک دیباگ ---

    candidates = []
    for entry in feed.entries:
        ts = get_timestamp(entry)
        if ts > last_posted_ts and ts >= min_ts:
            link = entry.get("link", "")
            if is_video_content(link):
                continue
            title = entry.get("title", "")
            excerpt = get_excerpt(entry)
            full_text = get_full_text(entry)
            if is_football_news(title, excerpt + " " + full_text):
                image_url = extract_image(entry)
                candidates.append((ts, title, excerpt, full_text, image_url))

    if not candidates:
        print("هیچ خبر فوتبالی جدیدی (در بازه ۸ ساعت اخیر) پیدا نشد.")
        return

    candidates.sort(key=lambda x: x[0])
    ts, title, excerpt, full_text, image_url = candidates[-1]

    try:
        message = build_message(title, excerpt, full_text)
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
