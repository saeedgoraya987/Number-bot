"""
Earning Hub Number Bot - Python Version
All features: Numbers, WhatsApp Check, OTP, Earnings, Withdraw, 2FA, TempMail, Admin
"""

import os
import json
import re
import time
import asyncio
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pyotp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

# ─── Logging ───
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ─── Configuration ───
BOT_TOKEN = "8672122739:AAGXzye3H-78dPMswDLCzMLkkoimcDCqihY"
ADMIN_PASSWORD = "sadhin8miya61458"

MAIN_CHANNEL     = "@earning_hub_official_channel"
MAIN_CHANNEL_URL = "https://t.me/earning_hub_official_channel"
MAIN_CHANNEL_ID  = -1003543718769
CHAT_GROUP       = "https://t.me/earning_hub_number_channel"
CHAT_GROUP_ID    = -1003875142184
OTP_GROUP        = "https://t.me/EarningHub_otp"
OTP_GROUP_ID     = -1003247504066

# ─── Green API (WhatsApp) ───
GREEN_API_URL   = "https://7107.api.greenapi.com"
GREEN_INSTANCE  = "7107585194"
GREEN_TOKEN     = "97f3ace72a9642adb3f1543ddc04da00d86aecf5f57945508f"

# ─── Data Directory ───
DATA_DIR = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", os.path.dirname(os.path.abspath(__file__)))
logger.info(f"📁 Data Directory: {DATA_DIR}")

# ─── File Paths ───
NUMBERS_FILE       = os.path.join(DATA_DIR, "numbers.txt")
COUNTRIES_FILE     = os.path.join(DATA_DIR, "countries.json")
USERS_FILE         = os.path.join(DATA_DIR, "users.json")
SERVICES_FILE      = os.path.join(DATA_DIR, "services.json")
ACTIVE_NUMBERS_FILE= os.path.join(DATA_DIR, "active_numbers.json")
OTP_LOG_FILE       = os.path.join(DATA_DIR, "otp_log.json")
ADMINS_FILE        = os.path.join(DATA_DIR, "admins.json")
SETTINGS_FILE      = os.path.join(DATA_DIR, "settings.json")
TOTP_SECRETS_FILE  = os.path.join(DATA_DIR, "totp_secrets.json")
TEMP_MAILS_FILE    = os.path.join(DATA_DIR, "temp_mails.json")
EARNINGS_FILE      = os.path.join(DATA_DIR, "earnings.json")
WITHDRAW_FILE      = os.path.join(DATA_DIR, "withdrawals.json")
COUNTRY_PRICES_FILE= os.path.join(DATA_DIR, "country_prices.json")
WA_OWNER_FILE      = os.path.join(DATA_DIR, "wa_owner.json")

# ─── Default Settings ───
DEFAULT_SETTINGS = {
    "defaultNumberCount": 10,
    "cooldownSeconds": 5,
    "requireVerification": True,
    "minWithdraw": 50,
    "defaultOtpPrice": 0.25,
    "withdrawMethods": ["bKash", "Nagad"],
    "withdrawEnabled": True
}

# ─── Load/Save Helpers ───
def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
    return default

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving {path}: {e}")

# ─── Load Data ───
settings       = load_json(SETTINGS_FILE, DEFAULT_SETTINGS)
users          = load_json(USERS_FILE, {})
active_numbers = load_json(ACTIVE_NUMBERS_FILE, {})
otp_log        = load_json(OTP_LOG_FILE, [])
admins         = load_json(ADMINS_FILE, [])
totp_secrets   = load_json(TOTP_SECRETS_FILE, {})
temp_mails     = load_json(TEMP_MAILS_FILE, {})
earnings       = load_json(EARNINGS_FILE, {})
withdrawals    = load_json(WITHDRAW_FILE, [])
country_prices = load_json(COUNTRY_PRICES_FILE, {})
wa_sessions    = {}  # { user_id: { connected: bool } }

countries = load_json(COUNTRIES_FILE, {
    "880": {"name": "Bangladesh", "flag": "🇧🇩"},
    "91":  {"name": "India",      "flag": "🇮🇳"},
    "92":  {"name": "Pakistan",   "flag": "🇵🇰"},
    "1":   {"name": "USA",        "flag": "🇺🇸"},
    "44":  {"name": "UK",         "flag": "🇬🇧"},
    "977": {"name": "Nepal",      "flag": "🇳🇵"},
})

services = load_json(SERVICES_FILE, {
    "whatsapp":    {"name": "WhatsApp",    "icon": "📱"},
    "telegram":    {"name": "Telegram",    "icon": "✈️"},
    "facebook":    {"name": "Facebook",    "icon": "📘"},
    "instagram":   {"name": "Instagram",   "icon": "📸"},
    "google":      {"name": "Google",      "icon": "🔍"},
    "verification":{"name": "Verification","icon": "✅"},
    "other":       {"name": "Other",       "icon": "🔧"},
})

numbers_by_cs = {}  # { country_code: { service: [numbers] } }

def load_numbers():
    global numbers_by_cs
    numbers_by_cs = {}
    if not os.path.exists(NUMBERS_FILE):
        return
    try:
        with open(NUMBERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if "|" in line:
                    parts = line.split("|")
                    if len(parts) >= 3:
                        num, cc, svc = parts[0].strip(), parts[1].strip(), parts[2].strip()
                    elif len(parts) == 2:
                        num, cc, svc = parts[0].strip(), parts[1].strip(), "other"
                    else:
                        continue
                else:
                    num = line
                    cc  = get_country_code_from_number(num)
                    svc = "other"
                if not re.match(r"^\d{10,15}$", num):
                    continue
                if not cc:
                    continue
                numbers_by_cs.setdefault(cc, {}).setdefault(svc, [])
                if num not in numbers_by_cs[cc][svc]:
                    numbers_by_cs[cc][svc].append(num)
        total = sum(len(nums) for cc in numbers_by_cs.values() for nums in cc.values())
        logger.info(f"✅ Loaded {total} numbers")
    except Exception as e:
        logger.error(f"Error loading numbers: {e}")

def save_numbers():
    try:
        lines = []
        for cc, svcs in numbers_by_cs.items():
            for svc, nums in svcs.items():
                for num in nums:
                    lines.append(f"{num}|{cc}|{svc}")
        with open(NUMBERS_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        logger.error(f"Error saving numbers: {e}")

load_numbers()

# ─── Save Functions ───
def save_settings():    save_json(SETTINGS_FILE, settings)
def save_users():       save_json(USERS_FILE, users)
def save_active():      save_json(ACTIVE_NUMBERS_FILE, active_numbers)
def save_otp_log():     save_json(OTP_LOG_FILE, otp_log[-1000:])
def save_admins():      save_json(ADMINS_FILE, admins)
def save_totp():        save_json(TOTP_SECRETS_FILE, totp_secrets)
def save_temp_mails():  save_json(TEMP_MAILS_FILE, temp_mails)
def save_earnings():    save_json(EARNINGS_FILE, earnings)
def save_withdrawals(): save_json(WITHDRAW_FILE, withdrawals)
def save_cp():          save_json(COUNTRY_PRICES_FILE, country_prices)
def save_countries():   save_json(COUNTRIES_FILE, countries)
def save_services():    save_json(SERVICES_FILE, services)

if not os.path.exists(SETTINGS_FILE):
    save_settings()
if not os.path.exists(COUNTRIES_FILE):
    save_countries()
if not os.path.exists(SERVICES_FILE):
    save_services()

# ─── Helper Functions ───
def is_admin(user_id: str) -> bool:
    return str(user_id) in admins

def get_country_code_from_number(num: str) -> str:
    s = str(num)
    for l in [3, 2, 1]:
        if s[:l] in countries:
            return s[:l]
    return ""

def get_otp_price(cc: str) -> float:
    return country_prices.get(cc, settings.get("defaultOtpPrice", 0.25))

def get_user_earnings(uid: str) -> dict:
    uid = str(uid)
    if uid not in earnings:
        earnings[uid] = {"balance": 0, "totalEarned": 0, "otpCount": 0}
    return earnings[uid]

def add_earning(uid: str, cc: str) -> float:
    uid = str(uid)
    price = get_otp_price(cc)
    e = get_user_earnings(uid)
    e["balance"]      = round(e["balance"] + price, 2)
    e["totalEarned"]  = round(e["totalEarned"] + price, 2)
    e["otpCount"]     = e.get("otpCount", 0) + 1
    save_earnings()
    return price

def get_time_ago(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        secs = int((now - dt).total_seconds())
        if secs < 60:   return f"{secs} seconds ago"
        if secs < 3600: return f"{secs // 60} minutes ago"
        if secs < 86400:return f"{secs // 3600} hours ago"
        return f"{secs // 86400} days ago"
    except:
        return "unknown"

def get_available_countries_for_service(svc: str) -> list:
    return [cc for cc, svcs in numbers_by_cs.items()
            if svc in svcs and svcs[svc] and cc in countries]

def get_multiple_numbers(cc: str, svc: str, uid: str, count: int) -> list:
    if cc not in numbers_by_cs or svc not in numbers_by_cs[cc]:
        return []
    pool = numbers_by_cs[cc][svc]
    if len(pool) < count:
        return []
    nums = pool[:count]
    numbers_by_cs[cc][svc] = pool[count:]
    now = datetime.now(timezone.utc).isoformat()
    for n in nums:
        active_numbers[n] = {
            "userId": str(uid), "countryCode": cc, "service": svc,
            "assignedAt": now, "lastOTP": None, "otpCount": 0
        }
    save_numbers()
    save_active()
    return nums

def extract_phone_from_text(text: str):
    m = re.search(r"\+?(\d{10,15})", text)
    return m.group(1) if m else None

def find_matching_active_number(text: str):
    for num in list(active_numbers.keys()):
        if num in text:
            return num
    for num in list(active_numbers.keys()):
        if num[-8:] in text:
            return num
    for num in list(active_numbers.keys()):
        if num[-6:] in text:
            return num
    for num in list(active_numbers.keys()):
        if num[-4:] in text:
            return num
    return None

def extract_otp(text: str):
    patterns = [
        r"(?:otp|code|pin|verification|verify|token)[^\d]{0,10}(\d{4,8})",
        r"(?:is|has|:)\s*(\d{4,8})\b",
        r"\b(\d{6})\b",
        r"\b(\d{4})\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m and 4 <= len(m.group(1)) <= 8:
            return m.group(1)
    return None

def generate_totp(secret: str):
    try:
        clean = secret.replace(" ", "").upper()
        totp = pyotp.TOTP(clean)
        token = totp.now()
        remaining = 30 - (int(time.time()) % 30)
        return {"token": token, "timeRemaining": remaining}
    except:
        return None

# ─── Green API (WhatsApp) Helpers ───

# ─── Green API Global State ───
# Single shared instance — একটাই WhatsApp connect থাকে
_green_state  = {"authorized": False}  # cached authorization state
_green_owner  = load_json(WA_OWNER_FILE, {"uid": None})  # bot restart এর পরেও owner মনে থাকে
_wa_pair_lock = None                   # initialized lazily

def save_green_owner():
    save_json(WA_OWNER_FILE, _green_owner)

def green_request(method: str, endpoint: str, body=None) -> dict:
    """Synchronous Green API HTTP call (thread-safe, blocking)"""
    url     = f"{GREEN_API_URL}/waInstance{GREEN_INSTANCE}/{endpoint}/{GREEN_TOKEN}"
    headers = {"Content-Type": "application/json"}
    data    = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.error(f"Green API error [{endpoint}]: {e}")
        return {}

async def green_get_state() -> str:
    """authorized / notAuthorized / blocked / sleepMode"""
    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: green_request("GET", "getStateInstance"))
    return result.get("stateInstance", "notAuthorized")

async def green_api_monitor(app):
    """
    Background task — Green API state পর্যবেক্ষণ।
    Startup এ immediately state check করে _green_state set করে।
    Logout হলে শুধু যার WhatsApp connect ছিল তাকেই notify করো।
    """
    logger.info("🟢 Green API monitor started")

    # ── Startup: current state জেনে নাও ──
    try:
        init_state = await green_get_state()
        _green_state["authorized"] = (init_state == "authorized")
        logger.info(f"🟢 Green API initial state: {init_state}")

        # যদি authorized এবং owner আছে — session restore করো
        if init_state == "authorized" and _green_owner.get("uid"):
            owner = str(_green_owner["uid"])
            wa_sessions[owner] = {"connected": True}
            logger.info(f"🔄 WA session restored for uid={owner}")
    except Exception as e:
        logger.error(f"Green API initial check error: {e}")

    while True:
        await asyncio.sleep(30)
        try:
            state    = await green_get_state()
            was_auth = _green_state.get("authorized", False)
            is_auth  = (state == "authorized")

            # ── Keepalive: authorized থাকলে session জীবিত রাখো ──
            if is_auth:
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: green_request("GET", "getStateInstance")
                    )
                    logger.debug("🟢 Green API keepalive ping sent")
                except Exception as ke:
                    logger.warning(f"Keepalive ping error: {ke}")

            if was_auth and not is_auth:
                # ── Logout detected ──
                _green_state["authorized"] = False
                owner_uid = _green_owner.get("uid")
                logger.warning(f"⚠️ Green API: WhatsApp logged out! owner={owner_uid}")

                # শুধু যার WhatsApp ছিল তাকেই notify করো
                if owner_uid:
                    wa_sessions.pop(str(owner_uid), None)
                    _green_owner["uid"] = None
                    save_green_owner()
                    try:
                        await app.bot.send_message(
                            int(owner_uid),
                            "⚠️ *WhatsApp Disconnected!*\n\n"
                            "তোমার WhatsApp থেকে bot logout হয়েছে।\n"
                            "আবার connect করতে নিচের button চাপো।",
                            parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("📱 Connect WhatsApp", callback_data="wa_connect")
                            ]])
                        )
                    except Exception as e:
                        logger.error(f"Logout notify error: {e}")
                else:
                    wa_sessions.clear()

            elif not was_auth and is_auth:
                _green_state["authorized"] = True
                logger.info("✅ Green API: WhatsApp authorized")
            elif is_auth:
                _green_state["authorized"] = True

        except Exception as e:
            logger.error(f"green_api_monitor error: {e}")

