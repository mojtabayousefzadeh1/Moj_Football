import os
import re
import json
import time
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]

SOURCE_CHANNEL = "ft360_ir"
PREVIEW_URL = f"https://t.me/s/{SOURCE_CHANNEL}"
STATE_FILE = "state_ft360.json"
DELAY_BETWEEN_POSTS = 2 * 60
SOURCE_TAG = "@Ft360_ir"
CHANNEL_TAG = "@moj_football"

# برای حذف اشاره‌ی خودشون از انتهای متن (با یا بدون @ و با حروف بزرگ/کوچک مختلف)
TRAILING_MENTION_RE = re.compile(r"(\s*@?Ft360_ir\s*)+$", re.IGNORECASE)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_post_id": None}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def clean_trailing_mention(text):
    return TRAILING_MENTION_RE.sub("", text).strip()


def fetch_posts():
    resp = requests.get(PREVIEW_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    html = resp.text

    raw_messages = re.split(
        r'(?=<div class="tgme_widget_message[^"]*" data-post="' + SOURCE_CHANNEL + r'/\d+")',
        html,
    )

    posts = []
    for block in raw_messages:
        id_match = re.search(r'data-post="' + SOURCE_CHANNEL + r'/(\d+)"', block)
        if not id_match:
            continue
        post_id = int(id_match.group(1))

        text_match = re.search(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL
        )
        text = ""
        if text_match:
            raw_text = text_match.group(1)
            raw_text = re.sub(r"<br\s*/?>", "\n", raw_text)
            text = re.sub(r"<.*?>", "", raw_text).strip()
            text = (
                text.replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", '"')
                .replace("&#39;", "'")
            )
            text = clean_trailing_mention(text)

        # تلاش برای پیدا کردن عکس (چند الگوی مختلف امتحان می‌شود)
        photo_url = None
        photo_patterns = [
            r'tgme_widget_message_photo_wrap"[^>]*style="[^"]*background-image:url\(\'([^\']+)\'\)',
            r"class=\"tgme_widget_message_photo_wrap[^\"]*\"[^>]*background-image:url\('([^']+)'\)",
        ]
        for pattern in photo_patterns:
            m = re.search(pattern, block)
            if m:
                photo_url = m.group(1)
                break

        # اگر عکس نبود، شاید ویدیو باشد؛ تامبنیل ویدیو را به‌جای عکس می‌گیریم
        if not photo_url:
            video_match = re.search(
                r'tgme_widget_message_video_thumb"[^>]*style="[^"]*background-image:url\(\'([^\']+)\'\)',
                block,
            )
            if video_match:
                photo_url = video_match.group(1)

        posts.append({"id": post_id, "text": text, "photo": photo_url})

    posts.sort(key=lambda p: p["id"])
    return posts


def send_text(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHANNEL_ID, "text": text, "parse_mode": "HTML"}
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()


def send_photo(photo_url, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": CHANNEL_ID, "photo": photo_url, "caption": caption[:1024], "parse_mode": "HTML"}
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()


def main():
    state = load_state()
    last_post_id = state.get("last_post_id")

    posts = fetch_posts()
    if not posts:
        print("هیچ پستی پیدا نشد (احتمالاً مشکل در خواندن صفحه).")
        return

    if last_post_id is None:
        state["last_post_id"] = posts[-1]["id"]
        save_state(state)
        print("اولین اجرا؛ فقط نقطه شروع ثبت شد، پستی ارسال نشد.")
        return

    new_posts = [p for p in posts if p["id"] > last_post_id]

    if not new_posts:
        print("پست جدیدی وجود ندارد.")
        return

    newest_id = last_post_id
    for i, post in enumerate(new_posts):
        if not post["text"] and not post["photo"]:
            newest_id = max(newest_id, post["id"])
            continue
        try:
            full_text = (
                f"{post['text']}\n\n"
                f"{CHANNEL_TAG}\n\n"
                f"📰 منبع: {SOURCE_TAG}"
            )

            if post["photo"]:
                send_photo(post["photo"], full_text)
            else:
                send_text(full_text)

            print(f"پست شد: {post['id']} | عکس: {'بله' if post['photo'] else 'خیر'}")
            newest_id = max(newest_id, post["id"])
            if i < len(new_posts) - 1:
                time.sleep(DELAY_BETWEEN_POSTS)
        except Exception as e:
            print(f"خطا در ارسال پست {post['id']}: {e}")

    state["last_post_id"] = newest_id
    save_state(state)


if __name__ == "__main__":
    main()
