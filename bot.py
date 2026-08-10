import asyncio
import os
import random
import re
import time

import libsql
import aiohttp
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.exceptions import TelegramRetryAfter
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_USERNAME = "MaksGeometryGd"
TURSO_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

PREMIUM_MIKU = '<tg-emoji emoji-id="5199793038410391513">🤩</tg-emoji>'
PREMIUM_MGG = '<tg-emoji emoji-id="6327920744789444368">🥰</tg-emoji>'

PREMIUM_BADGE_EVO = '<tg-emoji emoji-id="5370704514561093615">🏅</tg-emoji>'
PREMIUM_BADGE_CASE = '<tg-emoji emoji-id="5328257610472775810">🎖️</tg-emoji>'
PREMIUM_BADGE_FARM = '<tg-emoji emoji-id="5415966542078683753">🥇</tg-emoji>'
PREMIUM_BADGE_EVO5 = '<tg-emoji emoji-id="5372812377135789260">👑</tg-emoji>'

PREMIUM_DAILY_CHARM = '<tg-emoji emoji-id="5233570349148311519">🧿</tg-emoji>'

PREMIUM_MK_MGG = '<tg-emoji emoji-id="5420141555233071341">🪬</tg-emoji>'
PREMIUM_MK_SANDSMOON = '<tg-emoji emoji-id="5197260300490907908">🌔</tg-emoji>'
PREMIUM_MK_FIXSAHAL1 = '<tg-emoji emoji-id="5330393755407111028">😎</tg-emoji>'
PREMIUM_MK_MK = '<tg-emoji emoji-id="5776399733702528178">🔱</tg-emoji>'
PREMIUM_MK_PANTHER = '<tg-emoji emoji-id="5778352775591103997">🫯</tg-emoji>'
PREMIUM_MK_VECTOR = '<tg-emoji emoji-id="5233239138450312962">➰</tg-emoji>'
PREMIUM_MK_BROKEN = '<tg-emoji emoji-id="5208923808169222461">🩹</tg-emoji>'

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

REGULAR_THRESHOLDS = [10, 50, 150, 300, 500, 800, 1200, 1600, 2000, 2400,
                       3000, 3600, 4200, 4800, 5400, 6000, 6600, 7200, 7800, 8400]

CUSTOM_LEVELS = [
    (9000,  "🦵🍀", "нога удачи"),
    (9600,  "🌬️", "нога воздухана"),
    (10200, "🌔", "нога SandsMoon"),
    (10800, "🍗", "гигантская нога"),
    (11400, "✨", "блестящая нога"),
    (12000, "🥉", "бронзовая нога"),
    (12600, "🥈", "серебряная нога"),
    (13200, "🏆", "золотая нога"),
    (13800, "💎", "алмазная нога"),
    (14400, "💀", "нога смерти"),
    (15000, "😎", "нога Fixsahal1"),
    (15600, "👼", "нога ангела"),
    (16200, "🫯", "нога Panther"),
    (16800, PREMIUM_MIKU, "нога Мику"),
    (17400, "🏇", "нога героя"),
    (18000, "👁", "нога полу-бога"),
    (18600, "🌌", "космическая нога"),
    (19200, "🧿", "нога бога"),
    (19800, PREMIUM_MGG, "нога мгг"),
]

ALL_THRESHOLDS = REGULAR_THRESHOLDS + [t for t, _, _ in CUSTOM_LEVELS]
MAX_LEVEL_SCORE = ALL_THRESHOLDS[-1]

LEG_POINT = 1
LEG_LIMIT = 5
MEK_POINT = 25
MEK_LIMIT = 10

FARM_COOLDOWN = 1200
FARM_BASE = (100, 250)
FARM_EVOLVED = (700, 1250)

EXCHANGE_RATE = 200

DAILY_TABLE = [100, 250, 500, 750, 1000]
DAILY_MIN_GAP = 20 * 3600
DAILY_STREAK_LIMIT = 48 * 3600

BADGE_EVO_TOTAL = 30000