async def get_wa_pairing_code(phone: str, user_id: str) -> str:
    """
    Green API phone-number pairing code।
    Global lock: একসাথে একজনই pairing করতে পারবে।
    """
    global _wa_pair_lock
    if _wa_pair_lock is None:
        _wa_pair_lock = asyncio.Lock()

    digits = re.sub(r"\D", "", phone)
    logger.info(f"📱 Green API pairing for: +{digits}")

    async with _wa_pair_lock:
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: green_request("POST", "getAuthorizationCode", {"phoneNumber": int(digits)})
        )
        logger.info(f"Green API pairing result: {result}")
        if result.get("status") is True and result.get("code"):
            code  = str(result["code"])
            clean = re.sub(r"[^A-Z0-9]", "", code.upper())
            if len(clean) >= 8:
                return f"{clean[:4]}-{clean[4:8]}"
            return code
        raise Exception(
            result.get("message") or
            "Pairing code পাওয়া যায়নি। কিছুক্ষণ পর আবার try করো।"
        )

async def monitor_wa_connection(uid: str, context):
    """
    Pairing এর পর Green API state poll করো।
    Authorized হলে user কে notify এবং owner হিসেবে track করো।
    """
    logger.info(f"🔍 Waiting for WA auth: {uid}")
    for _ in range(60):
        await asyncio.sleep(5)
        try:
            state = await green_get_state()
            if state == "authorized":
                _green_state["authorized"] = True
                _green_owner["uid"]        = uid
                save_green_owner()
                wa_sessions[uid]           = {"connected": True}
                logger.info(f"✅ WA connected: uid={uid}")
                try:
                    await context.bot.send_message(
                        int(uid),
                        "✅ *WhatsApp Connected!*\n\n"
                        "🟢 তোমার WhatsApp সফলভাবে connect হয়েছে।\n"
                        "এখন numbers assign হলে WA check দেখাবে।\n\n"
                        "Disconnect করতে নিচের বাটন চাপো:",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔴 Logout / Disconnect", callback_data="wa_disconnect")],
                            [InlineKeyboardButton("📊 Check Status", callback_data="wa_status")],
                        ])
                    )
                except:
                    pass
                break
        except Exception as e:
            logger.warning(f"monitor_wa_connection error: {e}")

async def check_wa_number(phone: str, user_id: str):
    """
    Green API checkWhatsapp — pure HTTP request।
    Lock নেই — ১০০+ concurrent call একসাথে handle করতে পারে।
    """
    if not _green_state.get("authorized"):
        state = await green_get_state()
        if state != "authorized":
            return None
        _green_state["authorized"] = True

    digits = re.sub(r"\D", "", phone)
    loop   = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: green_request("POST", "checkWhatsapp", {"phoneNumber": int(digits)})
        )
        logger.info(f"📱 WA check +{digits}: {result}")
        exists = result.get("existsWhatsapp")
        if exists is True:  return True
        if exists is False: return False
        return None
    except Exception as e:
        logger.warning(f"check_wa_number error +{digits}: {e}")
        return None

# ─── Mail.tm API ───
def mailtm_request(method: str, path: str, body=None, token=None):
    url = f"https://api.mail.tm{path}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps(body).encode() if body else None

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())
            return err
        except:
            return None
    except Exception as e:
        logger.error(f"Mail.tm error: {e}")
        return None

def random_str(n: int, chars="abcdefghijklmnopqrstuvwxyz0123456789") -> str:
    import random
    return "".join(random.choice(chars) for _ in range(n))

async def create_fresh_email():
    try:
        domains = mailtm_request("GET", "/domains?page=1")
        domain_list = domains if isinstance(domains, list) else (domains or {}).get("hydra:member", [])
        if not domain_list:
            return None
        domain = domain_list[0]["domain"]

        username = random_str(12)
        password = random_str(16, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
        address  = f"{username}@{domain}"

        account = None
        for _ in range(3):
            account = mailtm_request("POST", "/accounts", {"address": address, "password": password})
            if account and account.get("id"):
                break
            await asyncio.sleep(3)

        if not account or not account.get("id"):
            return None

        token_res = mailtm_request("POST", "/token", {"address": address, "password": password})
        if not token_res or not token_res.get("token"):
            return None

        return {
            "address":   address,
            "sidToken":  token_res["token"],
            "provider":  "mailtm",
            "createdAt": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"createFreshEmail error: {e}")
        return None

async def get_email_inbox(email_obj: dict):
    try:
        data = mailtm_request("GET", "/messages?page=1", token=email_obj.get("sidToken"))
        msgs = data if isinstance(data, list) else (data or {}).get("hydra:member", [])
        return [{"id": m.get("id"), "from": (m.get("from") or {}).get("address", ""),
                 "subject": m.get("subject", ""), "date": m.get("createdAt", "")} for m in msgs]
    except:
        return []

async def get_email_message(msg_id: str, email_obj: dict) -> str:
    try:
        data = mailtm_request("GET", f"/messages/{msg_id}", token=email_obj.get("sidToken"))
        if not data:
            return ""
        text = data.get("text", "")
        html = (data.get("html") or [""])[0]
        raw = text or re.sub(r"<[^>]*>", " ", html)
        return re.sub(r"\s+", " ", raw).strip()
    except:
        return ""

# ─── Membership Check ───
async def check_membership(user_id: int, app) -> dict:
    result = {"mainChannel": False, "chatGroup": False, "otpGroup": False, "allJoined": False}
    try:
        m = await app.bot.get_chat_member(MAIN_CHANNEL_ID, user_id)
        result["mainChannel"] = m.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.warning(f"Main channel check: {e}")
    try:
        m = await app.bot.get_chat_member(CHAT_GROUP_ID, user_id)
        result["chatGroup"] = m.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.warning(f"Chat group check: {e}")
    try:
        m = await app.bot.get_chat_member(OTP_GROUP_ID, user_id)
        result["otpGroup"] = m.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.warning(f"OTP group check: {e}")

    result["allJoined"] = result["mainChannel"] and result["chatGroup"] and result["otpGroup"]
    return result

# ─── Keyboards ───
def main_keyboard():
    return ReplyKeyboardMarkup([
        ["☎️ Get Number", "📧 Get Tempmail"],
        ["🔐 2FA", "💰 Balances"],
        ["💸 Withdraw", "💬 Support"],
        ["ℹ️ Help"]
    ], resize_keyboard=True)

def verify_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ 📢 Main Channel", url=MAIN_CHANNEL_URL)],
        [InlineKeyboardButton("2️⃣ 💬 Number Channel", url=CHAT_GROUP)],
        [InlineKeyboardButton("3️⃣ 📨 OTP Group", url=OTP_GROUP)],
        [InlineKeyboardButton("✅ VERIFY MEMBERSHIP", callback_data="verify_user")],
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stock Report", callback_data="admin_stock"),
         InlineKeyboardButton("👥 User Stats", callback_data="admin_users")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
         InlineKeyboardButton("📋 OTP Log", callback_data="admin_otp_log")],
        [InlineKeyboardButton("➕ Add Numbers", callback_data="admin_add_numbers"),
         InlineKeyboardButton("📤 Upload File", callback_data="admin_upload")],
        [InlineKeyboardButton("🗑️ Delete Numbers", callback_data="admin_delete"),
         InlineKeyboardButton("🔧 Manage Services", callback_data="admin_manage_services")],
        [InlineKeyboardButton("🌍 Manage Countries", callback_data="admin_manage_countries"),
         InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
        [InlineKeyboardButton("💰 Country Prices", callback_data="admin_country_prices"),
         InlineKeyboardButton("💸 Withdrawals", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("👛 Balance Management", callback_data="admin_balance_manage")],
        [InlineKeyboardButton("🚪 Logout", callback_data="admin_logout")],
    ])

# ─── User Session State ───
user_sessions = {}  # { user_id: { state, data, verified, is_admin, ... } }

def get_session(uid) -> dict:
    uid = str(uid)
    if uid not in user_sessions:
        user_sessions[uid] = {
            "verified": False, "is_admin": False,
            "state": None, "data": None,
            "current_numbers": [], "current_service": None, "current_country": None,
            "last_number_time": 0, "last_verification_check": 0,
        }
    return user_sessions[uid]

