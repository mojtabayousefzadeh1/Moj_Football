import os
import json
import re
import time
import calendar
import html
import feedparser
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
)

FEED_URL = "https://feeds.bbci.co.uk/sport/football/rss.xml"
STATE_FILE = "state_bbc.json"
MAX_AGE_HOURS = 8
CHANNEL_TAG = "@moj_football"
SOURCE_PREFIX = "به گزارش موج فوتبال، "


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
    return {"last_posted_ts": 0}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def fetch_bbc_article_text(link):
    """
    RSS بی‌بی‌سی فقط یک خلاصه‌ی کوتاه می‌دهد. این تابع خود صفحه‌ی خبر
    را باز کرده و متن کامل انگلیسی مقاله را استخراج می‌کند.

    ساختار صفحات BBC Sport معمولاً بلوک‌های متن را داخل
    <div data-component="text-block"> و پاراگراف‌ها را داخل <p>
    قرار می‌دهد. اگر این ساختار پیدا نشد (به‌خاطر تغییر طراحی سایت)،
    به fallback ساده‌تر (تمام <p> های داخل <article>) سوییچ می‌کند.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            )
        }
        r = requests.get(link, headers=headers, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        paragraphs = []

        # حالت اول: بلوک‌های متنی استاندارد BBC
        text_blocks = soup.find_all(
            "div", attrs={"data-component": ["text-block", "correspondent-block"]}
        )
        for block in text_blocks:
            for p in block.find_all("p"):
                text = p.get_text(separator="", strip=True)
                if text:
                    paragraphs.append(text)

        # حالت دوم (fallback): تمام <p> داخل <article>
        if not paragraphs:
            article = soup.find("article")
            if article:
                for p in article.find_all("p"):
                    text = p.get_text(separator="", strip=True)
                    if text:
                        paragraphs.append(text)

        if paragraphs:
            return "\n\n".join(paragraphs)
    except Exception as e:
        print(f"خطا در دریافت متن کامل خبر بی‌بی‌سی ({link}): {e}")
    return None


def translate_with_gemini(title, excerpt, full_text):
    """
    عنوان، خلاصه و متن کامل انگلیسی را یکجا به جمنای می‌دهد و
    ترجمه‌ی فارسی هر سه بخش را با جداکننده‌های مشخص پس می‌گیرد.

    به‌جای JSON از یک فرمت متنی ساده با جداکننده استفاده شده، چون
    وقتی متن ترجمه‌شده چند پاراگراف و خط جدید دارد، مدل‌های زبانی
    گاهی JSON نامعتبر (با خط جدید خام داخل رشته) تولید می‌کنند که
    پارس کردنش شکننده است.
    """
    prompt = f"""شما یک مترجم و خبرنگار ورزشی حرفه‌ای فارسی‌زبان هستید.

متن خبر انگلیسی زیر (از بی‌بی‌سی ورزشی) را به فارسی روان و طبیعی برگردان.
خروجی را دقیقاً با همین سه جداکننده و به همین ترتیب بنویس. هیچ توضیح،
مقدمه یا متن اضافه‌ای غیر از این سه بخش ننویس:

===TITLE===
(ترجمه‌ی روان تیتر خبر به فارسی، فقط یک خط)
===EXCERPT===
(خلاصه‌ی بسیار کوتاه خبر در یک تا دو جمله‌ی فارسی)
===BODY===
(ترجمه‌ی کامل و روان کل متن خبر به فارسی؛ بازنویسی خبرنگاری با کلمات
خودت نه ترجمه کلمه‌به‌کلمه، اما بدون حذف اطلاعات مهم؛ پاراگراف‌بندی
اصلی را با یک خط خالی بین پاراگراف‌ها حفظ کن)