ITEMS = {
    "amulet": ("🪬", "Амулет галактики", 25, 10),
    "orb":    ("🔮", "Шар парадокса", 20, 20),
    "pill":   ("💊", "Таблетка силы", 8, 30),
    "candle": ("🪔", "Свеча солнцестояния", 6, 35),
    "gift":   ("💮", "Подарок кошко-девочки", 70, 5),
    "star":   ("⭐️", "Звезда перерождения", 50, 0),
    "daily_charm": (PREMIUM_DAILY_CHARM, "Дневной амулет", 25, 0),
    "mk_mgg":       (PREMIUM_MK_MGG, "Амулет MGG", 200, 2),
    "mk_sandsmoon": (PREMIUM_MK_SANDSMOON, "Амулет SandsMoon", 100, 8),
    "mk_fixsahal1": (PREMIUM_MK_FIXSAHAL1, "Амулет Fixsahal1", 80, 15),
    "mk_mk":        (PREMIUM_MK_MK, "Амулет Mk", 125, 5),
    "mk_panther":   (PREMIUM_MK_PANTHER, "Амулет Panther", 50, 20),
    "mk_vector":    (PREMIUM_MK_VECTOR, "Амулет Vector", 100, 10),
    "mk_broken":    (PREMIUM_MK_BROKEN, "Сломанный амулет", 20, 40),
}

ITEM_FLAT_BONUS = {
    "amulet": 1, "orb": 1, "pill": 1, "candle": 1,
    "star": 2, "gift": 3,
}

CASES = {
    1: {"name": "Базовый кейс", "price": 20, "pool": ["amulet", "orb", "pill", "candle", "gift"]},
    2: {"name": "Кейс Мк", "price": 50,
        "pool": ["mk_mgg", "mk_sandsmoon", "mk_fixsahal1", "mk_mk", "mk_panther", "mk_vector", "mk_broken"]},
}