# ─── Verification Middleware ───
async def ensure_verified(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    uid  = str(user.id)
    sess = get_session(uid)

    if sess["is_admin"] or is_admin(uid):
        sess["is_admin"] = True
        return True

    if not settings.get("requireVerification", True):
        return True

    now = time.time()
    RECHECK = 2 * 3600
    if sess["verified"] and (now - sess["last_verification_check"]) < RECHECK:
        return True

    membership = await check_membership(user.id, context.application)
    if membership["allJoined"]:
        sess["verified"] = True
        sess["last_verification_check"] = now
        if uid in users:
            users[uid]["verified"] = True
            save_users()
        return True

    sess["verified"] = False
    msg = (
        "⚠️ *Bot ব্যবহার করতে সকল গ্রুপে join করতে হবে!*\n\n"
        "নিচের সবগুলোতে join করুন, তারপর VERIFY চাপুন:"
    )
    if update.callback_query:
        await update.callback_query.answer("⛔ সব group এ join করো!", show_alert=True)
        try:
            await update.callback_query.edit_message_text(msg, parse_mode="Markdown", reply_markup=verify_keyboard())
        except:
            await update.effective_message.reply_text(msg, parse_mode="Markdown", reply_markup=verify_keyboard())
    else:
        await update.effective_message.reply_text(msg, parse_mode="Markdown", reply_markup=verify_keyboard())
    return False

# ─── /start ───
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        uid  = str(user.id)

        if uid not in users:
            users[uid] = {
                "id": uid, "username": user.username or "no_username",
                "first_name": user.first_name or "User",
                "last_name": user.last_name or "",
                "joined": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(),
                "verified": False,
            }
            save_users()

        sess = get_session(uid)
        sess["state"] = None
        sess["data"]  = None

        welcome = (
            f"👋 *Welcome to Earning Hub Number Bot!*\n\n"
            f"📱 Get virtual numbers for OTP verification\n"
            f"💵 Earn money from each OTP received"
        )

        # If already verified, show main keyboard directly
        if sess.get("verified") or (uid in users and users[uid].get("verified")):
            await update.message.reply_text(
                welcome + "\n\n✅ Choose an option:", 
                parse_mode="Markdown", reply_markup=main_keyboard()
            )
        else:
            await update.message.reply_text(
                welcome + "\n\nFirst, join all required groups to use the bot:",
                parse_mode="Markdown", reply_markup=verify_keyboard()
            )
    except Exception as e:
        logger.error(f"cmd_start error: {e}")
        try:
            await update.message.reply_text("⚠️ Error occurred. Please try again.")
        except:
            pass

# ─── Verify ───
async def cb_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Checking...")

    user = update.effective_user
    uid  = str(user.id)
    membership = await check_membership(user.id, context.application)

    if membership["allJoined"]:
        sess = get_session(uid)
        sess["verified"] = True
        sess["last_verification_check"] = time.time()
        # Restore admin status if applicable
        if is_admin(uid):
            sess["is_admin"] = True
        if uid in users:
            users[uid]["verified"] = True
            save_users()

        await query.edit_message_text("✅ *VERIFICATION SUCCESSFUL!*\n\nYou can now use all features.", parse_mode="Markdown")
        await context.bot.send_message(
            user.id, "🎉 Welcome! Choose an option:",
            reply_markup=main_keyboard()
        )
    else:
        msg = "❌ *VERIFICATION FAILED*\n\n"
        if not membership["mainChannel"]: msg += "❌ 1️⃣ Main Channel\n"
        if not membership["chatGroup"]:   msg += "❌ 2️⃣ Number Channel\n"
        if not membership["otpGroup"]:    msg += "❌ 3️⃣ OTP Group\n"
        msg += "\nPlease join ALL groups and click VERIFY again."
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=verify_keyboard())

# ─── Admin Login ───
async def cmd_adminlogin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split()
    if len(parts) < 2:
        return await update.message.reply_text("❌ Usage: /adminlogin [password]")

    if parts[1] == ADMIN_PASSWORD:
        uid = str(update.effective_user.id)
        sess = get_session(uid)
        sess["is_admin"] = True
        sess["state"]    = None
        sess["data"]     = None
        if uid not in admins:
            admins.append(uid)
            save_admins()
        await update.message.reply_text("✅ *Admin Login Successful!*\nUse /admin to access panel.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Wrong password.")

# ─── Admin Panel ───
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    sess = get_session(uid)
    if not sess["is_admin"] and not is_admin(uid):
        return await update.message.reply_text("❌ Use /adminlogin [password] first.")
    # Reset any leftover state
    sess["state"] = None
    sess["data"]  = None
    await update.message.reply_text("🛠 *Admin Dashboard*\n\nSelect an option:", parse_mode="Markdown", reply_markup=admin_keyboard())

# ─── GET NUMBERS ───
async def handle_get_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context):
        return
    sess = get_session(str(update.effective_user.id))
    sess["state"] = None

    avail = []
    for svc_id, svc in services.items():
        ccs = get_available_countries_for_service(svc_id)
        if ccs:
            total = sum(len(numbers_by_cs.get(cc, {}).get(svc_id, [])) for cc in ccs)
            avail.append((svc_id, svc, total))

    if not avail:
        return await update.message.reply_text("📭 *No Numbers Available*\n\nPlease try again later.", parse_mode="Markdown")

    buttons = []
    for i in range(0, len(avail), 2):
        row = []
        row.append(InlineKeyboardButton(
            f"{avail[i][1]['icon']} {avail[i][1]['name']} ({avail[i][2]})",
            callback_data=f"svc:{avail[i][0]}"
        ))
        if i+1 < len(avail):
            row.append(InlineKeyboardButton(
                f"{avail[i+1][1]['icon']} {avail[i+1][1]['name']} ({avail[i+1][2]})",
                callback_data=f"svc:{avail[i+1][0]}"
            ))
        buttons.append(row)

    await update.message.reply_text(
        "🎯 *Select a Service*\n\n_(number in brackets = available count)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def cb_select_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await ensure_verified(update, context):
        return
    await query.answer()
    svc_id = query.data.split(":", 1)[1]
    svc    = services.get(svc_id, {"name": svc_id, "icon": "📞"})
    ccs    = sorted(get_available_countries_for_service(svc_id), key=lambda cc: get_otp_price(cc))

    if not ccs:
        return await query.answer("❌ No numbers available", show_alert=True)

    buttons = []
    for i in range(0, len(ccs), 2):
        row = []
        cc1 = ccs[i]; c1 = countries[cc1]; p1 = get_otp_price(cc1)
        row.append(InlineKeyboardButton(f"{c1['flag']} {c1['name']} ({p1:.2f}TK)", callback_data=f"cc:{svc_id}:{cc1}"))
        if i+1 < len(ccs):
            cc2 = ccs[i+1]; c2 = countries[cc2]; p2 = get_otp_price(cc2)
            row.append(InlineKeyboardButton(f"{c2['flag']} {c2['name']} ({p2:.2f}TK)", callback_data=f"cc:{svc_id}:{cc2}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_services")])

    await query.edit_message_text(
        f"{svc['icon']} *{svc['name']}* — Select Country\n\n_(taka = earnings per OTP)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def cb_select_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await ensure_verified(update, context):
        return
    await query.answer()
    _, svc_id, cc = query.data.split(":")
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    count = settings.get("defaultNumberCount", 10)
    now   = time.time()

    cooldown = settings.get("cooldownSeconds", 5)
    if (now - sess["last_number_time"]) < cooldown and sess["current_numbers"]:
        remaining = int(cooldown - (now - sess["last_number_time"]))
        return await query.answer(f"⏳ {remaining} সেকেন্ড অপেক্ষা করো।", show_alert=True)

    nums = get_multiple_numbers(cc, svc_id, uid, count)
    if not nums:
        return await query.answer("❌ Not enough numbers available.", show_alert=True)

    # Release old numbers
    for old in sess["current_numbers"]:
        active_numbers.pop(old, None)
    save_active()

    sess["current_numbers"] = nums
    sess["current_service"] = svc_id
    sess["current_country"] = cc
    sess["last_number_time"] = now

    country = countries.get(cc, {"flag": "🌍", "name": cc})
    svc     = services.get(svc_id, {"icon": "📞", "name": svc_id})
    price   = get_otp_price(cc)

    # শুধু যে ইউজার WA connect করেছে সে-ই WA check পাবে
    wa_connected = _green_state.get("authorized", False) and str(_green_owner.get("uid")) == uid
    nums_text = "\n".join(
        f"{i+1}. `+{n}`" + (" ⏳" if wa_connected else "")
        for i, n in enumerate(nums)
    )

    def make_msg(nt):
        return (
            f"✅ *{len(nums)} Number(s) Assigned!*\n\n"
            f"{svc['icon']} *Service:* {svc['name']}\n"
            f"{country['flag']} *Country:* {country['name']}\n"
            f"💵 *Earnings per OTP:* {price:.2f} taka\n\n"
            f"📞 *Numbers:*\n{nt}\n\n"
            f"📌 OTP automatically আসবে।"
            + ("\n📱=WA আছে ❌=নেই" if wa_connected else "")
        )

    buttons = [
        [InlineKeyboardButton("📨 Open OTP Group", url=OTP_GROUP)],
        [InlineKeyboardButton("🔄 Get New Numbers", callback_data=f"newnum:{svc_id}:{cc}")],
        [InlineKeyboardButton("🔙 Service List", callback_data="back_services")],
    ]
    if wa_connected:
        # শুধু owner disconnect করতে পারবে
        buttons.append([InlineKeyboardButton("🔴 Disconnect WhatsApp", callback_data="wa_disconnect")])
    elif not _green_state.get("authorized", False):
        # কেউ connect না থাকলে Connect বাটন দেখাও
        buttons.append([InlineKeyboardButton("📱 Connect WhatsApp", callback_data="wa_connect")])

    await query.edit_message_text(make_msg(nums_text), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    # Background এ WA check করো — bot block হবে না
    if wa_connected:
        chat_id = query.message.chat_id
        msg_id  = query.message.message_id
        async def do_wa_check():
            # সব number একসাথে parallel check করো
            results = await asyncio.gather(
                *[check_wa_number(n, uid) for n in nums],
                return_exceptions=True
            )
            res = {n: (r if not isinstance(r, Exception) else None)
                   for n, r in zip(nums, results)}
            updated = "\n".join(
                f"{i+1}. `+{n}`" + (" 📱" if res.get(n) is True else (" ❌" if res.get(n) is False else " ⬜"))
                for i, n in enumerate(nums)
            )
            try:
                await context.bot.edit_message_text(
                    make_msg(updated), chat_id=chat_id, message_id=msg_id,
                    parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
                )
            except: pass
        asyncio.create_task(do_wa_check())

async def cb_new_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await ensure_verified(update, context):
        return
    await query.answer()
    _, svc_id, cc = query.data.split(":")
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    now  = time.time()
    cooldown = settings.get("cooldownSeconds", 5)

    if (now - sess["last_number_time"]) < cooldown:
        remaining = int(cooldown - (now - sess["last_number_time"]))
        return await query.answer(f"⏳ {remaining} সেকেন্ড অপেক্ষা করো।", show_alert=True)

    count = settings.get("defaultNumberCount", 10)
    nums  = get_multiple_numbers(cc, svc_id, uid, count)
    if not nums:
        return await query.answer("❌ No numbers available.", show_alert=True)

    for old in sess["current_numbers"]:
        active_numbers.pop(old, None)
    save_active()

    sess["current_numbers"] = nums
    sess["last_number_time"] = now

    country = countries.get(cc, {"flag": "🌍", "name": cc})
    svc     = services.get(svc_id, {"icon": "📞", "name": svc_id})
    price   = get_otp_price(cc)
    # শুধু যে ইউজার WA connect করেছে সে-ই WA check পাবে
    wa_connected = _green_state.get("authorized", False) and str(_green_owner.get("uid")) == uid

    nums_text = "\n".join(
        f"{i+1}. `+{n}`" + (" ⏳" if wa_connected else "")
        for i, n in enumerate(nums)
    )

    def make_msg_new(nt):
        return (
            f"🔄 *{len(nums)} New Number(s)!*\n\n"
            f"{svc['icon']} *Service:* {svc['name']}\n"
            f"{country['flag']} *Country:* {country['name']}\n"
            f"💵 *Earnings per OTP:* {price:.2f} taka\n\n"
            f"📞 *Numbers:*\n{nt}\n\n"
            f"📌 OTP automatically আসবে।"
            + ("\n📱=WA আছে ❌=নেই" if wa_connected else "")
        )

    buttons = [
        [InlineKeyboardButton("📨 Open OTP Group", url=OTP_GROUP)],
        [InlineKeyboardButton("🔄 Get New Numbers", callback_data=f"newnum:{svc_id}:{cc}")],
        [InlineKeyboardButton("🔙 Service List", callback_data="back_services")],
    ]
    if wa_connected:
        # শুধু owner disconnect করতে পারবে
        buttons.append([InlineKeyboardButton("🔴 Disconnect WhatsApp", callback_data="wa_disconnect")])
    elif not _green_state.get("authorized", False):
        # কেউ connect না থাকলে Connect বাটন দেখাও
        buttons.append([InlineKeyboardButton("📱 Connect WhatsApp", callback_data="wa_connect")])

    await query.edit_message_text(make_msg_new(nums_text), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    if wa_connected:
        chat_id = query.message.chat_id
        msg_id  = query.message.message_id
        async def do_wa_check_new():
            # সব number একসাথে parallel check করো
            results = await asyncio.gather(
                *[check_wa_number(n, uid) for n in nums],
                return_exceptions=True
            )
            res = {n: (r if not isinstance(r, Exception) else None)
                   for n, r in zip(nums, results)}
            updated = "\n".join(
                f"{i+1}. `+{n}`" + (" 📱" if res.get(n) is True else (" ❌" if res.get(n) is False else " ⬜"))
                for i, n in enumerate(nums)
            )
            try:
                await context.bot.edit_message_text(
                    make_msg_new(updated), chat_id=chat_id, message_id=msg_id,
                    parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
                )
            except: pass
        asyncio.create_task(do_wa_check_new())

async def cb_back_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    avail = []
    for svc_id, svc in services.items():
        ccs = get_available_countries_for_service(svc_id)
        if ccs:
            total = sum(len(numbers_by_cs.get(cc, {}).get(svc_id, [])) for cc in ccs)
            avail.append((svc_id, svc, total))

    buttons = []
    for i in range(0, len(avail), 2):
        row = []
        row.append(InlineKeyboardButton(
            f"{avail[i][1]['icon']} {avail[i][1]['name']} ({avail[i][2]})",
            callback_data=f"svc:{avail[i][0]}"
        ))
        if i+1 < len(avail):
            row.append(InlineKeyboardButton(
                f"{avail[i+1][1]['icon']} {avail[i+1][1]['name']} ({avail[i+1][2]})",
                callback_data=f"svc:{avail[i+1][0]}"
            ))
        buttons.append(row)

    await query.edit_message_text(
        "🎯 *Select a Service*\n\n_(number in brackets = available count)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ─── BALANCE ───
async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context): return
    uid = str(update.effective_user.id)
    e   = get_user_earnings(uid)
    pending = [w for w in withdrawals if w["userId"] == uid and w["status"] == "pending"]
    withdrawn = sum(w["amount"] for w in withdrawals if w["userId"] == uid and w["status"] == "approved")

    await update.message.reply_text(
        f"💰 *Your Earnings*\n\n"
        f"💵 *Current Balance:* {e['balance']:.2f} taka\n"
        f"📈 *Total Earned:* {e['totalEarned']:.2f} taka\n"
        f"📨 *Total OTPs:* {e.get('otpCount', 0)}\n"
        f"💸 *Total Withdrawn:* {withdrawn:.2f} taka\n"
        f"⏳ *Pending Withdrawals:* {len(pending)}\n\n"
        f"📌 *Minimum Withdraw:* {settings['minWithdraw']} taka",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 Withdraw", callback_data="start_withdraw")],
            [InlineKeyboardButton("📋 Withdraw History", callback_data="withdraw_history")],
        ])
    )

# ─── WITHDRAW ───
async def handle_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context): return
    uid = str(update.effective_user.id)
    e   = get_user_earnings(uid)
    sess = get_session(uid)
    sess["state"] = None

    if not settings.get("withdrawEnabled", True):
        return await update.message.reply_text("⏸️ *Withdrawals are currently disabled.*", parse_mode="Markdown")

    if e["balance"] < settings["minWithdraw"]:
        return await update.message.reply_text(
            f"❌ *Insufficient balance.*\n\n"
            f"💵 Balance: {e['balance']:.2f} taka\n"
            f"📌 Minimum: {settings['minWithdraw']} taka",
            parse_mode="Markdown"
        )

    await update.message.reply_text(
        f"💸 *Withdraw*\n\n💵 Balance: *{e['balance']:.2f} taka*\n\nChoose method:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟣 bKash", callback_data="wm:bKash"),
             InlineKeyboardButton("🟠 Nagad", callback_data="wm:Nagad")],
            [InlineKeyboardButton("❌ Cancel", callback_data="w_cancel")],
        ])
    )

