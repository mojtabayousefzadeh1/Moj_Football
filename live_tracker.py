import os
import json
import requests
from datetime import datetime, timezone

API_KEY = os.environ["API_FOOTBALL_KEY"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]

STATE_FILE = "state_live.json"
LIVE_URL = "https://v3.football.api-sports.io/fixtures?live=all"
HEADERS = {"x-apisports-key": API_KEY}

WINDOW_START_UTC_MIN = 10 * 60 + 30
WINDOW_END_UTC_MIN = 22 * 60 + 30

LEAGUES = {
    696: "پریمیرلیگ انگلیس",
    45: "جام حذفی انگلیس (FA Cup)",
    48: "جام اتحادیه انگلیس (EFL Cup)",
    140: "لالیگا اسپانیا",
    143: "کوپا دل‌ری",
    556: "سوپرکاپ اسپانیا",
    61: "لیگ ۱ فرانسه",
    66: "کوپ دو فرانس",
    135: "سری‌آ ایتالیا",
    137: "کوپا ایتالیا",
    78: "بوندسلیگا آلمان",
    715: "یوپوکال آلمان (DFB Pokal)",
    91: "اردیویزی هلند",
    94: "پریمیرا لیگا پرتغال",
    307: "لیگ عربستان",
    826: "سوپرکاپ عربستان",
    290: "لیگ برتر ایران",
    291: "لیگ دسته اول ایران (آزادگان)",
    495: "جام حذفی ایران",
    905: "سوپرکاپ ایران",
    2: "لیگ قهرمانان اروپا",
    3: "لیگ اروپا",
    848: "لیگ کنفرانس اروپا",
    17: "لیگ قهرمانان آسیا (نخبگان)",
    18: "لیگ قهرمانان آسیا ۲",
    1: "جام جهانی",
    15: "جام باشگاه‌های جهان",
    4: "یورو",
    7: "جام ملت‌های آسیا",
    9: "کوپا آمه‌ریکا",
    6: "جام ملت‌های آفریقا",
    5: "لیگ ملت‌های اروپا",
    30: "انتخابی جام جهانی - آسیا",
    31: "انتخابی جام جهانی - کونکاکاف",
    29: "انتخابی جام جهانی - آفریقا",
    32: "انتخابی جام جهانی - اروپا",
    34: "انتخابی جام جهانی - آمریکای جنوبی",
}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_telegram(text, reply_to=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHANNEL_ID, "text": text, "parse_mode": "HTML"}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["result"]["message_id"]


def get_fixture_state(state, fixture_id):
    key = str(fixture_id)
    if key not in state:
        state[key] = {
            "last_message_id": None,
            "kickoff_posted": False,
            "fulltime_posted": False,
            "posted_events": [],
        }
    return state[key]


def match_label(home, away, league_name):
    return f"⚽ {home} - {away}\n🏆 {league_name}"


def process_fixture(item, state, league_name):
    fixture_id = item["fixture"]["id"]
    status_short = item["fixture"]["status"]["short"]
    home = item["teams"]["home"]["name"]
    away = item["teams"]["away"]["name"]

    fstate = get_fixture_state(state, fixture_id)

    if status_short in ("1H", "LIVE") and not fstate["kickoff_posted"]:
        text = f"🟢 شروع بازی\n{match_label(home, away, league_name)}"
        msg_id = send_telegram(text)
        fstate["last_message_id"] = msg_id
        fstate["kickoff_posted"] = True

    for ev in item.get("events", []):
        ev_type = ev.get("type")
        ev_detail = ev.get("detail", "")
        minute = ev.get("time", {}).get("elapsed")
        extra = ev.get("time", {}).get("extra")
        player = ev.get("player", {}).get("name", "")
        team_name = ev.get("team", {}).get("name", "")

        ev_key = f"{ev_type}-{ev_detail}-{minute}-{extra}-{player}-{team_name}"
        if ev_key in fstate["posted_events"]:
            continue

        minute_str = f"{minute}'" + (f"+{extra}" if extra else "")
        text = None

        if ev_type == "Goal" and ev_detail == "Missed Penalty":
            text = f"❌ پنالتی از دست رفته ({minute_str})\n{team_name} - {player}\n\n{match_label(home, away, league_name)}"
        elif ev_type == "Goal":
            text = f"⚽ گل! ({minute_str})\n{team_name} - {player}\n\n{match_label(home, away, league_name)}"
        elif ev_type == "Card" and ev_detail in ("Red Card", "Second Yellow card"):
            text = f"🟥 اخراج ({minute_str})\n{team_name} - {player}\n\n{match_label(home, away, league_name)}"
        elif ev_type == "Var":
            text = f"📺 تصمیم VAR ({minute_str})\n{ev_detail}\n\n{match_label(home, away, league_name)}"

        if text:
            msg_id = send_telegram(text, reply_to=fstate["last_message_id"])
            fstate["last_message_id"] = msg_id
            fstate["posted_events"].append(ev_key)

    if status_short in ("FT", "AET", "PEN") and not fstate["fulltime_posted"]:
        home_goals = item["goals"]["home"]
        away_goals = item["goals"]["away"]
        text = f"🏁 پایان بازی\n{home} {home_goals} - {away_goals} {away}"
        msg_id = send_telegram(text, reply_to=fstate["last_message_id"])
        fstate["last_message_id"] = msg_id
        fstate["fulltime_posted"] = True


def main():
    now_utc = datetime.now(timezone.utc)
    minutes_now = now_utc.hour * 60 + now_utc.minute

    if not (WINDOW_START_UTC_MIN <= minutes_now <= WINDOW_END_UTC_MIN):
        print("خارج از بازه فعال (۱۴:۰۰ تا ۰۲:۰۰ به وقت ایران)؛ درخواستی ارسال نشد.")
        return

    resp = requests.get(LIVE_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("response", [])

    state = load_state()
    processed_count = 0

    for item in data:
        league_id = item.get("league", {}).get("id")
        if league_id not in LEAGUES:
            continue
        try:
            process_fixture(item, state, LEAGUES[league_id])
            processed_count += 1
        except Exception as e:
            fixture_id = item.get("fixture", {}).get("id", "?")
            print(f"خطا در پردازش بازی {fixture_id}: {e}")
            continue

    save_state(state)
    print(f"تعداد بازی‌های پردازش‌شده در این اجرا: {processed_count}")


if __name__ == "__main__":
    main()
