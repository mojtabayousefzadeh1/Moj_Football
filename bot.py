import os
import json
import re
import time
import feedparser
import requests

# ---------- تنظیمات از Secrets ----------
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"

POSTED_FILE = "posted.json"
SLEEP_BETWEEN_POSTS = 13 * 60  # 13 دقیقه

# ---------- منابع خبری ----------
FEED_SLOTS = [
    {"key": "iran", "url": "https://www.varzesh3.com/rss/domesticfootball", "count": 1, "label": "🇮🇷 ایران", "needs_translation": False},
    {"key": "bbc", "url": "https://feeds.bbci.co.uk/sport/football/rss.xml", "count": 2, "label": "🌍 جهان", "needs_translation": True},
    {"key": "sky", "url": "https://www.skysports.com/rss/12040", "count": 1, "label": "🌍 جهان", "needs_translation": True},
    {"key": "goal", "url": "https://www.goal.com/en/feeds/news?fmt=rss", "count": 1, "label": "🌍 جهان", "needs_translation": True},
]

# ---------- لیست‌های اهمیت‌سنجی ----------
IRAN_TEAMS = {
    "تیم ملی": 6, "ملی‌پوشان": 6, "تیم ملی ایران": 6,
    "استقلال": 5,
    "پرسپولیس": 4,
    "سپاهان": 3,
    "تراکتور": 2,
    "فولاد": 1, "ذوب آهن": 1, "ملوان": 1, "آلومینیوم اراک": 1,
    "نساجی": 1, "گل گهر": 1, "مس رفسنجان": 1, "صنعت نفت": 1,
    "شمس آذر": 1, "چادرملو": 1, "خیبر": 1, "استقلال خوزستان": 1,
    "فجر سپاسی": 1, "پیکان": 1, "هوادار": 1,
}

IRAN_PLAYERS = {
    "طارمی": 5, "مهدی طارمی": 5,
    "آزمون": 5, "سردار آزمون": 5,
    "جهانبخش": 4, "علیرضا جهانبخش": 4,
    "رضاییان": 3, "رامین رضاییان": 3,
    "حسین‌زاده": 3, "امیرحسین حسین‌زاده": 3,
    "غفوری": 3, "وریا غفوری": 3,
    "قلی‌زاده": 3, "علی قلی‌زاده": 3,
    "قدوس": 3, "سامان قدوس": 3,
    "بیرانوند": 3, "علیرضا بیرانوند": 3,
    "کنعانی‌زادگان": 2, "حسین کنعانی‌زادگان": 2,
    "محرمی": 2, "صادق محرمی": 2,
    "میلاد محمدی": 2,
    "نورالهی": 2, "احمد نورالهی": 2,
    "قائدی": 2, "مهدی قائدی": 2,
}

IRAN_COACHES = {
    "قلعه‌نویی": 5, "امیر قلعه‌نویی": 5,
    "مجیدی": 4, "فرهاد مجیدی": 4,
    "گل‌محمدی": 4, "یحیی گل‌محمدی": 4,
    "تارتار": 3,
    "بختیاری‌زاده": 3,
    "سرمربی سپاهان": 2,
    "سرمربی تراکتور": 2,
}

FOREIGN_TEAMS = {
    "Barcelona": 3, "Real Madrid": 3, "Arsenal": 3, "Manchester City": 3,
    "Man City": 3, "Manchester United": 3, "Man United": 3, "Man Utd": 3,
    "Liverpool": 3, "Chelsea": 3, "Paris Saint-Germain": 3, "PSG": 3,
    "Bayern Munich": 3, "Bayern": 3, "Borussia Dortmund": 3, "Dortmund": 3,
    "Juventus": 3, "Inter Milan": 3, "Inter": 3, "AC Milan": 3,
    "AS Roma": 3, "Roma": 3, "Napoli": 3,
}