async def cb_withdraw_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split(":", 1)[1]
    uid    = str(update.effective_user.id)
    sess   = get_session(uid)
    e      = get_user_earnings(uid)

    sess["state"] = "w_amount"
    sess["data"]  = {"method": method}

    amounts = []
    for a in [settings["minWithdraw"], 100, 200, 500]:
        if e["balance"] >= a and a not in amounts:
            amounts.append(a)

    rows = []
    for i in range(0, len(amounts), 2):
        row = [InlineKeyboardButton(f"{amounts[i]} taka", callback_data=f"wa:{method}:{amounts[i]}")]
        if i+1 < len(amounts):
            row.append(InlineKeyboardButton(f"{amounts[i+1]} taka", callback_data=f"wa:{method}:{amounts[i+1]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(f"💰 All ({e['balance']:.2f} taka)", callback_data=f"wa:{method}:{e['balance']:.2f}")])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="w_cancel")])

    icon = "🟣" if method == "bKash" else "🟠"
    await query.edit_message_text(
        f"{icon} *{method} Withdrawal*\n\n💵 Balance: *{e['balance']:.2f} taka*\n\nSelect amount or type in chat:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def cb_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, method, amt_str = query.data.split(":")
    amount = float(amt_str)
    uid    = str(update.effective_user.id)
    sess   = get_session(uid)
    e      = get_user_earnings(uid)

    if amount < settings["minWithdraw"]:
        return await query.answer(f"❌ Minimum {settings['minWithdraw']} taka", show_alert=True)
    if amount > e["balance"]:
        return await query.answer("❌ Insufficient balance!", show_alert=True)

    sess["state"] = "w_account"
    sess["data"]  = {"method": method, "amount": amount}
    icon = "🟣" if method == "bKash" else "🟠"

    await query.edit_message_text(
        f"{icon} *{method} — {amount:.2f} taka*\n\n📱 Your *{method} number:*\nExample: `01712345678`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="w_cancel")]])
    )

async def cb_withdraw_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    sess["state"] = None
    sess["data"]  = None
    await query.edit_message_text("❌ *Cancelled.*", parse_mode="Markdown")

async def cb_withdraw_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid   = str(update.effective_user.id)
    uwith = [w for w in withdrawals if w["userId"] == uid][-10:][::-1]

    text = "📋 *Withdraw History*\n\n"
    if not uwith:
        text += "No withdrawal requests yet."
    else:
        for w in uwith:
            icon = "✅" if w["status"] == "approved" else "❌" if w["status"] == "rejected" else "⏳"
            date = w["requestedAt"][:10]
            text += f"{icon} *{w['amount']:.2f} taka* - {w['method']}\n"
            text += f"📱 `{w['account']}` | {date}\n\n"

    await query.edit_message_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="goto_main")]]))

async def cb_start_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = str(update.effective_user.id)
    e    = get_user_earnings(uid)
    sess = get_session(uid)
    sess["state"] = None
    sess["data"]  = None

    if not settings.get("withdrawEnabled", True):
        return await query.edit_message_text("⏸️ *Withdrawals are currently disabled.*", parse_mode="Markdown")
    if e["balance"] < settings["minWithdraw"]:
        return await query.edit_message_text(
            f"❌ *Insufficient balance.*\n💵 Balance: {e['balance']:.2f} taka\n📌 Minimum: {settings['minWithdraw']} taka",
            parse_mode="Markdown"
        )

    await query.edit_message_text(
        f"💸 *Withdraw*\n\n💵 Balance: *{e['balance']:.2f} taka*\n\nChoose method:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟣 bKash", callback_data="wm:bKash"),
             InlineKeyboardButton("🟠 Nagad", callback_data="wm:Nagad")],
            [InlineKeyboardButton("❌ Cancel", callback_data="w_cancel")],
        ])
    )

# ─── WhatsApp Connect ───
async def cb_wa_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = str(update.effective_user.id)

    # যদি ইতিমধ্যে connected থাকে, logout বাটন দেখাও
    if _green_state.get("authorized"):
        owner_uid = str(_green_owner.get("uid") or "")
        if owner_uid == uid or wa_sessions.get(uid, {}).get("connected"):
            await query.edit_message_text(
                "✅ *WhatsApp Already Connected!*\n\n"
                "🟢 WhatsApp এখন active আছে।\n"
                "Disconnect করতে নিচের বাটন চাপো:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔴 Logout / Disconnect", callback_data="wa_disconnect")],
                    [InlineKeyboardButton("📊 Check Status", callback_data="wa_status")],
                ])
            )
            return

    sess = get_session(uid)
    sess["state"] = "wa_waiting_number"
    await context.bot.send_message(
        update.effective_user.id,
        "📱 WhatsApp Connect\n\nতোমার WhatsApp নম্বর দাও (country code সহ):\nExample: 8801712345678"
    )