ADMIN_GIVE_LEGS_RE = re.compile(r"^дать ног (\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_LEGS_RE = re.compile(r"^снять ноги (\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_EVO_RE = re.compile(r"^дать эво (\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_EVO_RE = re.compile(r"^снять эво (\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_COIN_RE = re.compile(r"^дать коин (\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_COIN_RE = re.compile(r"^снять коин (\d+)(\s+себе)?$", re.IGNORECASE)
EXCHANGE_RE = re.compile(r"^обменять (\d+)$", re.IGNORECASE)
CASE_NUM_RE = re.compile(r"^кейс (\d+)$", re.IGNORECASE)

NEWS_PREFIX = "новость "

FIXED_COMMANDS = {
    "моя нога", "топ ног", "гл топ ног", "топ эво", "гл топ эво", "топ коин", "гл топ коин",
    "ферма", "фарма", "инвентарь", "эволюция", "кейс", "кейсы", "бонус", "ивент ноги",
}
PREFIX_COMMANDS = (
    "обменять ", "дать ног", "снять ноги", "дать эво", "снять эво",
    "дать коин", "снять коин", "передать ", "кейс ", NEWS_PREFIX,
)


def is_command_text(text: str) -> bool:
    t = text.lower()
    if t in FIXED_COMMANDS:
        return True
    return any(t.startswith(p) for p in PREFIX_COMMANDS)


def esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_regular_visual(level: int) -> str:
    if level <= 5:
        return "🦵" * level
    idx = level - 6
    tier = idx // 5
    pos = idx % 5 + 1
    tier_emoji = ["🦵🏻", "🦵🏽", "🦿"][tier]
    prev_emoji = ["🦵", "🦵🏻", "🦵🏽"][tier]
    return tier_emoji * pos + prev_emoji * (5 - pos)


def get_level_index(score: int) -> int:
    idx = 0
    for i, threshold in enumerate(ALL_THRESHOLDS, start=1):
        if score >= threshold:
            idx = i
    return idx


def get_level_visual(score: int):
    level = get_level_index(score)
    if level == 0:
        return "🧍", "обычный безногий челик"
    if level <= 20:
        return build_regular_visual(level), f"{level} ур"
    _, emoji, name = CUSTOM_LEVELS[level - 21]
    return emoji, name


def next_level_text(score: int) -> str:
    level = get_level_index(score)
    if level >= len(ALL_THRESHOLDS):
        return "Ты достиг максимума — можно делать эволюцию 🎆"
    threshold = ALL_THRESHOLDS[level]
    return f"До {level + 1} уровня осталось {threshold - score} очков"


def get_multiplier(evolution_level: int, active_item: str) -> float:
    mult = 1.0
    if evolution_level >= 2:
        mult += 0.30
    if evolution_level >= 3:
        mult += 0.20 * (evolution_level - 2)
    if active_item and active_item in ITEMS:
        mult += ITEMS[active_item][2] / 100
    return mult


def get_badges(evolution_level: int, cases_opened: int, total_farmed: int) -> str:
    badges = ""
    if evolution_level >= 1:
        badges += PREMIUM_BADGE_EVO
    if cases_opened >= 5:
        badges += PREMIUM_BADGE_CASE
    if total_farmed >= BADGE_EVO_TOTAL:
        badges += PREMIUM_BADGE_FARM
    if evolution_level >= 5:
        badges += PREMIUM_BADGE_EVO5
    return badges


def farm_range(evolution_level: int):
    return FARM_EVOLVED if evolution_level >= 1 else FARM_BASE


def is_admin(message: Message) -> bool:
    return (message.from_user.username or "").lower() == ADMIN_USERNAME.lower()


def roll_case_item(case_num: int) -> str:
    pool = CASES[case_num]["pool"]
    weights = [ITEMS[k][3] for k in pool]
    return random.choices(pool, weights=weights, k=1)[0]


def find_item_by_name(query: str):
    q = query.strip().lower()
    for key, (_, name, _, _) in ITEMS.items():
        if name.lower() == q:
            return key
    matches = [key for key, (_, name, _, _) in ITEMS.items() if q in name.lower()]
    if len(matches) == 1:
        return matches[0]
    return None


async def resolve_target(message: Message, to_self: bool):
    if to_self:
        return message.from_user
    if message.reply_to_message:
        return message.reply_to_message.from_user
    return None


# ---------- Слой БД (Turso / libSQL) ----------

_db_lock = asyncio.Lock()
_conn = None


def _connect():
    global _conn
    if _conn is None:
        _conn = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
    return _conn


def _exec_sync(sql, params):
    conn = _connect()
    conn.execute(sql, params)
    conn.commit()


def _query_sync(sql, params):
    conn = _connect()
    cur = conn.execute(sql, params)
    return cur.fetchall()


async def db_exec(sql, params=()):
    async with _db_lock:
        await asyncio.to_thread(_exec_sync, sql, params)


async def db_query(sql, params=()):
    async with _db_lock:
        return await asyncio.to_thread(_query_sync, sql, params)


async def db_query_one(sql, params=()):
    rows = await db_query(sql, params)
    return rows[0] if rows else None


async def init_db():
    await db_exec("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            score INTEGER DEFAULT 0,
            evolution_level INTEGER DEFAULT 0,
            last_farm INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            active_item TEXT,
            cases_opened INTEGER DEFAULT 0,
            total_farmed INTEGER DEFAULT 0,
            last_bonus INTEGER DEFAULT 0,
            bonus_streak INTEGER DEFAULT 0
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS inventory (
            user_id INTEGER,
            item_key TEXT,
            qty INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, item_key)
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS chat_members (
            user_id INTEGER,
            chat_id INTEGER,
            PRIMARY KEY (user_id, chat_id)
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)


async def get_user(user_id: int):
    return await db_query_one(
        "SELECT user_id, username, score, evolution_level, last_farm, coins, active_item, "
        "cases_opened, total_farmed, last_bonus, bonus_streak FROM users WHERE user_id = ?",
        (user_id,),
    )


async def ensure_user(user_id: int, username: str):
    row = await get_user(user_id)
    if row is None:
        await db_exec("INSERT INTO users (user_id, username, score) VALUES (?, ?, 0)", (user_id, username))
        return (user_id, username, 0, 0, 0, 0, None, 0, 0, 0, 0)
    if row[1] != username:
        await db_exec("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    return row


async def get_inventory(user_id: int):
    return await db_query("SELECT item_key, qty FROM inventory WHERE user_id = ? AND qty > 0", (user_id,))


async def add_item(user_id: int, item_key: str, qty: int = 1):
    await db_exec(
        "INSERT INTO inventory (user_id, item_key, qty) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, item_key) DO UPDATE SET qty = qty + excluded.qty",
        (user_id, item_key, qty),
    )


async def remove_item(user_id: int, item_key: str, qty: int = 1) -> bool:
    row = await db_query_one("SELECT qty FROM inventory WHERE user_id = ? AND item_key = ?", (user_id, item_key))
    if not row or row[0] < qty:
        return False
    await db_exec("UPDATE inventory SET qty = ? WHERE user_id = ? AND item_key = ?", (row[0] - qty, user_id, item_key))
    return True


async def is_event_active() -> bool:
    row = await db_query_one("SELECT value FROM settings WHERE key = 'event_active'")
    return bool(row and row[0] == "1")


async def track_membership(user_id: int, chat_id: int):
    await db_exec("INSERT OR IGNORE INTO chat_members (user_id, chat_id) VALUES (?, ?)", (user_id, chat_id))


async def get_all_chat_ids():
    rows = await db_query("SELECT DISTINCT chat_id FROM chat_members")
    return [r[0] for r in rows]


async def build_top(chat_id, order_column: str, limit: int = 10):
    if chat_id is None:
        rows = await db_query(
            f"SELECT username, score, evolution_level, coins, cases_opened, total_farmed FROM users ORDER BY {order_column} DESC LIMIT ?",
            (limit,),
        )
    else:
        rows = await db_query(
            f"""SELECT u.username, u.score, u.evolution_level, u.coins, u.cases_opened, u.total_farmed
                FROM users u JOIN chat_members cm ON u.user_id = cm.user_id
                WHERE cm.chat_id = ? ORDER BY u.{order_column} DESC LIMIT ?""",
            (chat_id, limit),
        )
    return rows


def inventory_keyboard(inventory_rows, active_item: str, user_id: int) -> InlineKeyboardMarkup:
    rows = []
    for item_key, qty in inventory_rows:
        emoji, name, percent, _ = ITEMS[item_key]
        mark = " ✅" if active_item == item_key else ""
        rows.append([InlineKeyboardButton(
            text=f"{emoji} {name} (+{percent}%) x{qty}{mark}",
            callback_data=f"equip:{user_id}:{item_key}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_chat(event):
    if isinstance(event, Message):
        return event.chat
    if isinstance(event, CallbackQuery) and event.message:
        return event.message.chat
    return None


class PrivateBlockMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        chat = get_chat(event)
        if chat is not None and chat.type == "private":
            user = event.from_user
            if not (user and (user.username or "").lower() == ADMIN_USERNAME.lower()):
                return
        return await handler(event, data)


class TrackMembershipMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.chat.type in ("group", "supergroup") and event.from_user:
            await track_membership(event.from_user.id, event.chat.id)
        return await handler(event, data)


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, rate: float = 1.5):
        self.rate = rate
        self.last_call = {}

    async def __call__(self, handler, event, data):
        user_id = event.from_user.id if event.from_user else None
        if user_id is None:
            return await handler(event, data)

        text = getattr(event, "text", None)
        is_button = isinstance(event, CallbackQuery)
        if not is_button and (not text or not is_command_text(text)):
            return await handler(event, data)

        now = time.monotonic()
        key = (user_id, "cmd")
        if now - self.last_call.get(key, 0) < self.rate:
            return
        self.last_call[key] = now
        return await handler(event, data)


dp.message.middleware(PrivateBlockMiddleware())
dp.callback_query.middleware(PrivateBlockMiddleware())
dp.message.middleware(TrackMembershipMiddleware())
dp.message.middleware(ThrottleMiddleware(1.5))
dp.callback_query.middleware(ThrottleMiddleware(1.5))

LEG_REPLY_COOLDOWN = 2
_last_leg_reply = {}


@dp.errors()
async def error_handler(event, exception):
    if isinstance(exception, TelegramRetryAfter):
        await asyncio.sleep(exception.retry_after)
        return True
    print(f"Необработанная ошибка: {exception}")
    return True


@dp.message(F.text.regexp(r"[🦵🦿]"))
async def count_legs(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    text = message.text

    _, _, score, evolution_level, last_farm, coins, active_item, cases_opened, total_farmed, last_bonus, bonus_streak = await ensure_user(user_id, username)

    flat_bonus = ITEM_FLAT_BONUS.get(active_item, 0)

    legs = min(text.count("🦵"), LEG_LIMIT)
    gained = legs * (LEG_POINT + flat_bonus)

    mek = 0
    if evolution_level >= 1:
        mek = min(text.count("🦿"), MEK_LIMIT)
        gained += mek * (MEK_POINT + flat_bonus)

    if gained == 0:
        return

    mult = get_multiplier(evolution_level, active_item)
    event_mult = 2 if await is_event_active() else 1
    total = round(gained * mult * event_mult)
    new_score = score + total

    await db_exec(
        "UPDATE users SET score = ?, total_farmed = total_farmed + ? WHERE user_id = ?",
        (new_score, total, user_id),
    )

    now = time.monotonic()
    chat_id = message.chat.id
    if now - _last_leg_reply.get(chat_id, 0) < LEG_REPLY_COOLDOWN:
        return
    _last_leg_reply[chat_id] = now

    parts = f"+{legs}🦵"
    if mek:
        parts += f" +{mek}🦿"
    await message.reply(f"Лютый рофл засчитан! {parts} → +{total} очков (Всего: {new_score})")


@dp.message(F.text.lower() == "моя нога")
async def my_profile(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    _, _, score, evolution_level, last_farm, coins, active_item, cases_opened, total_farmed, last_bonus, bonus_streak = await ensure_user(user_id, username)

    emoji, name = get_level_visual(score)
    level = get_level_index(score)
    nxt = next_level_text(score)
    mult = get_multiplier(evolution_level, active_item)

    text = (
        f"👣 <b>ТВОЯ ЛЮТАЯ НОГОСТЬ:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"● Очки: <code>{score}</code> {emoji}\n"
        f"● Монеты: <code>{coins}</code> 🪙\n"
        f"● Вид ног: {emoji} {esc(name)} ({level} ур)\n"
        f"● Уровень эволюции: {evolution_level}\n"
        f"● Процентовый буст: +{round((mult - 1) * 100)}%\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"● {nxt}"
    )
    await message.reply(text)


async def send_legs_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "score")

    if not rows:
        await message.reply("В топе пока пусто, никто еще не кинул ногу... 🧍")
        return

    text = f"🏆 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed) in enumerate(rows, 1):
        emoji, name = get_level_visual(score)
        badges = get_badges(evolution_level, cases_opened, total_farmed)
        text += f"{i}. {esc(username)}{badges} — <code>{score}</code>\n   └ {emoji} {esc(name)}\n\n"

    await message.reply(text)


async def send_evo_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "evolution_level")

    if not rows:
        await message.reply("В топе пока пусто.")
        return

    text = f"🎆 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed) in enumerate(rows, 1):
        badges = get_badges(evolution_level, cases_opened, total_farmed)
        text += f"{i}. {esc(username)}{badges} — эво {evolution_level} ({score} очков)\n"

    await message.reply(text)


async def send_coin_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "coins")

    if not rows:
        await message.reply("В топе пока пусто.")
        return

    text = f"🪙 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed) in enumerate(rows, 1):
        badges = get_badges(evolution_level, cases_opened, total_farmed)
        text += f"{i}. {esc(username)}{badges} — {coins} 🪙\n"

    await message.reply(text)


@dp.message(F.text.lower() == "топ ног")
async def top_legs_local(message: Message):
    await send_legs_top(message, message.chat.id, "ТОП-10 НОГ ЭТОГО ЧАТА")


@dp.message(F.text.lower() == "гл топ ног")
async def top_legs_global(message: Message):
    await send_legs_top(message, None, "ТОП-10 НОГ ВЕЗДЕ")


@dp.message(F.text.lower() == "топ эво")
async def top_evo_local(message: Message):
    await send_evo_top(message, message.chat.id, "ТОП ЭВОЛЮЦИЙ ЭТОГО ЧАТА")


@dp.message(F.text.lower() == "гл топ эво")
async def top_evo_global(message: Message):
    await send_evo_top(message, None, "ТОП ЭВОЛЮЦИЙ ВЕЗДЕ")


@dp.message(F.text.lower() == "топ коин")
async def top_coin_local(message: Message):
    await send_coin_top(message, message.chat.id, "ТОП МОНЕТ ЭТОГО ЧАТА")


@dp.message(F.text.lower() == "гл топ коин")
async def top_coin_global(message: Message):
    await send_coin_top(message, None, "ТОП МОНЕТ ВЕЗДЕ")


@dp.message(F.text.lower().in_({"ферма", "фарма"}))
async def farm(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    now = int(time.time())

    _, _, score, evolution_level, last_farm, coins, active_item, cases_opened, total_farmed, last_bonus, bonus_streak = await ensure_user(user_id, username)

    if now - last_farm < FARM_COOLDOWN:
        left = FARM_COOLDOWN - (now - last_farm)
        m, s = divmod(left, 60)
        await message.reply(f"Ферма на кулдауне ⏳ Осталось {m} мин {s} сек")
        return

    low, high = farm_range(evolution_level)
    mult = get_multiplier(evolution_level, active_item)
    event_mult = 2 if await is_event_active() else 1
    gained = round(random.randint(low, high) * mult * event_mult)
    new_score = score + gained

    await db_exec(
        "UPDATE users SET score = ?, last_farm = ?, total_farmed = total_farmed + ? WHERE user_id = ?",
        (new_score, now, gained, user_id),
    )

    await message.reply(f"Наферметил ногу! 🦵 +{gained} очков (Всего: {new_score})")


@dp.message(F.text.lower() == "бонус")
async def daily_bonus(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    now = int(time.time())

    _, _, score, evolution_level, last_farm, coins, active_item, cases_opened, total_farmed, last_bonus, bonus_streak = await ensure_user(user_id, username)

    elapsed = now - last_bonus
    if last_bonus and elapsed < DAILY_MIN_GAP:
        left = DAILY_MIN_GAP - elapsed
        h, rem = divmod(left, 3600)
        m = rem // 60
        await message.reply(f"Бонус уже забирал сегодня ⏳ Приходи через {h} ч {m} мин")
        return

    if last_bonus and elapsed <= DAILY_STREAK_LIMIT:
        streak = bonus_streak + 1
    else:
        streak = 1

    day_index = (streak - 1) % len(DAILY_TABLE)
    reward = DAILY_TABLE[day_index]
    new_score = score + reward

    await db_exec(
        "UPDATE users SET score = ?, total_farmed = total_farmed + ?, last_bonus = ?, bonus_streak = ? WHERE user_id = ?",
        (new_score, reward, now, streak, user_id),
    )

    item_text = ""
    if day_index == len(DAILY_TABLE) - 1:
        await add_item(user_id, "daily_charm")
        item_text = f"\n{PREMIUM_DAILY_CHARM} Плюс Дневной амулет (+25% буст) в инвентарь!"

    await message.reply(f"🎁 День {streak}: +{reward} очков ноги (Всего: {new_score}){item_text}")


@dp.message(F.text.lower().startswith("обменять "))
async def exchange(message: Message):
    match = EXCHANGE_RE.match(message.text.strip().lower())
    if not match:
        await message.reply(f"Формат: обменять <количество монет>. Курс: {EXCHANGE_RATE} очков ноги = 1 монета.")
        return

    coins_wanted = int(match.group(1))
    if coins_wanted <= 0:
        await message.reply("Количество монет должно быть больше нуля.")
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, coins = row[2], row[5]

    spent = coins_wanted * EXCHANGE_RATE
    if spent > score:
        max_coins = score // EXCHANGE_RATE
        await message.reply(f"Недостаточно очков. У тебя {score}, максимум можешь обменять на {max_coins} 🪙.")
        return

    old_level = get_level_index(score)
    new_score = score - spent
    new_level = get_level_index(new_score)
    new_coins = coins + coins_wanted

    await db_exec("UPDATE users SET score = ?, coins = ? WHERE user_id = ?", (new_score, new_coins, user_id))

    warn = f"\n⚠️ Уровень упал с {old_level} до {new_level}!" if new_level < old_level else ""
    await message.reply(f"Обменял {spent} очков → +{coins_wanted} 🪙 монет (Всего монет: {new_coins}){warn}")


@dp.message(F.text.lower().startswith("передать "))
async def transfer_item(message: Message):
    if not message.reply_to_message:
        await message.reply("Ответь этой командой на сообщение того, кому передаёшь предмет.")
        return

    item_query = message.text[len("передать "):].strip()
    item_key = find_item_by_name(item_query)
    if not item_key:
        await message.reply("Не нашёл такой предмет. Проверь название (см. инвентарь).")
        return

    sender_id = message.from_user.id
    sender_username = message.from_user.username or message.from_user.first_name or "Без имени"
    receiver = message.reply_to_message.from_user
    receiver_username = receiver.username or receiver.first_name or "Без имени"

    if receiver.id == sender_id:
        await message.reply("Нельзя передать предмет самому себе.")
        return

    emoji, name, _, _ = ITEMS[item_key]

    await ensure_user(sender_id, sender_username)
    await ensure_user(receiver.id, receiver_username)

    removed = await remove_item(sender_id, item_key, 1)
    if not removed:
        await message.reply(f"У тебя нет предмета «{esc(name)}».")
        return

    sender_row = await get_user(sender_id)
    if sender_row[6] == item_key:
        remaining = await get_inventory(sender_id)
        has_more = any(k == item_key and q > 0 for k, q in remaining)
        if not has_more:
            await db_exec("UPDATE users SET active_item = NULL WHERE user_id = ?", (sender_id,))

    await add_item(receiver.id, item_key)

    await message.reply(f"{emoji} {esc(name)} передан игроку {esc(receiver_username)}!")


@dp.message(F.text.lower() == "инвентарь")
async def inventory(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    active_item = row[6]
    rows = await get_inventory(user_id)

    if not rows:
        await message.reply("🎒 Инвентарь пуст.")
        return

    kb = inventory_keyboard(rows, active_item, user_id)
    await message.reply("🎒 Твой инвентарь (можно носить максимум 1 предмет):", reply_markup=kb)


@dp.callback_query(F.data.startswith("equip:"))
async def toggle_equip(callback: CallbackQuery):
    _, owner_str, item_key = callback.data.split(":")
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer("Это не твой инвентарь!", show_alert=True)
        return

    row = await get_user(owner_id)
    active_item = row[6]
    new_active = None if active_item == item_key else item_key
    await db_exec("UPDATE users SET active_item = ? WHERE user_id = ?", (new_active, owner_id))
    rows = await get_inventory(owner_id)

    kb = inventory_keyboard(rows, new_active, owner_id)
    await callback.message.edit_text("🎒 Твой инвентарь (можно носить максимум 1 предмет):", reply_markup=kb)
    await callback.answer("Готово!")


def case_offer_keyboard(case_num: int, user_id: int) -> InlineKeyboardMarkup:
    case = CASES[case_num]
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"🎁 Купить {case['name']} ({case['price']} 🪙)", callback_data=f"buy_case:{case_num}:{user_id}")
    ]])


async def send_case_offer(message: Message, case_num: int):
    case = CASES.get(case_num)
    if not case:
        await message.reply("Такого кейса нет.")
        return
    await message.reply(f"{case['name']}. Что выпадет — решает удача!", reply_markup=case_offer_keyboard(case_num, message.from_user.id))


@dp.message(F.text.lower() == "кейс")
async def case_default(message: Message):
    await send_case_offer(message, 1)


@dp.message(F.text.lower().regexp(r"^кейс \d+$"))
async def case_numbered(message: Message):
    match = CASE_NUM_RE.match(message.text.strip().lower())
    await send_case_offer(message, int(match.group(1)))


@dp.message(F.text.lower() == "кейсы")
async def case_list(message: Message):
    user_id = message.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{case['name']} ({case['price']} 🪙)", callback_data=f"buy_case:{num}:{user_id}")]
        for num, case in CASES.items()
    ])
    await message.reply("Доступные кейсы:", reply_markup=kb)


@dp.callback_query(F.data.startswith("buy_case:"))
async def buy_case(callback: CallbackQuery):
    _, case_num_str, owner_str = callback.data.split(":")
    case_num = int(case_num_str)
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer("Это не твой кейс!", show_alert=True)
        return

    case = CASES[case_num]

    row = await get_user(owner_id)
    coins = row[5]
    if coins < case["price"]:
        await callback.answer(f"Не хватает монет. Нужно {case['price']} 🪙", show_alert=True)
        return

    item_key = roll_case_item(case_num)
    emoji, name, percent, _ = ITEMS[item_key]

    await db_exec(
        "UPDATE users SET coins = coins - ?, cases_opened = cases_opened + 1 WHERE user_id = ?",
        (case["price"], owner_id),
    )
    await add_item(owner_id, item_key)
    new_coins = coins - case["price"]

    await callback.message.edit_text(
        f"🎉 Выпало: {emoji} {esc(name)} (+{percent}%)!\nОстаток монет: {new_coins} 🪙",
        reply_markup=case_offer_keyboard(case_num, owner_id),
    )
    await callback.answer("Кейс открыт!")


@dp.message(F.text.lower() == "эволюция")
async def evolve(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level = row[2], row[3]

    if score < MAX_LEVEL_SCORE:
        await message.reply(f"Нужно достичь «ногу мгг» (39 ур, {MAX_LEVEL_SCORE} очков), чтобы эволюционировать.")
        return

    new_evolution = evolution_level + 1
    await db_exec("UPDATE users SET score = 0, evolution_level = ? WHERE user_id = ?", (new_evolution, user_id))

    unlock_text = ""
    if new_evolution == 1:
        unlock_text = "\nОткрыта фарма 700-1250 очков и эмодзи 🦿 (25 очков, до 10 раз в соо)!"
    elif new_evolution == 2:
        await add_item(user_id, "star")
        unlock_text = "\nПолучена ⭐️ Звезда перерождения (+50%) — экипируй в инвентарь!"

    await message.reply(f"🎆 ЭВОЛЮЦИЯ! Прогресс сброшен, теперь у тебя {new_evolution} уровень эволюции навсегда.{unlock_text}")


@dp.message(F.text.lower() == "ивент ноги")
async def toggle_event(message: Message):
    if not is_admin(message):
        return

    active = await is_event_active()
    new_value = "0" if active else "1"
    await db_exec(
        "INSERT INTO settings (key, value) VALUES ('event_active', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (new_value,),
    )

    if new_value == "1":
        await message.reply("🌟 Ивент «Золотая ногость» запущен! Х2 к фарме ног во всех чатах.")
    else:
        await message.reply("Ивент «Золотая ногость» окончен.")


@dp.message(F.text.lower().startswith(NEWS_PREFIX))
async def broadcast_news(message: Message):
    if not is_admin(message):
        return
    if message.chat.type != "private":
        return

    text = message.text[len(NEWS_PREFIX):].strip()
    if not text:
        await message.reply("Напиши текст новости после команды: новость <текст>")
        return

    chat_ids = await get_all_chat_ids()
    sent = 0
    failed = 0
    body = f"📰 <b>Новость от разработчика:</b>\n\n{esc(text)}"

    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id, body)
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(chat_id, body)
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await message.reply(f"Разослано в {sent} чатов. Не удалось: {failed}.")


@dp.message(F.text.lower().startswith("дать ног"))
async def admin_give_legs(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_GIVE_LEGS_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: дать ног <количество> [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    amount = int(match.group(1))
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_score = row[2] + amount
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_score, target.id))

    await message.reply(f"Выдано {amount} очков ноги игроку {esc(target_username)}. Теперь у него: {new_score}")


@dp.message(F.text.lower().startswith("снять ноги"))
async def admin_take_legs(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_TAKE_LEGS_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: снять ноги <количество> [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    amount = int(match.group(1))
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_score = max(0, row[2] - amount)
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_score, target.id))

    await message.reply(f"Снято очков у {esc(target_username)}. Теперь у него: {new_score}")


@dp.message(F.text.lower().startswith("дать эво"))
async def admin_give_evo(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_GIVE_EVO_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: дать эво <количество> [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    amount = int(match.group(1))
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_evo = row[3] + amount
    await db_exec("UPDATE users SET evolution_level = ? WHERE user_id = ?", (new_evo, target.id))

    await message.reply(f"Выдано {amount} уровней эволюции игроку {esc(target_username)}. Теперь: {new_evo}")


@dp.message(F.text.lower().startswith("снять эво"))
async def admin_take_evo(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_TAKE_EVO_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: снять эво <количество> [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    amount = int(match.group(1))
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_evo = max(0, row[3] - amount)
    await db_exec("UPDATE users SET evolution_level = ? WHERE user_id = ?", (new_evo, target.id))

    await message.reply(f"Снято {amount} уровней эволюции у {esc(target_username)}. Теперь: {new_evo}")


@dp.message(F.text.lower().startswith("дать коин"))
async def admin_give_coin(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_GIVE_COIN_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: дать коин <количество> [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    amount = int(match.group(1))
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_coins = row[5] + amount
    await db_exec("UPDATE users SET coins = ? WHERE user_id = ?", (new_coins, target.id))

    await message.reply(f"Выдано {amount} 🪙 игроку {esc(target_username)}. Теперь: {new_coins}")


@dp.message(F.text.lower().startswith("снять коин"))
async def admin_take_coin(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_TAKE_COIN_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: снять коин <количество> [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    amount = int(match.group(1))
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_coins = max(0, row[5] - amount)
    await db_exec("UPDATE users SET coins = ? WHERE user_id = ?", (new_coins, target.id))

    await message.reply(f"Снято {amount} 🪙 у {esc(target_username)}. Теперь: {new_coins}")


async def handle(request):
    return web.Response(text="Бот Нога Работает!")


PING_INTERVAL = 600


async def keep_alive():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        print("RENDER_EXTERNAL_URL не задан, self-ping отключён")
        return

    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    print(f"Self-ping: {resp.status}")
            except Exception as e:
                print(f"Self-ping не удался: {e}")


async def main():
    await init_db()

    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    asyncio.create_task(keep_alive())

    print("Бот НОГА запущен!")
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        await bot.session.close()
        await runner.cleanup()


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Установи переменную окружения BOT_TOKEN")
    if not TURSO_URL or not TURSO_TOKEN:
        raise RuntimeError("Установи переменные окружения TURSO_DATABASE_URL и TURSO_AUTH_TOKEN")
    asyncio.run(main())