FOREIGN_PLAYERS = {
    "Messi": 4, "Ronaldo": 4, "Mbappe": 4, "Mbappé": 4, "Haaland": 4,
    "Vinicius": 4, "Vinícius": 4, "Bellingham": 4, "Harry Kane": 4,
    "Kane": 3, "Salah": 4, "Lamine Yamal": 4, "Yamal": 4,
    "Neymar": 3, "De Bruyne": 3, "Modric": 3, "Modrić": 3,
    "Griezmann": 3, "Kylian Mbappe": 4,
}

NATIONAL_TEAMS = {
    "Germany": 2, "France": 2, "Argentina": 2, "Brazil": 2,
    "Italy": 2, "Spain": 2, "England": 2, "Portugal": 2,
    "Netherlands": 2, "Belgium": 2,
}


def build_keyword_dict(category):
    if category == "iran":
        merged = {}
        merged.update(IRAN_TEAMS)
        merged.update(IRAN_PLAYERS)
        merged.update(IRAN_COACHES)
        return merged
    else:
        merged = {}
        merged.update(FOREIGN_TEAMS)
        merged.update(FOREIGN_PLAYERS)
        merged.update(NATIONAL_TEAMS)
        return merged


def score_entry(text, category):
    keywords = build_keyword_dict(category)
    best_score = 0
    text_lower = text.lower()
    for kw, weight in keywords.items():
        if kw.lower() in text_lower:
            if weight > best_score:
                best_score = weight
    return best_score


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


def rewrite_with_gemini(title, summary, needs_translation):
    if needs_translation:
        instruction = (
            "متن خبر انگلیسی زیر را به فارسی روان خلاصه و بازنویسی کن "
            "(نه ترجمه کلمه‌به‌کلمه، بلکه بازنویسی کامل با کلمات خودت، حداکثر ۴ خط)."
        )
    else:
        instruction = (
            "متن خبر فارسی زیر را بازنویسی و خلاصه کن (کپی مستقیم نکن، با جملات خودت "
            "دوباره بنویس، حداکثر ۴ خط)."
        )

    prompt = f"""شما یک دستیار خبرنگار ورزشی فارسی‌زبان هستید.
{instruction}
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


def pick_best_entries(feed_url, category, posted, count):
    try:
        feed = feedparser.parse(feed_url)
        source_name = feed.feed.get("title", feed_url)
    except Exception as e:
        print(f"خطا در خواندن فید {feed_url}: {e}")
        return [], feed_url

    candidates = []
    for entry in feed.entries:
        uid = entry.get("id", entry.get("link"))
        if uid in posted:
            continue
        title = entry.get("title", "")
        summary = clean_html(entry.get("summary", ""))
        score = score_entry(title + " " + summary, category)
        if score > 0:
            candidates.append((score, uid, title, summary, entry.get("link", "")))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[:count], source_name


def main():
    posted = load_posted()
    new_posted = set(posted)
    posts_sent = 0

    for slot in FEED_SLOTS:
        selected, source_name = pick_best_entries(
            slot["url"], slot["key"], posted, slot["count"]
        )

        if not selected:
            print(f"[{slot['key']}] خبر مهمی برای پست کردن پیدا نشد.")
            continue

        for score, uid, title, summary, link in selected:
            try:
                rewritten = rewrite_with_gemini(
                    title, summary, slot["needs_translation"]
                )
                message = (
                    f"{slot['label']}\n\n{rewritten}\n\n"
                    f"📰 منبع: {source_name}\n🔗 {link}"
                )
                send_to_telegram(message)
                print(f"پست شد (امتیاز {score}): {title}")
                new_posted.add(uid)
                posts_sent += 1
                save_posted(new_posted)
                time.sleep(SLEEP_BETWEEN_POSTS)
            except Exception as e:
                print(f"خطا در پردازش/ارسال خبر: {e}")

    save_posted(new_posted)
    print(f"مجموع پست‌های ارسال‌شده در این اجرا: {posts_sent}")


if __name__ == "__main__":
    main()