async def cb_wa_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Checking...")
    uid   = str(update.effective_user.id)

    # Green API থেকে real-time state নাও
    try:
        state = await green_get_state()
    except:
        state = "notAuthorized"

    conn = (state == "authorized")
    if conn:
        wa_sessions[uid] = {"connected": True}
    else:
        wa_sessions.pop(uid, None)

    STATE_MAP = {
        "authorized":    "✅ *WhatsApp Connected!*\n\nNumber assign হলে 📱/❌ দেখাবে।",
        "notAuthorized": "🔴 *WhatsApp connected নেই।*\n\nCode enter করলে আবার Check Status চাপো।",
        "blocked":       "⛔ *WhatsApp instance blocked!*\n\nAdmin কে জানান।",
        "sleepMode":     "😴 *WhatsApp sleep mode এ আছে।*\n\nকিছুক্ষণ পর আবার check করো।",
    }
    text = STATE_MAP.get(state, f"❓ Unknown state: {state}")
    btns = [[InlineKeyboardButton("🔴 Disconnect", callback_data="wa_disconnect")]] if conn else \
           [[InlineKeyboardButton("📱 Connect", callback_data="wa_connect")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btns))

async def cb_wa_disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Disconnecting...")
    uid = str(update.effective_user.id)

    # Green API থেকে logout করো
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: green_request("GET", "logout"))
        logger.info(f"✅ Green API logout called for uid={uid}")
    except Exception as e:
        logger.error(f"Green API logout error: {e}")

    # Session ও state clear করো
    wa_sessions.pop(uid, None)
    _green_state["authorized"] = False
    if _green_owner.get("uid") == uid:
        _green_owner["uid"] = None
        save_green_owner()

    await query.edit_message_text(
        "🔴 *WhatsApp Disconnected!*\n\n"
        "তোমার WhatsApp সফলভাবে logout হয়েছে।\n"
        "আবার connect করতে নিচের বাটন চাপো:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 Connect WhatsApp", callback_data="wa_connect")],
        ])
    )

# ─── Temp Mail ───
async def handle_tempmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context): return
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    sess["state"] = None
    existing = temp_mails.get(uid)

    if existing:
        await update.message.reply_text(
            f"📧 *Temporary Email*\n\n📌 Your email:\n`{existing['address']}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📬 Check Inbox", callback_data="tm_inbox")],
                [InlineKeyboardButton("📋 Show Email", callback_data="tm_show")],
                [InlineKeyboardButton("🔄 Get New Email", callback_data="tm_create")],
                [InlineKeyboardButton("🗑️ Delete Email", callback_data="tm_delete")],
            ])
        )
    else:
        await update.message.reply_text(
            "📧 *Temporary Email*\n\n✅ Create a new disposable email address.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🆕 Create New Email", callback_data="tm_create")]])
        )

async def cb_tm_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Creating...")
    uid   = str(update.effective_user.id)
    loading = await context.bot.send_message(uid, "⏳ *Creating your email...*", parse_mode="Markdown")

    new_email = await create_fresh_email()
    if not new_email:
        await context.bot.edit_message_text(
            "❌ *Email creation failed.* Please try again.",
            chat_id=uid, message_id=loading.message_id,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data="tm_create")]])
        )
        return

    temp_mails[uid] = new_email
    save_temp_mails()

    await context.bot.edit_message_text(
        f"✅ *New Email Created!*\n\n📧 `{new_email['address']}`\n\n📌 Use this on any website.",
        chat_id=uid, message_id=loading.message_id,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📬 Check Inbox", callback_data="tm_inbox")],
            [InlineKeyboardButton("🔄 Get New Email", callback_data="tm_create")],
            [InlineKeyboardButton("🗑️ Delete", callback_data="tm_delete")],
        ])
    )

async def cb_tm_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📬 Loading...")
    uid = str(update.effective_user.id)

    if uid not in temp_mails:
        return await query.edit_message_text(
            "❌ No email found.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🆕 Create", callback_data="tm_create")]])
        )

    email_obj = temp_mails[uid]
    messages  = await get_email_inbox(email_obj)
    now_str   = datetime.now().strftime("%I:%M:%S %p")
    text      = f"📬 *Inbox:* `{email_obj['address']}`\n🕐 _{now_str}_\n\n"

    if not messages:
        text += "📭 *No emails yet.*"
    else:
        for msg in messages[:5]:
            text += f"━━━━━━━━━━\n📩 *From:* {msg['from']}\n📌 *Subject:* {msg['subject']}\n"
            body = await get_email_message(msg["id"], email_obj)
            if body:
                otp_m = re.findall(r"\b\d{4,8}\b", body)
                if otp_m:
                    text += f"\n🔑 *OTP:* `{otp_m[0]}`\n"
                text += f"\n📝 _{body[:250]}..._\n" if len(body) > 250 else f"\n📝 _{body}_\n"
            text += "\n"

    try:
        await query.edit_message_text(text[:4000], parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="tm_inbox")],
            [InlineKeyboardButton("🔄 New Email", callback_data="tm_create")],
            [InlineKeyboardButton("🗑️ Delete", callback_data="tm_delete")],
        ]))
    except:
        pass

async def cb_tm_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    if uid not in temp_mails:
        return await query.answer("❌ No email found", show_alert=True)
    addr = temp_mails[uid]["address"]
    await query.edit_message_text(
        f"📧 *Your Temp Email:*\n\n`{addr}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📬 Check Inbox", callback_data="tm_inbox")],
            [InlineKeyboardButton("🔄 New Email", callback_data="tm_create")],
        ])
    )

async def cb_tm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    temp_mails.pop(uid, None)
    save_temp_mails()
    await query.edit_message_text("✅ *Email deleted.*", parse_mode="Markdown")

# ─── 2FA/TOTP ───
async def handle_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context): return
    sess = get_session(str(update.effective_user.id))
    sess["state"] = None
    await update.message.reply_text(
        "🔐 *2-Step Verification Code Generator*\n\nSelect a service:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📘 Facebook 2FA", callback_data="totp:facebook")],
            [InlineKeyboardButton("📸 Instagram 2FA", callback_data="totp:instagram")],
            [InlineKeyboardButton("🔍 Google 2FA", callback_data="totp:google")],
            [InlineKeyboardButton("⚙️ Other 2FA", callback_data="totp:other")],
        ])
    )

async def cb_totp_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    svc  = query.data.split(":", 1)[1]
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    sess["state"] = "totp_waiting_secret"
    sess["data"]  = {"service": svc}

    icons = {"facebook": "📘", "instagram": "📸", "google": "🔍", "other": "⚙️"}
    names = {"facebook": "Facebook", "instagram": "Instagram", "google": "Google", "other": "Other"}
    icon  = icons.get(svc, "🔐")
    name  = names.get(svc, svc)

    await query.edit_message_text(
        f"{icon} *{name} Secret Key*\n\n"
        f"Send your Authenticator Secret Key.\n\n"
        f"🔑 It looks like: `JBSWY3DPEHPK3PXP`\n\n"
        f"Type /cancel to cancel",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="totp_back")]])
    )

async def cb_totp_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔐 *2FA Code Generator*\n\nSelect a service:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📘 Facebook 2FA", callback_data="totp:facebook")],
            [InlineKeyboardButton("📸 Instagram 2FA", callback_data="totp:instagram")],
            [InlineKeyboardButton("🔍 Google 2FA", callback_data="totp:google")],
            [InlineKeyboardButton("⚙️ Other 2FA", callback_data="totp:other")],
        ])
    )

async def cb_totp_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔄 Refreshing...")
    _, svc, secret_enc = query.data.split(":", 2)
    secret = urllib.parse.unquote(secret_enc)
    result = generate_totp(secret)

    icons = {"facebook": "📘", "instagram": "📸", "google": "🔍", "other": "⚙️"}
    names = {"facebook": "Facebook", "instagram": "Instagram", "google": "Google", "other": "2FA"}
    icon  = icons.get(svc, "🔐")
    name  = names.get(svc, svc)

    if not result:
        return await query.edit_message_text("❌ Invalid secret key.", parse_mode="Markdown")

    try:
        await query.edit_message_text(
            f"{icon} *{name} 2FA Code*\n\n"
            f"🔑 *Code:* `{result['token']}`\n\n"
            f"⏰ *{result['timeRemaining']} seconds remaining*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh Code", callback_data=f"totp_r:{svc}:{urllib.parse.quote(secret)}")],
                [InlineKeyboardButton("🔙 Back", callback_data="totp_back")],
            ])
        )
    except:
        pass

# ─── Support & Help ───
async def handle_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💬 *Support*\n\nContact admin:\n📌 @sadhin8miya",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Contact", url="https://t.me/sadhin8miya")]])
    )

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Bot Help*\n\n"
        "• ☎️ *Get Number* - Virtual number পাও\n"
        "• 📧 *Get Tempmail* - Temp email পাও\n"
        "• 🔐 *2FA* - 2-step verification code\n"
        "• 💰 *Balances* - তোমার earnings দেখো\n"
        "• 💸 *Withdraw* - Balance withdraw করো\n\n"
        f"📌 Minimum withdraw: {settings['minWithdraw']} taka\n\n"
        "Admin: /adminlogin",
        parse_mode="Markdown"
    )

# ─── Admin Callbacks ───
async def cb_admin_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    report = "📊 *Stock Report*\n\n"
    total_all = 0
    for cc, svcs in numbers_by_cs.items():
        country = countries.get(cc, {"flag": "🏴", "name": cc})
        report += f"\n{country['flag']} {country['name']} (+{cc}):\n"
        ct = 0
        for svc_id, nums in svcs.items():
            svc = services.get(svc_id, {"icon": "📞", "name": svc_id})
            if nums:
                report += f"  {svc['icon']} {svc['name']}: *{len(nums)}*\n"
                ct += len(nums)
        report += f"  *Total:* {ct}\n"
        total_all += ct

    report += f"\n📈 *Grand Total:* {total_all}\n"
    report += f"👥 *Active:* {len(active_numbers)}\n"
    report += f"📨 *OTPs:* {len(otp_log)}"

    if len(report) > 4000:
        report = report[:3950] + "\n..._truncated_"

    await query.edit_message_text(report, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_stock")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back")],
    ]))

async def cb_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    total = len(users)
    msg   = f"👥 *User Statistics*\n\n• Total: {total}\n• Active: {len(active_numbers)}\n• OTPs: {len(otp_log)}\n\n"

    recent = sorted(users.values(), key=lambda u: u.get("last_active",""), reverse=True)[:10]
    for u in recent:
        msg += f"👤 *{u.get('first_name','')}*\n🆔 `{u['id']}` | @{u.get('username','')}\n"
        msg += f"🕐 {get_time_ago(u.get('last_active', ''))}\n\n"

    if len(msg) > 4000:
        msg = msg[:3950] + "..._truncated_"

    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_users")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back")],
    ]))

async def cb_admin_otp_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    msg = "📋 *Recent OTP Logs*\n\n"
    if not otp_log:
        msg += "No OTPs yet."
    else:
        for log in otp_log[-10:][::-1]:
            msg += f"📞 `{log['phoneNumber']}` → 👤 `{log['userId']}`\n"
            msg += f"🕐 {get_time_ago(log.get('timestamp',''))}\n\n"

    await query.edit_message_text(msg[:4000], parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_otp_log")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back")],
    ]))

async def cb_admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    sess = get_session(uid)
    sess["state"] = "admin_broadcast"
    await query.edit_message_text(
        "📢 *Broadcast Message*\n\nSend the message to broadcast to all users:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
    )