عنوان انگلیسی: {title}
خلاصه‌ی انگلیسی: {excerpt}
متن کامل انگلیسی:
{full_text}
"""
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(GEMINI_URL, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

    title_match = re.search(r"===TITLE===\s*(.*?)\s*===EXCERPT===", raw_text, re.S)
    excerpt_match = re.search(r"===EXCERPT===\s*(.*?)\s*===BODY===", raw_text, re.S)
    body_match = re.search(r"===BODY===\s*(.*)", raw_text, re.S)

    if not (title_match and excerpt_match and body_match):
        raise ValueError(f"خروجی جمنای قابل پارس نبود:\n{raw_text[:500]}")

    return {
        "title": title_match.group(1).strip(),
        "excerpt": excerpt_match.group(1).strip(),
        "body": body_match.group(1).strip(),
    }


def build_message(fa_title, fa_excerpt, fa_body, source_name, link):
    safe_title = html.escape(fa_title)
    safe_excerpt = html.escape(fa_excerpt)
    safe_body = html.escape(SOURCE_PREFIX + fa_body)

    parts = [f"<b>{safe_title}</b>"]
    if safe_excerpt:
        parts.append(safe_excerpt)
    parts.append(f"<blockquote expandable>{safe_body}</blockquote>")
    parts.append(CHANNEL_TAG)
    # توجه: source_name و link عمداً به متن پیام اضافه نمی‌شوند
    # (طبق درخواست، در کانال تلگرام نمایش داده نشوند)

    return "\n\n".join(parts)


def trim_message(message, limit=4096):
    """
    محدودیت طول پیام متنی تلگرام ۴۰۹۶ کاراکتر است. اگر رد شد،
    طوری کوتاه می‌کنیم که تگ blockquote سالم بسته بماند.
    """
    if len(message) <= limit:
        return message
    closing_tag = "</blockquote>"
    tail_idx = message.rfind(closing_tag)
    if tail_idx == -1:
        return message[:limit]
    after = message[tail_idx + len(closing_tag):]
    budget = limit - len(after) - len(closing_tag) - 3
    return message[:budget] + "..." + closing_tag + after


def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": trim_message(message),
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

    if feed.entries:
        first = feed.entries[0]
        print(f"=== DEBUG: کلیدهای موجود در خبر اول: {list(first.keys())}")
        print(f"=== DEBUG: media_thumbnail: {first.get('media_thumbnail', 'وجود ندارد')}")
        print(f"=== DEBUG: media_content: {first.get('media_content', 'وجود ندارد')}")

    # --- DEBUG: بعد از پیدا کردن علت مشکل، این بلاک رو حذف کن ---
    print(f"=== DEBUG: تعداد کل آیتم‌های فید: {len(feed.entries)}")
    print(f"=== DEBUG: last_posted_ts ذخیره‌شده: {last_posted_ts}")
    print(f"=== DEBUG: now_ts: {now_ts} | min_ts (۸ ساعت قبل): {min_ts}")
    if feed.bozo:
        print(f"=== DEBUG: خطای پارس فید (bozo): {feed.bozo_exception}")
    for e in feed.entries[:5]:
        ts = get_timestamp(e)
        print(
            f"=== DEBUG entry: ts={ts} | "
            f"newer_than_last={ts > last_posted_ts} | "
            f"within_8h={ts >= min_ts} | title={e.get('title', '')[:60]}"
        )
    print("=== DEBUG END ===")
    # --- پایان بلاک دیباگ ---

    candidates = []
    for entry in feed.entries:
        ts = get_timestamp(entry)
        if ts > last_posted_ts and ts >= min_ts:
            title = entry.get("title", "")
            excerpt = clean_html(entry.get("summary", ""))
            link = entry.get("link", "")
            candidates.append((ts, title, excerpt, link))

    if not candidates:
        print("هیچ خبر جدیدی (در بازه ۸ ساعت اخیر) پیدا نشد.")
        return

    candidates.sort(key=lambda x: x[0])
    ts, title, excerpt, link = candidates[-1]

    try:
        full_text = fetch_bbc_article_text(link)
        if not full_text:
            # اگر اسکرپینگ صفحه شکست خورد، حداقل از خلاصه استفاده کن
            full_text = excerpt

        translated = translate_with_gemini(title, excerpt, full_text)
        fa_title = translated["title"].strip()
        fa_excerpt = translated["excerpt"].strip()
        fa_body = translated["body"].strip()

        message = build_message(fa_title, fa_excerpt, fa_body, source_name, link)
        send_to_telegram(message)
        print(f"پست شد: {title}")
        state["last_posted_ts"] = ts
        save_state(state)
    except Exception as e:
        print(f"خطا در پردازش/ارسال خبر: {e}")


if __name__ == "__main__":
    main()