async def cb_admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    await query.edit_message_text(
        f"⚙️ *Bot Settings*\n\n"
        f"📞 Number Count: *{settings['defaultNumberCount']}*\n"
        f"⏱ Cooldown: *{settings['cooldownSeconds']} seconds*\n"
        f"🔐 Verification: *{'Enabled ✅' if settings['requireVerification'] else 'Disabled ❌'}*\n"
        f"💵 OTP Price: *{settings.get('defaultOtpPrice', 0.25):.2f} taka*\n"
        f"💸 Min Withdraw: *{settings['minWithdraw']} taka*\n"
        f"🏧 Withdraw: *{'Enabled ✅' if settings['withdrawEnabled'] else 'Disabled ❌'}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 Number Count", callback_data="as_count"),
             InlineKeyboardButton("⏱ Cooldown", callback_data="as_cooldown")],
            [InlineKeyboardButton(f"🔐 Verification {'Disable' if settings['requireVerification'] else 'Enable'}", callback_data="as_toggle_verify")],
            [InlineKeyboardButton("💵 OTP Price", callback_data="as_price"),
             InlineKeyboardButton("💸 Min Withdraw", callback_data="as_minw")],
            [InlineKeyboardButton(f"🏧 Withdraw {'🔴 Disable' if settings['withdrawEnabled'] else '🟢 Enable'}", callback_data="as_toggle_withdraw")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_back")],
        ])
    )

async def cb_admin_toggle_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    settings["requireVerification"] = not settings["requireVerification"]
    save_settings()
    await query.answer(f"✅ Verification {'Enabled' if settings['requireVerification'] else 'Disabled'}")
    await cb_admin_settings(update, context)

async def cb_admin_toggle_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    settings["withdrawEnabled"] = not settings["withdrawEnabled"]
    save_settings()
    await query.answer(f"✅ Withdraw {'Enabled' if settings['withdrawEnabled'] else 'Disabled'}")
    await cb_admin_settings(update, context)

async def cb_as_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_count"
    await query.edit_message_text(
        f"📞 *Set Number Count*\n\nCurrent: *{settings['defaultNumberCount']}*\n\nSend new count (1-100):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
    )

async def cb_as_cooldown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_cooldown"
    await query.edit_message_text(
        f"⏱ *Set Cooldown*\n\nCurrent: *{settings['cooldownSeconds']} seconds*\n\nSend new cooldown (1-3600):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
    )

async def cb_as_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_price"
    await query.edit_message_text(
        f"💵 *Set Default OTP Price*\n\nCurrent: *{settings.get('defaultOtpPrice', 0.25):.2f} taka*\n\nSend new price:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
    )

async def cb_as_minw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_minw"
    await query.edit_message_text(
        f"💸 *Set Min Withdraw*\n\nCurrent: *{settings['minWithdraw']} taka*\n\nSend new minimum:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
    )

async def cb_admin_add_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_add_numbers"
    await query.edit_message_text(
        "➕ *Add Numbers*\n\nFormat:\n`[number]|[country code]|[service]`\n\nExample:\n`8801712345678|880|whatsapp`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
    )

async def cb_admin_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    pending = [w for w in withdrawals if w["status"] == "pending"]
    msg = f"💸 *Pending Withdrawals:* {len(pending)}\n\n"

    for w in pending[:10]:
        msg += f"🆔 `{w['id'][-8:]}`\n"
        msg += f"👤 {w.get('userName','')} | 💵 {w['amount']:.2f} taka\n"
        msg += f"📱 {w['method']}: `{w['account']}`\n\n"

    buttons = []
    for w in pending[:5]:
        buttons.append([
            InlineKeyboardButton(f"✅ {w['id'][-6:]}", callback_data=f"wadm_approve:{w['id']}"),
            InlineKeyboardButton(f"❌ {w['id'][-6:]}", callback_data=f"wadm_reject:{w['id']}"),
        ])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_back")])

    await query.edit_message_text(msg[:4000], parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def cb_withdraw_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    wid = query.data.split(":", 1)[1]
    for w in withdrawals:
        if w["id"] == wid:
            w["status"] = "approved"
            w["processedAt"] = datetime.now().isoformat()
            save_withdrawals()
            await query.answer("✅ Approved!")
            try:
                await context.bot.send_message(w["userId"],
                    f"✅ *Withdrawal Approved!*\n\n💵 {w['amount']:.2f} taka → {w['method']}: `{w['account']}`",
                    parse_mode="Markdown")
            except:
                pass
            break
    await cb_admin_withdrawals(update, context)

async def cb_withdraw_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    wid = query.data.split(":", 1)[1]
    for w in withdrawals:
        if w["id"] == wid:
            w["status"] = "rejected"
            w["processedAt"] = datetime.now().isoformat()
            # Refund
            e = get_user_earnings(w["userId"])
            e["balance"] = round(e["balance"] + w["amount"], 2)
            save_earnings()
            save_withdrawals()
            await query.answer("❌ Rejected!")
            try:
                await context.bot.send_message(w["userId"],
                    f"❌ *Withdrawal Rejected.*\n\n💵 {w['amount']:.2f} taka refunded.",
                    parse_mode="Markdown")
            except:
                pass
            break
    await cb_admin_withdrawals(update, context)

async def cb_admin_balance_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    await query.edit_message_text(
        "👛 *Balance Management*\n\nSelect action:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Balance", callback_data="bal_add"),
             InlineKeyboardButton("➖ Deduct Balance", callback_data="bal_deduct")],
            [InlineKeyboardButton("🔄 Reset Balance", callback_data="bal_reset")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_back")],
        ])
    )

async def cb_bal_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_add_balance"
    await query.edit_message_text(
        "➕ *Add Balance*\n\nFormat: `[userId] [amount]`\nExample: `123456789 50`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
    )

async def cb_bal_deduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_deduct_balance"
    await query.edit_message_text(
        "➖ *Deduct Balance*\n\nFormat: `[userId] [amount]`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
    )

async def cb_bal_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_reset_balance"
    await query.edit_message_text(
        "🔄 *Reset Balance*\n\nSend the userId:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
    )

async def cb_admin_country_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_country_price"
    text = "💰 *Country Prices*\n\nCurrent prices:\n"
    for cc, c in countries.items():
        p = country_prices.get(cc, settings.get("defaultOtpPrice", 0.25))
        text += f"{c['flag']} +{cc}: *{p:.2f} TK*\n"
    text += "\nSend new prices (format: `880 0.50`):"

    await query.edit_message_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]]))

async def cb_admin_manage_countries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    await query.edit_message_text(
        f"🌍 *Manage Countries*\n\nTotal: *{len(countries)}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Country", callback_data="country_add"),
             InlineKeyboardButton("📋 List Countries", callback_data="country_list")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_back")],
        ])
    )

async def cb_country_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "🌍 *Country List*\n\n"
    for cc, c in countries.items():
        p = country_prices.get(cc, settings.get("defaultOtpPrice", 0.25))
        text += f"{c['flag']} *{c['name']}* (+{cc}) — {p:.2f} TK/OTP\n"
    await query.edit_message_text(text[:4000], parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_manage_countries")]]))

async def cb_country_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = "admin_add_country"
    await query.edit_message_text(
        "🌍 *Add Country*\n\nFormat: `[code] [name] [flag]`\nExample: `880 Bangladesh 🇧🇩`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
    )

async def cb_admin_manage_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    await query.edit_message_text(
        "🔧 *Manage Services*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 List Services", callback_data="svc_list"),
             InlineKeyboardButton("➕ Add Service", callback_data="svc_add")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_back")],
        ])
    )

async def cb_svc_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "📋 *Services List*\n\n"
    for svc_id, svc in services.items():
        text += f"• {svc['icon']} *{svc['name']}* (ID: `{svc_id}`)\n"
    await query.edit_message_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_manage_services")]]))

async def cb_svc_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = "admin_add_service"
    await query.edit_message_text(
        "🔧 *Add Service*\n\nFormat: `[id] [name] [icon]`\nExample: `facebook Facebook 📘`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
    )

async def cb_admin_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    sess = get_session(uid)
    sess["state"] = "admin_upload_select_service"

    buttons = [[InlineKeyboardButton(f"{svc['icon']} {svc['name']}", callback_data=f"upload_svc:{svc_id}")]
               for svc_id, svc in services.items()]
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")])
    await query.edit_message_text("📤 *Upload Numbers*\n\nSelect service:", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons))

async def cb_upload_svc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.answer()
    svc_id = query.data.split(":", 1)[1]
    svc    = services.get(svc_id, {"name": svc_id})
    sess   = get_session(uid)
    sess["state"] = "admin_upload_file"
    sess["data"]  = {"serviceId": svc_id}
    await query.edit_message_text(
        f"📤 *Upload Numbers for {svc['name']}*\n\nSend a .txt file with numbers (one per line).",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
    )

async def cb_admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = None
    get_session(uid)["data"]  = None
    await query.edit_message_text("🛠 *Admin Dashboard*\n\nSelect an option:", parse_mode="Markdown", reply_markup=admin_keyboard())

async def cb_admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = None
    get_session(uid)["data"]  = None
    await query.edit_message_text("❌ *Cancelled.*", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛠 Back to Admin", callback_data="admin_back")]]))

async def cb_admin_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.answer()
    sess = get_session(uid)
    sess["is_admin"] = False
    sess["state"]    = None
    await query.edit_message_text("🚪 *Admin Logged Out.*", parse_mode="Markdown")

async def cb_admin_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    buttons = []
    for cc, svcs in numbers_by_cs.items():
        for svc_id, nums in svcs.items():
            if nums:
                svc = services.get(svc_id, {"icon": "📞"})
                buttons.append([InlineKeyboardButton(
                    f"🗑️ +{cc}/{svc_id} ({len(nums)})",
                    callback_data=f"del_confirm:{cc}:{svc_id}"
                )])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="admin_back")])
    await query.edit_message_text("🗑️ *Delete Numbers*\n\nSelect to delete:", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons))

async def cb_del_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    _, cc, svc_id = query.data.split(":")
    count = len(numbers_by_cs.get(cc, {}).get(svc_id, []))
    await query.edit_message_text(
        f"⚠️ *Confirm Deletion*\n\nDelete {count} numbers from +{cc}/{svc_id}?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes", callback_data=f"del_exec:{cc}:{svc_id}"),
             InlineKeyboardButton("❌ No", callback_data="admin_back")],
        ])
    )

async def cb_del_exec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    _, cc, svc_id = query.data.split(":")
    count = len(numbers_by_cs.get(cc, {}).get(svc_id, []))
    if cc in numbers_by_cs and svc_id in numbers_by_cs[cc]:
        del numbers_by_cs[cc][svc_id]
        if not numbers_by_cs[cc]:
            del numbers_by_cs[cc]
    save_numbers()
    await query.edit_message_text(f"✅ *Deleted {count} numbers.*", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]))

async def cb_goto_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✅ Done.", parse_mode="Markdown")

# ─── Document Handler (file upload) ───
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = str(update.effective_user.id)
    sess = get_session(uid)

    if sess.get("state") != "admin_upload_file":
        return

    doc = update.message.document
    if not doc.file_name.endswith(".txt"):
        return await update.message.reply_text("❌ Only .txt files are supported.")

    file = await context.bot.get_file(doc.file_id)
    content = await file.download_as_bytearray()
    lines   = content.decode("utf-8", errors="ignore").split("\n")

    svc_id = (sess.get("data") or {}).get("serviceId", "other")
    added = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            parts = line.split("|")
            num = parts[0].strip()
            cc  = parts[1].strip() if len(parts) > 1 else get_country_code_from_number(num)
            svc = parts[2].strip() if len(parts) > 2 else svc_id
        else:
            num = line
            cc  = get_country_code_from_number(num)
            svc = svc_id

        if not re.match(r"^\d{10,15}$", num) or not cc:
            continue
        numbers_by_cs.setdefault(cc, {}).setdefault(svc, [])
        if num not in numbers_by_cs[cc][svc]:
            numbers_by_cs[cc][svc].append(num)
            added += 1

    save_numbers()
    sess["state"] = None
    sess["data"]  = None
    await update.message.reply_text(f"✅ *{added} numbers uploaded successfully!*", parse_mode="Markdown")

# ─── Main Text Handler ───
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    uid  = str(user.id)
    text = update.message.text.strip()

    # Update user record
    if uid not in users:
        users[uid] = {
            "id": uid, "username": user.username or "no_username",
            "first_name": user.first_name or "User", "last_name": user.last_name or "",
            "joined": datetime.now().isoformat(), "last_active": datetime.now().isoformat(), "verified": False
        }
    users[uid]["last_active"] = datetime.now().isoformat()
    save_users()

    sess = get_session(uid)
    # Restore admin status from file if session was cleared (e.g. after restart)
    if not sess.get("is_admin") and is_admin(uid):
        sess["is_admin"] = True
    state = sess.get("state")

    # ── WhatsApp number input ──
    if state == "wa_waiting_number":
        sess["state"] = None
        phone = re.sub(r"\D", "", text)
        if len(phone) < 10 or len(phone) > 15:
            return await update.message.reply_text("❌ Invalid number. Example: `8801712345678`", parse_mode="Markdown")

        loading = await update.message.reply_text(
            "⏳ *Pairing code নিচ্ছে...*\n\n"
            "⌛ কয়েক সেকেন্ড অপেক্ষা করো।",
            parse_mode="Markdown"
        )

        async def wa_task():
            try:
                code = await get_wa_pairing_code(phone, uid)
                clean_code = re.sub(r"[^A-Z0-9]", "", code.upper())
                formatted = (clean_code[:4] + "-" + clean_code[4:8]) if len(clean_code) >= 8 else code
                try: await loading.delete()
                except: pass
                await context.bot.send_message(
                    uid,
                    f"🔑 *Pairing Code*\n\n"
                    f"`{formatted}`\n\n"
                    f"📋 *Steps:*\n"
                    f"1. WhatsApp খোলো\n"
                    f"2. Settings → Linked Devices\n"
                    f"3. Link a Device → *Link with phone number*\n"
                    f"4. উপরের code enter করো\n\n"
                    f"✅ Code enter করার পর *Check Status* চাপো।",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Check Status", callback_data="wa_status")],
                        [InlineKeyboardButton("🔄 New Code", callback_data="wa_connect")],
                    ])
                )
                asyncio.create_task(monitor_wa_connection(uid, context))
            except Exception as e:
                try: await loading.delete()
                except: pass
                logger.error(f"WA error: {e}", exc_info=True)
                await context.bot.send_message(
                    uid,
                    f"❌ *Connection failed:* {str(e)[:150]}\n\nকিছুক্ষণ পর আবার try করো।",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Try Again", callback_data="wa_connect")]])
                )

        asyncio.create_task(wa_task())
        return

    # ── TOTP secret input ──
    if state == "totp_waiting_secret":
        sess["state"] = None
        svc    = (sess.get("data") or {}).get("service", "other")
        result = generate_totp(text)
        if not result:
            return await update.message.reply_text("❌ *Invalid secret key!* Please try again.", parse_mode="Markdown")

        icons = {"facebook": "📘", "instagram": "📸", "google": "🔍", "other": "⚙️"}
        names = {"facebook": "Facebook", "instagram": "Instagram", "google": "Google", "other": "2FA"}
        icon  = icons.get(svc, "🔐")
        name  = names.get(svc, svc)

        await update.message.reply_text(
            f"{icon} *{name} 2FA Code*\n\n"
            f"🔑 *Code:* `{result['token']}`\n\n"
            f"⏰ *{result['timeRemaining']} seconds remaining*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh Code", callback_data=f"totp_r:{svc}:{urllib.parse.quote(text)}")],
                [InlineKeyboardButton("🔙 Back", callback_data="totp_back")],
            ])
        )
        return

    # ── Withdraw account input ──
    if state == "w_account":
        sess["state"] = None
        data   = sess.get("data", {})
        method = data.get("method", "bKash")
        amount = data.get("amount", 0)
        uid_e  = uid
        e      = get_user_earnings(uid_e)

        if amount > e["balance"]:
            return await update.message.reply_text("❌ Insufficient balance!")

        icon = "🟣" if method == "bKash" else "🟠"
        sess["state"] = "w_confirm"
        sess["data"]  = {"method": method, "amount": amount, "account": text}

        await update.message.reply_text(
            f"{icon} *Confirm Withdrawal*\n\n"
            f"💳 Method: {method}\n"
            f"📱 Account: `{text}`\n"
            f"💵 Amount: *{amount:.2f} taka*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirm", callback_data="w_confirm"),
                 InlineKeyboardButton("❌ Cancel", callback_data="w_cancel")],
            ])
        )
        return

    # ── Admin states ──
    if state == "admin_broadcast" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        sent = 0
        for target_uid in list(users.keys()):
            try:
                await context.bot.send_message(target_uid, text, parse_mode="Markdown")
                sent += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await update.message.reply_text(f"✅ *Broadcast sent to {sent} users.*", parse_mode="Markdown")
        return

    if state == "admin_add_numbers" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        added = 0
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                num, cc, svc = parts[0].strip(), parts[1].strip(), parts[2].strip()
            elif len(parts) == 2:
                num, cc, svc = parts[0].strip(), parts[1].strip(), "other"
            else:
                num = line
                cc  = get_country_code_from_number(num)
                svc = "other"
            if re.match(r"^\d{10,15}$", num) and cc:
                numbers_by_cs.setdefault(cc, {}).setdefault(svc, [])
                if num not in numbers_by_cs[cc][svc]:
                    numbers_by_cs[cc][svc].append(num)
                    added += 1
        save_numbers()
        await update.message.reply_text(f"✅ *{added} numbers added!*", parse_mode="Markdown")
        return

    if state == "admin_set_count" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        try:
            val = int(text)
            if 1 <= val <= 100:
                settings["defaultNumberCount"] = val
                save_settings()
                await update.message.reply_text(f"✅ *Number count set to {val}.*", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Enter 1-100.")
        except:
            await update.message.reply_text("❌ Invalid number.")
        return

    if state == "admin_set_cooldown" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        try:
            val = int(text)
            if 1 <= val <= 3600:
                settings["cooldownSeconds"] = val
                save_settings()
                await update.message.reply_text(f"✅ *Cooldown set to {val} seconds.*", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Enter 1-3600.")
        except:
            await update.message.reply_text("❌ Invalid number.")
        return

    if state == "admin_set_price" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        try:
            val = float(text)
            if val >= 0:
                settings["defaultOtpPrice"] = val
                save_settings()
                await update.message.reply_text(f"✅ *Default OTP price set to {val:.2f} taka.*", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ Invalid price.")
        return

    if state == "admin_set_minw" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        try:
            val = float(text)
            if val > 0:
                settings["minWithdraw"] = val
                save_settings()
                await update.message.reply_text(f"✅ *Min withdraw set to {val:.2f} taka.*", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ Invalid amount.")
        return

    if state == "admin_add_balance" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        parts = text.split()
        if len(parts) >= 2:
            try:
                target_id = parts[0]
                amount    = float(parts[1])
                e         = get_user_earnings(target_id)
                e["balance"] = round(e["balance"] + amount, 2)
                save_earnings()
                await update.message.reply_text(f"✅ *{amount:.2f} taka added to {target_id}.*", parse_mode="Markdown")
            except:
                await update.message.reply_text("❌ Error.")
        else:
            await update.message.reply_text("❌ Format: `[userId] [amount]`", parse_mode="Markdown")
        return

    if state == "admin_deduct_balance" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        parts = text.split()
        if len(parts) >= 2:
            try:
                target_id = parts[0]
                amount    = float(parts[1])
                e         = get_user_earnings(target_id)
                e["balance"] = max(0, round(e["balance"] - amount, 2))
                save_earnings()
                await update.message.reply_text(f"✅ *{amount:.2f} taka deducted from {target_id}.*", parse_mode="Markdown")
            except:
                await update.message.reply_text("❌ Error.")
        return

    if state == "admin_reset_balance" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        target_id = text.strip()
        e = get_user_earnings(target_id)
        e["balance"] = 0
        save_earnings()
        await update.message.reply_text(f"✅ *{target_id}'s balance reset to 0.*", parse_mode="Markdown")
        return

    if state == "admin_set_country_price" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        updated = 0
        for line in text.split("\n"):
            parts = re.split(r"[:\s]+", line.strip())
            if len(parts) >= 2:
                cc    = re.sub(r"\D", "", parts[0])
                try:
                    price = float(parts[1])
                    if cc and price >= 0:
                        country_prices[cc] = price
                        updated += 1
                except:
                    pass
        save_cp()
        await update.message.reply_text(f"✅ *{updated} prices updated!*", parse_mode="Markdown")
        return

    if state == "admin_add_country" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        parts = text.split()
        if len(parts) >= 3:
            cc   = re.sub(r"\D", "", parts[0])
            name = " ".join(parts[1:-1])
            flag = parts[-1]
            countries[cc] = {"name": name, "flag": flag}
            save_countries()
            await update.message.reply_text(f"✅ *Country added!*\n+{cc}: {flag} {name}", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Format: `[code] [name] [flag]`", parse_mode="Markdown")
        return

    if state == "admin_add_service" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        parts = text.split()
        if len(parts) >= 3:
            svc_id   = parts[0].lower()
            svc_name = " ".join(parts[1:-1])
            icon     = parts[-1]
            services[svc_id] = {"name": svc_name, "icon": icon}
            save_services()
            await update.message.reply_text(f"✅ *Service added!*\n`{svc_id}`: {icon} {svc_name}", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Format: `[id] [name] [icon]`", parse_mode="Markdown")
        return

    if state == "w_amount":
        # Try to parse amount from typed text
        try:
            amount = float(text)
            uid_e  = uid
            e      = get_user_earnings(uid_e)
            method = (sess.get("data") or {}).get("method", "bKash")

            if amount < settings["minWithdraw"]:
                return await update.message.reply_text(f"❌ Minimum {settings['minWithdraw']} taka")
            if amount > e["balance"]:
                return await update.message.reply_text("❌ Insufficient balance!")

            sess["state"] = "w_account"
            sess["data"]  = {"method": method, "amount": amount}
            icon = "🟣" if method == "bKash" else "🟠"
            await update.message.reply_text(
                f"{icon} *{method} — {amount:.2f} taka*\n\n📱 Your {method} number:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="w_cancel")]])
            )
        except:
            pass
        return

# ─── Withdraw Confirm (callback) ───
async def cb_withdraw_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    if sess.get("state") != "w_confirm":
        return

    data   = sess.get("data", {})
    method  = data.get("method")
    account = data.get("account")
    amount  = data.get("amount")
    e       = get_user_earnings(uid)

    if amount > e["balance"]:
        sess["state"] = None
        return await query.edit_message_text("❌ Balance changed. Please try again.", parse_mode="Markdown")

    e["balance"] = round(e["balance"] - amount, 2)
    save_earnings()

    wid = str(int(time.time() * 1000))
    withdrawals.append({
        "id": wid, "userId": uid,
        "userName": update.effective_user.first_name or "User",
        "userUsername": update.effective_user.username or "",
        "amount": amount, "method": method, "account": account,
        "status": "pending", "requestedAt": datetime.now().isoformat(), "processedAt": None
    })
    save_withdrawals()
    sess["state"] = None
    sess["data"]  = None

    await query.edit_message_text(
        f"✅ *Withdrawal Request Submitted!*\n\n"
        f"💳 {method}\n📱 `{account}`\n💵 {amount:.2f} taka\n\n"
        f"⏳ Admin approval pending.",
        parse_mode="Markdown"
    )

# ─── OTP Group Message Handler ───
async def handle_otp_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.message.chat_id
    if str(chat_id) != str(OTP_GROUP_ID) and chat_id != OTP_GROUP_ID:
        return

    msg_text = update.message.text or update.message.caption or ""
    msg_id   = update.message.message_id
    if not msg_text:
        return

    logger.info(f"📨 OTP Group [{msg_id}]: {msg_text[:80]}")
    matched = find_matching_active_number(msg_text)
    if not matched:
        return

    data = active_numbers[matched]
    uid  = data["userId"]
    cc   = data.get("countryCode", "")

    if data.get("lastOTP") == msg_id:
        return
    data["lastOTP"] = msg_id
    data["otpCount"] = data.get("otpCount", 0) + 1
    save_active()

    otp_code = extract_otp(msg_text)
    earned   = add_earning(uid, cc)
    balance  = get_user_earnings(uid)["balance"]
    svc      = services.get(data.get("service",""), {"icon": "📱", "name": "Service"})
    country  = countries.get(cc, {"flag": "🌍", "name": cc})

    notify = (
        f"📨 *OTP Received!*\n\n"
        f"{svc['icon']} *Service:* {svc['name']}\n"
        f"{country['flag']} *Country:* {country['name']}\n"
        f"📞 *Number:* `+{matched}`\n"
    )
    if otp_code:
        notify += f"\n🔑 *OTP Code:* `{otp_code}`\n"
    notify += f"\n💵 *+{earned:.2f} taka earned!*\n💰 *Balance: {balance:.2f} taka*"

    try:
        await context.bot.send_message(uid, notify, parse_mode="Markdown")
        await context.bot.forward_message(uid, OTP_GROUP_ID, msg_id)
    except Exception as e:
        logger.error(f"OTP notify error: {e}")

    otp_log.append({
        "phoneNumber": matched, "userId": uid, "countryCode": cc,
        "service": data.get("service"), "otpCode": otp_code, "earned": earned,
        "messageId": msg_id, "delivered": True,
        "timestamp": datetime.now().isoformat()
    })
    save_otp_log()

# ─── /cancel command ───
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    sess["state"] = None
    sess["data"]  = None
    if is_admin(uid):
        sess["is_admin"] = True
    await update.message.reply_text("✅ Cancelled.", reply_markup=main_keyboard())

# ─── Periodic scheduled check ───
async def scheduled_membership_check(app):
    while True:
        await asyncio.sleep(2 * 3600)
        if not settings.get("requireVerification", True):
            continue
        logger.info(f"🔄 [Scheduled] Checking {len(users)} users...")
        blocked = 0
        for uid, user in list(users.items()):
            try:
                membership = await check_membership(int(uid), app)
                if not membership["allJoined"]:
                    users[uid]["verified"] = False
                    blocked += 1
                    sess = get_session(uid)
                    sess["verified"] = False
                    try:
                        await app.bot.send_message(int(uid),
                            "⛔ *Access Blocked!*\n\nYou left a required group.",
                            parse_mode="Markdown", reply_markup=verify_keyboard())
                    except:
                        pass
                else:
                    users[uid]["verified"] = True
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Scheduled check error for {uid}: {e}")
        save_users()
        logger.info(f"✅ [Scheduled] {blocked} users blocked.")

# ─── Main ───
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("adminlogin", cmd_adminlogin))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # Reply keyboard handlers
    app.add_handler(MessageHandler(filters.Regex("^(☎️ Get Number|📞 Get Numbers)$"), handle_get_numbers))
    app.add_handler(MessageHandler(filters.Regex("^📧"), handle_tempmail))
    app.add_handler(MessageHandler(filters.Regex("^🔐"), handle_2fa))
    app.add_handler(MessageHandler(filters.Regex("^💰 Balances$"), handle_balance))
    app.add_handler(MessageHandler(filters.Regex("^💸 Withdraw$"), handle_withdraw))
    app.add_handler(MessageHandler(filters.Regex("^💬 Support$"), handle_support))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ Help$"), handle_help))

    # Document handler
    app.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, handle_document))

    # Callback handlers
    app.add_handler(CallbackQueryHandler(cb_verify, pattern="^verify_user$"))
    app.add_handler(CallbackQueryHandler(cb_select_service, pattern="^svc:"))
    app.add_handler(CallbackQueryHandler(cb_select_country, pattern="^cc:"))
    app.add_handler(CallbackQueryHandler(cb_new_numbers, pattern="^newnum:"))
    app.add_handler(CallbackQueryHandler(cb_back_services, pattern="^back_services$"))

    app.add_handler(CallbackQueryHandler(cb_start_withdraw, pattern="^start_withdraw$"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_method, pattern="^wm:"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_amount, pattern="^wa:"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_cancel, pattern="^w_cancel$"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_confirm, pattern="^w_confirm$"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_history, pattern="^withdraw_history$"))
    app.add_handler(CallbackQueryHandler(cb_goto_main, pattern="^goto_main$"))

    app.add_handler(CallbackQueryHandler(cb_wa_connect, pattern="^wa_connect$"))
    app.add_handler(CallbackQueryHandler(cb_wa_status, pattern="^wa_status$"))
    app.add_handler(CallbackQueryHandler(cb_wa_disconnect, pattern="^wa_disconnect$"))

    app.add_handler(CallbackQueryHandler(cb_tm_create, pattern="^tm_create$"))
    app.add_handler(CallbackQueryHandler(cb_tm_inbox, pattern="^tm_inbox$"))
    app.add_handler(CallbackQueryHandler(cb_tm_show, pattern="^tm_show$"))
    app.add_handler(CallbackQueryHandler(cb_tm_delete, pattern="^tm_delete$"))

    app.add_handler(CallbackQueryHandler(cb_totp_service, pattern="^totp:"))
    app.add_handler(CallbackQueryHandler(cb_totp_back, pattern="^totp_back$"))
    app.add_handler(CallbackQueryHandler(cb_totp_refresh, pattern="^totp_r:"))

    # Admin callbacks
    app.add_handler(CallbackQueryHandler(cb_admin_stock, pattern="^admin_stock$"))
    app.add_handler(CallbackQueryHandler(cb_admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(cb_admin_otp_log, pattern="^admin_otp_log$"))
    app.add_handler(CallbackQueryHandler(cb_admin_broadcast, pattern="^admin_broadcast$"))
    app.add_handler(CallbackQueryHandler(cb_admin_settings, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(cb_admin_toggle_verify, pattern="^as_toggle_verify$"))
    app.add_handler(CallbackQueryHandler(cb_admin_toggle_withdraw, pattern="^as_toggle_withdraw$"))
    app.add_handler(CallbackQueryHandler(cb_as_count, pattern="^as_count$"))
    app.add_handler(CallbackQueryHandler(cb_as_cooldown, pattern="^as_cooldown$"))
    app.add_handler(CallbackQueryHandler(cb_as_price, pattern="^as_price$"))
    app.add_handler(CallbackQueryHandler(cb_as_minw, pattern="^as_minw$"))
    app.add_handler(CallbackQueryHandler(cb_admin_add_numbers, pattern="^admin_add_numbers$"))
    app.add_handler(CallbackQueryHandler(cb_admin_withdrawals, pattern="^admin_withdrawals$"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_approve, pattern="^wadm_approve:"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_reject, pattern="^wadm_reject:"))
    app.add_handler(CallbackQueryHandler(cb_admin_balance_manage, pattern="^admin_balance_manage$"))
    app.add_handler(CallbackQueryHandler(cb_bal_add, pattern="^bal_add$"))
    app.add_handler(CallbackQueryHandler(cb_bal_deduct, pattern="^bal_deduct$"))
    app.add_handler(CallbackQueryHandler(cb_bal_reset, pattern="^bal_reset$"))
    app.add_handler(CallbackQueryHandler(cb_admin_country_prices, pattern="^admin_country_prices$"))
    app.add_handler(CallbackQueryHandler(cb_admin_manage_countries, pattern="^admin_manage_countries$"))
    app.add_handler(CallbackQueryHandler(cb_country_list, pattern="^country_list$"))
    app.add_handler(CallbackQueryHandler(cb_country_add, pattern="^country_add$"))
    app.add_handler(CallbackQueryHandler(cb_admin_manage_services, pattern="^admin_manage_services$"))
    app.add_handler(CallbackQueryHandler(cb_svc_list, pattern="^svc_list$"))
    app.add_handler(CallbackQueryHandler(cb_svc_add, pattern="^svc_add$"))
    app.add_handler(CallbackQueryHandler(cb_admin_upload, pattern="^admin_upload$"))
    app.add_handler(CallbackQueryHandler(cb_upload_svc, pattern="^upload_svc:"))
    app.add_handler(CallbackQueryHandler(cb_admin_delete, pattern="^admin_delete$"))
    app.add_handler(CallbackQueryHandler(cb_del_confirm, pattern="^del_confirm:"))
    app.add_handler(CallbackQueryHandler(cb_del_exec, pattern="^del_exec:"))
    app.add_handler(CallbackQueryHandler(cb_admin_back, pattern="^admin_back$"))
    app.add_handler(CallbackQueryHandler(cb_admin_cancel, pattern="^admin_cancel$"))
    app.add_handler(CallbackQueryHandler(cb_admin_logout, pattern="^admin_logout$"))

    # OTP group handler — only matches messages from the OTP group chat
    app.add_handler(MessageHandler(filters.Chat(OTP_GROUP_ID) & ~filters.COMMAND, handle_otp_group_message))
    # Private text handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_text))

    # Start scheduled tasks
    async def post_init(application):
        asyncio.create_task(scheduled_membership_check(application))
        asyncio.create_task(green_api_monitor(application))

    app.post_init = post_init

    logger.info("="*50)
    logger.info("🚀 Starting Earning Hub Bot (Python)...")
    logger.info(f"📢 Main Channel: {MAIN_CHANNEL_ID}")
    logger.info(f"💬 Chat Group: {CHAT_GROUP_ID}")
    logger.info(f"📨 OTP Group: {OTP_GROUP_ID}")
    logger.info("="*50)

    app.run_polling(allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"])

if __name__ == "__main__":
    main()
