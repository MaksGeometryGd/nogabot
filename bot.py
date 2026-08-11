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

# ---------- Премиум-эмодзи ----------
PREMIUM_MIKU = '<tg-emoji emoji-id="5199793038410391513">🤩</tg-emoji>'
PREMIUM_MGG = '<tg-emoji emoji-id="6327920744789444368">🥰</tg-emoji>'

PREMIUM_BADGE_EVO = '<tg-emoji emoji-id="5370704514561093615">🏅</tg-emoji>'
PREMIUM_BADGE_CASE = '<tg-emoji emoji-id="5328257610472775810">🎖️</tg-emoji>'
PREMIUM_BADGE_FARM = '<tg-emoji emoji-id="5415966542078683753">🥇</tg-emoji>'
PREMIUM_BADGE_EVO5 = '<tg-emoji emoji-id="5372812377135789260">👑</tg-emoji>'

PREMIUM_DAILY_CHARM = '<tg-emoji emoji-id="5233570349148311519">🧿</tg-emoji>'

PREMIUM_MK_MGG = '<tg-emoji emoji-id="5420141555233071341">📿</tg-emoji>'
PREMIUM_MK_SANDSMOON = '<tg-emoji emoji-id="5197260300490907908">📿</tg-emoji>'
PREMIUM_MK_FIXSAHAL1 = '<tg-emoji emoji-id="5330393755407111028">📿</tg-emoji>'
PREMIUM_MK_MK = '<tg-emoji emoji-id="5776399733702528178">📿</tg-emoji>'
PREMIUM_MK_PANTHER = '<tg-emoji emoji-id="5778352775591103997">📿</tg-emoji>'
PREMIUM_MK_VECTOR = '<tg-emoji emoji-id="5233239138450312962">📿</tg-emoji>'
PREMIUM_MK_BROKEN = '<tg-emoji emoji-id="5208923808169222461">📿🥀</tg-emoji>'

# заглушки — замени на реальные emoji-id, когда достанешь (см. инструкцию про custom_emoji_id)
PREMIUM_OWNER_BADGE = '<tg-emoji emoji-id="5204056085509477484">💠</tg-emoji>'
PREMIUM_VIP_BADGE = '<tg-emoji emoji-id="5233333941263437275">💎</tg-emoji>'
PREMIUM_VIP_ITEM = '<tg-emoji emoji-id="5344025423258864934">🎗️</tg-emoji>'
PREMIUM_MK_MARY = '<tg-emoji emoji-id="5224652622652266008">📿</tg-emoji>'
PREMIUM_MK_VERON03 = '<tg-emoji emoji-id="5429446558930182229">📿</tg-emoji>'
PREMIUM_STRANGE_COIN = '<tg-emoji emoji-id="5035428694441592026">🪙</tg-emoji>'

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------- Уровни 1-20 (визуальный рост) ----------
REGULAR_THRESHOLDS = [10, 50, 150, 300, 500, 800, 1200, 1600, 2000, 2400,
                       3000, 3600, 4200, 4800, 5400, 6000, 6600, 7200, 7800, 8400]

# ---------- Уровни 21-39 (именные) ----------
CUSTOM_LEVELS = [
    (9000,  "🦵🍀", "нога удачи"),
    (9600,  "🦵🌬️", "нога воздухана"),
    (10200, "🦵🌔", "нога SandsMoon"),
    (10800, "🦵🍗", "гигантская нога"),
    (11400, "🦵✨", "блестящая нога"),
    (12000, "🦵🥉", "бронзовая нога"),
    (12600, "🦵🥈", "серебряная нога"),
    (13200, "🦵🏆", "золотая нога"),
    (13800, "🦵💎", "алмазная нога"),
    (14400, "🦵💀", "нога смерти"),
    (15000, "🦵😎", "нога Fixsahal1"),
    (15600, "🦵👼", "нога ангела"),
    (16200, "🦵🦵", "нога Panther"),
    (16800, PREMIUM_MIKU, "нога Мику"),
    (17400, "🦵🏇", "нога героя"),
    (18000, "🦵👁", "нога полу-бога"),
    (18600, "🦵🌌", "космическая нога"),
    (19200, "🦵🧿", "нога бога"),
    (19800, PREMIUM_MGG, "нога MGG"),
]

ALL_THRESHOLDS = REGULAR_THRESHOLDS + [t for t, _, _ in CUSTOM_LEVELS]
MAX_LEVEL_SCORE = ALL_THRESHOLDS[-1]  # база (эво 0) для требования эволюции — 39 ур

# ---------- Уровни 40+ (престиж-грайнд для топов) ----------
EXTRA_TIERS = [
    (40, 45, "🦵☄️", "нога Метеорита"),
    (46, 50, "🦵🪐", "нога Планеты"),
    (51, 55, "🦵⚡🔥", "нога Плазмы"),
    (56, 60, "🦵📡✨", "нога Пульсара"),
    (61, 70, "🦵🌠", "нога Квазара"),
    (71, 80, "🦵🌑🕳️", "нога Тёмной Материи"),
    (81, 100, "🦵⚫🕳️", "нога Чёрной дыры"),
    (101, 125, "🦵🌌", "нога галактики"),
    (126, 150, "🦵🌠🌌", "нога вселенной"),
    (151, 200, "🦵🌀🌌", "нога Мультивселенной"),
    (201, 300, "🦵⚛️🌀", "нога Сингулярности"),
    (301, 500, "🦵☢️⚛️", "нога Антиматерии"),
    (501, 1000, "🦵⬛🌌", "нога пустоты"),
    (1001, 1500, "🦵♾️🌀", "нога Парадокса"),
    (1501, 2000, "🦵🟩💻", "нога Матрицы"),
    (2001, 3000, "🦵🔷🔁", "нога Фрактала"),
    (3001, 5000, "🦵🌀⏳🕳️", "нога Разрыва пространственно-временного континуума"),
    (5001, 10000, "🦵🚀💫", "нога Сверхсветового прыжка"),
    (10001, 20000, "🦵⏳❌🌀", "нога Стирателя тайм-лайнов"),
]
MGG_MEGA_LEVEL = 20001
MGG_MEGA_EMOJI = PREMIUM_MGG
MGG_MEGA_NAME = "нога кошко-девочки MGG"

LEG_POINT = 1
LEG_LIMIT = 5
MEK_POINT = 18  # нерф с 25
MEK_LIMIT = 10

FARM_COOLDOWN = 1200
FARM_BASE = (70, 170)      # нерф с (100, 250)
FARM_EVOLVED = (500, 900)  # нерф с (700, 1250)

EXCHANGE_RATE = 200

DAILY_TABLE = [100, 250, 500, 750, 1000]
DAILY_MIN_GAP = 20 * 3600
DAILY_STREAK_LIMIT = 48 * 3600

BADGE_EVO_TOTAL = 30000

EVO_HARDNESS_RATE = 0.10  # +10% к порогу очков за каждый уровень эволюции (линейно, не по нарастающей)
EVO_BOOST_STEP = 0.10      # нерф с 0.30/0.20

VIP_BOOST = 2.0  # +200%

# ---------- Предметы (нерф % и шансов дропа) ----------
ITEMS = {
    "amulet": ("🪬", "Амулет галактики", 12, 10),
    "orb":    ("🔮", "Шар парадокса", 10, 20),
    "pill":   ("💊", "Таблетка силы", 8, 30),
    "candle": ("🪔", "Свеча солнцестояния", 6, 35),
    "gift":   ("💮", "Подарок кошко-девочки", 45, 5),
    "star":   ("⭐️", "Звезда перерождения", 30, 0),
    "daily_charm": (PREMIUM_DAILY_CHARM, "Дневной амулет", 15, 0),
    "mk_mgg":       (PREMIUM_MK_MGG, "Амулет MGG", 125, 1),
    "mk_sandsmoon": (PREMIUM_MK_SANDSMOON, "Амулет SandsMoon", 40, 6),
    "mk_fixsahal1": (PREMIUM_MK_FIXSAHAL1, "Амулет Fixsahal1", 30, 10),
    "mk_mk":        (PREMIUM_MK_MK, "Амулет Mk", 50, 3),
    "mk_panther":   (PREMIUM_MK_PANTHER, "Амулет Panther", 20, 14),
    "mk_vector":    (PREMIUM_MK_VECTOR, "Амулет Vector", 40, 7),
    "mk_broken":    (PREMIUM_MK_BROKEN, "Сломанный амулет", 20, 29),
    "mk_mary":      (PREMIUM_MK_MARY, "Амулет Mary", 45, 10),
    "mk_veron03":   (PREMIUM_MK_VERON03, "Амулет Veron03", 70, 5),
    "vip_charm":    (PREMIUM_VIP_ITEM, "VIP-амулет", 250, 0),
    "strange_coin": (PREMIUM_STRANGE_COIN, "Странная монета", 0, 15),
}

PASSIVE_ITEMS = {"strange_coin"}  # не экипируются, работают пассивно пока лежат в инвентаре

SELL_PRICE = {
    "amulet": 8, "orb": 6, "pill": 5, "candle": 4, "gift": 20, "star": 15, "daily_charm": 10,
    "mk_mgg": 60, "mk_sandsmoon": 18, "mk_fixsahal1": 14, "mk_mk": 22, "mk_panther": 10,
    "mk_vector": 18, "mk_broken": 8, "mk_mary": 20, "mk_veron03": 30, "vip_charm": 50,
    "strange_coin": 12,
}

ITEM_FLAT_BONUS = {
    "amulet": 1, "orb": 1, "pill": 1, "candle": 1,
    "star": 2, "gift": 3,
}

CASES = {
    1: {"name": "Базовый кейс", "price": 20, "pool": ["amulet", "orb", "pill", "candle", "gift"]},
    2: {"name": "Кейс Мк", "price": 50,
        "pool": ["mk_mgg", "mk_sandsmoon", "mk_fixsahal1", "mk_mk", "mk_panther", "mk_vector",
                 "mk_broken", "mk_mary", "mk_veron03", "strange_coin"]},
}

# ---------- Regex ----------
AMOUNT = r"(\d+(?:\.\d+)?к{0,4})"

ADMIN_GIVE_LEGS_RE = re.compile(rf"^!дать ног {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_LEGS_RE = re.compile(rf"^!снять ноги {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_EVO_RE = re.compile(rf"^!дать эво {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_EVO_RE = re.compile(rf"^!снять эво {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_COIN_RE = re.compile(rf"^!дать коин {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_COIN_RE = re.compile(rf"^!снять коин {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_BOOST_RE = re.compile(r"^!дать б (.+?)(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_BOOST_RE = re.compile(r"^!снять б (.+?)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_ITEM_RE = re.compile(r"^!дать п (.+?)(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_ITEM_RE = re.compile(r"^!снять п (.+?)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_VIP_RE = re.compile(rf"^!дать вип {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_VIP_RE = re.compile(r"^!снять вип(\s+себе)?$", re.IGNORECASE)
ADMIN_RESET_RE = re.compile(r"^!сбросить(\s+себе)?$", re.IGNORECASE)

PEER_GIVE_LEGS_RE = re.compile(rf"^дать ног {AMOUNT}$", re.IGNORECASE)
PEER_GIVE_COIN_RE = re.compile(rf"^дать коин {AMOUNT}$", re.IGNORECASE)

EXCHANGE_RE = re.compile(rf"^обменять {AMOUNT}$", re.IGNORECASE)
CASE_NUM_RE = re.compile(r"^кейс (\d+)$", re.IGNORECASE)
INFO_RE = re.compile(r"^инфо\s+@?(\w+)$", re.IGNORECASE)

NEWS_PREFIX = "!новость "

FIXED_COMMANDS = {
    "моя нога", "топ ног", "гл топ ног", "топ эво", "гл топ эво", "топ коин", "гл топ коин",
    "ферма", "фарма", "инвентарь", "эволюция", "кейс", "кейсы", "бонус",
    "смс выкл", "смс вкл", "вип", "!ивент ноги", "бейджи",
}
PREFIX_COMMANDS = (
    "обменять ", "!дать ног", "!снять ноги", "!дать эво", "!снять эво",
    "!дать коин", "!снять коин", "!дать б", "!снять б", "!дать п", "!снять п", "!дать вип", "!снять вип", "!сбросить",
    "передать ", "кейс ", NEWS_PREFIX, "дать ног ", "дать коин ", "инфо ", "продать б ", "продать п ",
)


def is_command_text(text: str) -> bool:
    t = text.lower()
    if t in FIXED_COMMANDS:
        return True
    return any(t.startswith(p) for p in PREFIX_COMMANDS)


def esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def parse_amount(text: str):
    m = re.match(r"^(\d+(?:\.\d+)?)(к{0,4})$", text.strip().lower())
    if not m:
        return None
    number = float(m.group(1))
    k_count = len(m.group(2))
    return round(number * (1000 ** k_count))


TG_EMOJI_RE = re.compile(r"<tg-emoji[^>]*>(.*?)</tg-emoji>")


def plain_emoji(emoji_html: str) -> str:
    m = TG_EMOJI_RE.match(emoji_html or "")
    return m.group(1) if m else (emoji_html or "")


def build_regular_visual(level: int) -> str:
    if level <= 5:
        return "🦵" * level
    idx = level - 6
    tier = idx // 5
    pos = idx % 5 + 1
    tier_emoji = ["🦵🏻", "🦵🏽", "🦿"][tier]
    prev_emoji = ["🦵", "🦵🏻", "🦵🏽"][tier]
    return tier_emoji * pos + prev_emoji * (5 - pos)


def base_level_threshold(level: int) -> int:
    if level <= 39:
        return ALL_THRESHOLDS[level - 1]
    return MAX_LEVEL_SCORE + round(200 * (level - 39) ** 1.5)


def level_threshold(level: int, evolution_level: int) -> int:
    return round(base_level_threshold(level) * (1 + EVO_HARDNESS_RATE * evolution_level))


def get_level_index(score: int, evolution_level: int = 0) -> int:
    lo, hi = 0, 200000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if level_threshold(mid, evolution_level) <= score:
            lo = mid
        else:
            hi = mid - 1
    return lo


def get_level_visual(level: int):
    if level == 0:
        return "🧍", "обычный безногий челик", True
    if level <= 20:
        return build_regular_visual(level), "", True
    if level <= 39:
        _, emoji, name = CUSTOM_LEVELS[level - 21]
        return emoji, name, True
    if level >= MGG_MEGA_LEVEL:
        return MGG_MEGA_EMOJI, MGG_MEGA_NAME, False
    for start, end, emoji, name in EXTRA_TIERS:
        if start <= level <= end:
            return emoji, name, True
    return "❓", "неизвестный уровень", True


def next_level_text(score: int, evolution_level: int) -> str:
    level = get_level_index(score, evolution_level)
    if level >= MGG_MEGA_LEVEL:
        return "Ты достиг абсолютного предела ноги — дальше только легенды 🌌"
    nxt = level_threshold(level + 1, evolution_level)
    return f"До {level + 1} уровня осталось {nxt - score} очков"


def get_multiplier(evolution_level: int, active_item: str, vip_active: bool) -> float:
    mult = 1.0
    if evolution_level >= 2:
        mult += EVO_BOOST_STEP
    if evolution_level >= 3:
        mult += EVO_BOOST_STEP * (evolution_level - 2)
    if active_item and active_item in ITEMS:
        mult += ITEMS[active_item][2] / 100
    if vip_active:
        mult += VIP_BOOST
    return mult


def parse_hidden(hidden_str: str) -> set:
    return set(h for h in (hidden_str or "").split(",") if h)


def badge_list(username: str, evolution_level: int, cases_opened: int, total_farmed: int, vip_active: bool):
    result = []
    if username and username.lower() == ADMIN_USERNAME.lower():
        result.append(("owner", PREMIUM_OWNER_BADGE, "Владелец"))
    if vip_active:
        result.append(("vip", PREMIUM_VIP_BADGE, "VIP"))
    if evolution_level >= 1:
        result.append(("evo", PREMIUM_BADGE_EVO, "1+ эволюция"))
    if cases_opened >= 5:
        result.append(("case", PREMIUM_BADGE_CASE, "5+ кейсов"))
    if total_farmed >= BADGE_EVO_TOTAL:
        result.append(("farm", PREMIUM_BADGE_FARM, "30k нафармлено"))
    if evolution_level >= 5:
        result.append(("evo5", PREMIUM_BADGE_EVO5, "5 эволюция"))
    return result


def get_badges(username: str, evolution_level: int, cases_opened: int, total_farmed: int, vip_active: bool,
                hidden: set = frozenset()) -> str:
    earned = badge_list(username, evolution_level, cases_opened, total_farmed, vip_active)
    return "".join(emoji for key, emoji, _ in earned if key not in hidden)


def badges_keyboard(earned, hidden: set, user_id: int) -> InlineKeyboardMarkup:
    rows = []
    for key, emoji, label in earned:
        state = "🙈 скрыт" if key in hidden else "✅ показан"
        rows.append([InlineKeyboardButton(
            text=f"{plain_emoji(emoji)} {label} — {state}",
            callback_data=f"badge:{user_id}:{key}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def farm_range(evolution_level: int):
    return FARM_EVOLVED if evolution_level >= 1 else FARM_BASE


def is_admin(message: Message) -> bool:
    return (message.from_user.username or "").lower() == ADMIN_USERNAME.lower()


def roll_case_item(case_num: int) -> str:
    pool = CASES[case_num]["pool"]
    weights = [ITEMS[k][3] for k in pool]
    return random.choices(pool, weights=weights, k=1)[0]


def find_item_by_name(query: str, only_passive=None):
    q = query.strip().lower()
    candidates = ITEMS.items()
    if only_passive is True:
        candidates = [(k, v) for k, v in candidates if k in PASSIVE_ITEMS]
    elif only_passive is False:
        candidates = [(k, v) for k, v in candidates if k not in PASSIVE_ITEMS]
    for key, (_, name, _, _) in candidates:
        if name.lower() == q:
            return key
    matches = [key for key, (_, name, _, _) in candidates if q in name.lower()]
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


USER_COLUMNS = (
    "user_id, username, score, evolution_level, last_farm, coins, active_item, "
    "cases_opened, total_farmed, last_bonus, bonus_streak, levelup_notify, vip_until, hidden_badges"
)


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
            bonus_streak INTEGER DEFAULT 0,
            levelup_notify INTEGER DEFAULT 1,
            vip_until INTEGER DEFAULT 0
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
    for stmt in (
        "ALTER TABLE users ADD COLUMN levelup_notify INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN vip_until INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN hidden_badges TEXT DEFAULT ''",
    ):
        try:
            await db_exec(stmt)
        except Exception:
            pass


async def get_user(user_id: int):
    return await db_query_one(f"SELECT {USER_COLUMNS} FROM users WHERE user_id = ?", (user_id,))


async def get_user_by_username(username: str):
    return await db_query_one(f"SELECT {USER_COLUMNS} FROM users WHERE lower(username) = lower(?)", (username,))


async def ensure_user(user_id: int, username: str):
    row = await get_user(user_id)
    if row is None:
        await db_exec("INSERT INTO users (user_id, username, score) VALUES (?, ?, 0)", (user_id, username))
        return (user_id, username, 0, 0, 0, 0, None, 0, 0, 0, 0, 1, 0, "")
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
            f"SELECT username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges "
            f"FROM users ORDER BY {order_column} DESC LIMIT ?",
            (limit,),
        )
    else:
        rows = await db_query(
            f"""SELECT u.username, u.score, u.evolution_level, u.coins, u.cases_opened, u.total_farmed, u.vip_until, u.hidden_badges
                FROM users u JOIN chat_members cm ON u.user_id = cm.user_id
                WHERE cm.chat_id = ? ORDER BY u.{order_column} DESC LIMIT ?""",
            (chat_id, limit),
        )
    return rows


def is_vip_active(vip_until: int) -> bool:
    return bool(vip_until) and vip_until > int(time.time())


def inventory_keyboard(inventory_rows, active_item: str, user_id: int) -> InlineKeyboardMarkup:
    rows = []
    for item_key, qty in inventory_rows:
        if item_key in PASSIVE_ITEMS:
            continue
        emoji, name, percent, _ = ITEMS[item_key]
        mark = " ✅" if active_item == item_key else ""
        rows.append([InlineKeyboardButton(
            text=f"{name} {plain_emoji(emoji)} (+{percent}%) x{qty}{mark}",
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


async def maybe_announce_levelup(message: Message, username: str, old_score: int, new_score: int,
                                  evolution_level: int, notify: bool):
    if not notify:
        return
    old_level = get_level_index(old_score, evolution_level)
    new_level = get_level_index(new_score, evolution_level)
    if new_level <= old_level:
        return
    emoji, name, show_level = get_level_visual(new_level)
    lvl_part = f" ({new_level} лвл)" if show_level else ""
    name_part = f" {esc(name)}" if name else ""
    await message.reply(f"🎉 {esc(username)} поднялся до нового уровня! {emoji}{name_part}{lvl_part}")


@dp.message(F.text.lower() == "смс выкл")
async def notify_off(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)
    await db_exec("UPDATE users SET levelup_notify = 0 WHERE user_id = ?", (user_id,))
    await message.reply("Уведомления о новом уровне выключены.")


@dp.message(F.text.lower() == "смс вкл")
async def notify_on(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)
    await db_exec("UPDATE users SET levelup_notify = 1 WHERE user_id = ?", (user_id,))
    await message.reply("Уведомления о новом уровне включены.")


@dp.message(F.text.lower() == "вип")
async def vip_info_command(message: Message):
    await message.reply(f"Вы можете купить ВИП у создателя @{ADMIN_USERNAME}")


@dp.message(F.text.lower() == "бейджи")
async def badges_menu(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    evolution_level, cases_opened, total_farmed, vip_until = row[3], row[7], row[8], row[12]
    hidden = parse_hidden(row[13] if len(row) > 13 else "")
    vip_active = is_vip_active(vip_until)

    earned = badge_list(username, evolution_level, cases_opened, total_farmed, vip_active)
    if not earned:
        await message.reply("У тебя пока нет значков. Качай ногу, эволюционируй, открывай кейсы!")
        return

    kb = badges_keyboard(earned, hidden, user_id)
    await message.reply("🏷 Твои значки (жми, чтобы скрыть/показать в топах):", reply_markup=kb)


@dp.callback_query(F.data.startswith("badge:"))
async def toggle_badge(callback: CallbackQuery):
    _, owner_str, key = callback.data.split(":")
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer("Это не твои значки!", show_alert=True)
        return

    row = await get_user(owner_id)
    username, evolution_level, cases_opened, total_farmed, vip_until = row[1], row[3], row[7], row[8], row[12]
    hidden = parse_hidden(row[13] if len(row) > 13 else "")

    if key in hidden:
        hidden.discard(key)
    else:
        hidden.add(key)

    new_hidden_str = ",".join(sorted(hidden))
    await db_exec("UPDATE users SET hidden_badges = ? WHERE user_id = ?", (new_hidden_str, owner_id))

    vip_active = is_vip_active(vip_until)
    earned = badge_list(username, evolution_level, cases_opened, total_farmed, vip_active)
    kb = badges_keyboard(earned, hidden, owner_id)
    await callback.message.edit_text("🏷 Твои значки (жми, чтобы скрыть/показать в топах):", reply_markup=kb)
    await callback.answer("Готово!")


@dp.message(F.text.regexp(r"[🦵🦿]"))
async def count_legs(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    text = message.text

    row = await ensure_user(user_id, username)
    score, evolution_level, active_item = row[2], row[3], row[6]
    levelup_notify, vip_until = row[11], row[12]
    vip_active = is_vip_active(vip_until)

    flat_bonus = ITEM_FLAT_BONUS.get(active_item, 0)

    legs = min(text.count("🦵"), LEG_LIMIT)
    gained = legs * LEG_POINT

    mek = 0
    if evolution_level >= 1:
        mek = min(text.count("🦿"), MEK_LIMIT)
        gained += mek * MEK_POINT

    if gained == 0:
        return

    gained += flat_bonus  # гарант-бонус применяется один раз к итогу, а не за каждую ногу

    mult = get_multiplier(evolution_level, active_item, vip_active)
    event_mult = 2 if await is_event_active() else 1
    total = round(gained * mult * event_mult)
    new_score = score + total

    await db_exec(
        "UPDATE users SET score = ?, total_farmed = total_farmed + ? WHERE user_id = ?",
        (new_score, total, user_id),
    )

    await maybe_announce_levelup(message, username, score, new_score, evolution_level, bool(levelup_notify))

    inv = await get_inventory(user_id)
    has_strange_coin = any(k == "strange_coin" and q > 0 for k, q in inv)
    coin_bonus = 0
    if has_strange_coin:
        coin_bonus = 1
        await db_exec("UPDATE users SET coins = coins + 1 WHERE user_id = ?", (user_id,))

    now = time.monotonic()
    chat_id = message.chat.id
    if now - _last_leg_reply.get(chat_id, 0) < LEG_REPLY_COOLDOWN:
        return
    _last_leg_reply[chat_id] = now

    parts = f"+{legs}🦵"
    if mek:
        parts += f" +{mek}🦿"
    coin_text = f" +{coin_bonus}🪙" if coin_bonus else ""
    await message.reply(f"Лютый рофл засчитан! {parts} → +{total} очков{coin_text} (Всего: {new_score})")


@dp.message(F.text.lower() == "моя нога")
async def my_profile(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level, coins, active_item = row[2], row[3], row[5], row[6]
    vip_until = row[12]
    vip_active = is_vip_active(vip_until)

    level = get_level_index(score, evolution_level)
    emoji, name, show_level = get_level_visual(level)
    nxt = next_level_text(score, evolution_level)
    mult = get_multiplier(evolution_level, active_item, vip_active)
    flat_bonus = ITEM_FLAT_BONUS.get(active_item, 0)

    if vip_active:
        left = vip_until - int(time.time())
        d, rem = divmod(left, 86400)
        h = rem // 3600
        vip_line = f"● VIP статус: активен ({d} дн {h} ч) {PREMIUM_VIP_BADGE}\n"
    else:
        vip_line = "● VIP статус: не активен\n"

    lvl_line = f"● Уровень ноги: {level} лвл\n" if show_level else ""
    name_part = f" {esc(name)}" if name else ""
    guarant_line = f"● Гарант-буст с предмета: +{flat_bonus} к итогу\n" if flat_bonus else ""

    text = (
        f"👣 <b>ТВОЯ ЛЮТАЯ НОГОСТЬ:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"● Очки: <code>{score}</code> {emoji}\n"
        f"● Монеты: <code>{coins}</code> 🪙\n"
        f"● Вид ног: {emoji}{name_part}\n"
        f"{lvl_line}"
        f"● Уровень эволюции: {evolution_level}\n"
        f"● Процентовый буст: +{round((mult - 1) * 100)}%\n"
        f"{guarant_line}"
        f"{vip_line}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"● {nxt}"
    )
    await message.reply(text)


@dp.message(F.text.regexp(r"(?i)^инфо\s+@?\w+$"))
async def info_player(message: Message):
    match = INFO_RE.match(message.text.strip())
    if not match:
        return
    target_username = match.group(1)

    row = await get_user_by_username(target_username)
    if not row:
        await message.reply("Игрок не найден (он ещё не писал ноги в этом боте).")
        return

    username = row[1]
    score, evolution_level, coins, active_item = row[2], row[3], row[5], row[6]
    cases_opened, total_farmed = row[7], row[8]
    vip_until = row[12]
    hidden = parse_hidden(row[13] if len(row) > 13 else "")
    vip_active = is_vip_active(vip_until)
    level = get_level_index(score, evolution_level)
    emoji, name, show_level = get_level_visual(level)
    lvl_part = f" ({level} лвл)" if show_level else ""
    name_part = f" {esc(name)}" if name else ""
    item_text = ITEMS[active_item][1] if active_item and active_item in ITEMS else "нет"
    vip_text = "активен" if vip_active else "не активен"
    badges = get_badges(username, evolution_level, cases_opened, total_farmed, vip_active, hidden)

    text = (
        f"👣 <b>Инфо об игроке {esc(username)}{badges}:</b>\n"
        f"● Нога: {emoji}{name_part}{lvl_part}\n"
        f"● Очки: <code>{score}</code>\n"
        f"● Монеты: <code>{coins}</code> 🪙\n"
        f"● Уровень эволюции: {evolution_level}\n"
        f"● VIP: {vip_text}\n"
        f"● Экипировано: {esc(item_text)}"
    )
    await message.reply(text)


async def send_legs_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "score")

    if not rows:
        await message.reply("В топе пока пусто, никто еще не кинул ногу... 🧍")
        return

    text = f"🏆 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges) in enumerate(rows, 1):
        level = get_level_index(score, evolution_level)
        emoji, name, show_level = get_level_visual(level)
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_hidden(hidden_badges))
        lvl_part = f" ({level} лвл)" if show_level else ""
        name_part = f" {esc(name)}" if name else ""
        text += f"{i}. {esc(username)}{badges} — <code>{score}</code>\n   └ {emoji}{name_part}{lvl_part}\n\n"

    await message.reply(text)


async def send_evo_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "evolution_level")

    if not rows:
        await message.reply("В топе пока пусто.")
        return

    text = f"🎆 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges) in enumerate(rows, 1):
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_hidden(hidden_badges))
        text += f"{i}. {esc(username)}{badges} — эво {evolution_level} ({score} очков)\n"

    await message.reply(text)


async def send_coin_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "coins")

    if not rows:
        await message.reply("В топе пока пусто.")
        return

    text = f"🪙 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges) in enumerate(rows, 1):
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_hidden(hidden_badges))
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

    row = await ensure_user(user_id, username)
    score, evolution_level, active_item = row[2], row[3], row[6]
    last_farm, levelup_notify, vip_until = row[4], row[11], row[12]
    vip_active = is_vip_active(vip_until)

    if now - last_farm < FARM_COOLDOWN:
        left = FARM_COOLDOWN - (now - last_farm)
        m, s = divmod(left, 60)
        await message.reply(f"Ферма на кулдауне ⏳ Осталось {m} мин {s} сек")
        return

    low, high = farm_range(evolution_level)
    mult = get_multiplier(evolution_level, active_item, vip_active)
    event_mult = 2 if await is_event_active() else 1
    gained = round(random.randint(low, high) * mult * event_mult)
    new_score = score + gained

    await db_exec(
        "UPDATE users SET score = ?, last_farm = ?, total_farmed = total_farmed + ? WHERE user_id = ?",
        (new_score, now, gained, user_id),
    )

    await maybe_announce_levelup(message, username, score, new_score, evolution_level, bool(levelup_notify))
    await message.reply(f"Наферметил ногу! 🦵 +{gained} очков (Всего: {new_score})")


@dp.message(F.text.lower() == "бонус")
async def daily_bonus(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    now = int(time.time())

    row = await ensure_user(user_id, username)
    score, evolution_level = row[2], row[3]
    last_bonus, bonus_streak, levelup_notify = row[9], row[10], row[11]

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
        item_text = f"\n{PREMIUM_DAILY_CHARM} Плюс Дневной амулет (+15% буст) в инвентарь!"

    await maybe_announce_levelup(message, username, score, new_score, evolution_level, bool(levelup_notify))
    await message.reply(f"🎁 День {streak}: +{reward} очков ноги (Всего: {new_score}){item_text}")


@dp.message(F.text.lower().startswith("обменять "))
async def exchange(message: Message):
    match = EXCHANGE_RE.match(message.text.strip().lower())
    if not match:
        await message.reply(f"Формат: обменять <количество монет>. Курс: {EXCHANGE_RATE} очков ноги = 1 монета.")
        return

    coins_wanted = parse_amount(match.group(1))
    if not coins_wanted or coins_wanted <= 0:
        await message.reply("Количество монет должно быть больше нуля.")
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, coins, evolution_level = row[2], row[5], row[3]

    spent = coins_wanted * EXCHANGE_RATE
    if spent > score:
        max_coins = score // EXCHANGE_RATE
        await message.reply(f"Недостаточно очков. У тебя {score}, максимум можешь обменять на {max_coins} 🪙.")
        return

    old_level = get_level_index(score, evolution_level)
    new_score = score - spent
    new_level = get_level_index(new_score, evolution_level)
    new_coins = coins + coins_wanted

    await db_exec("UPDATE users SET score = ?, coins = ? WHERE user_id = ?", (new_score, new_coins, user_id))

    warn = f"\n⚠️ Уровень упал с {old_level} до {new_level}!" if new_level < old_level else ""
    await message.reply(f"Обменял {spent} очков → +{coins_wanted} 🪙 монет (Всего монет: {new_coins}){warn}")


@dp.message(F.text.regexp(r"(?i)^дать ног \d+(?:\.\d+)?к{0,4}$"))
async def peer_give_legs(message: Message):
    match = PEER_GIVE_LEGS_RE.match(message.text.strip().lower())
    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply("Некорректное количество.")
        return

    if not message.reply_to_message:
        await message.reply("Ответь этой командой на сообщение того, кому передаёшь очки.")
        return

    receiver = message.reply_to_message.from_user
    sender = message.from_user
    if receiver.id == sender.id:
        await message.reply("Нельзя передать очки самому себе.")
        return

    sender_username = sender.username or sender.first_name or "Без имени"
    receiver_username = receiver.username or receiver.first_name or "Без имени"

    sender_row = await ensure_user(sender.id, sender_username)
    if sender_row[3] < 1:
        await message.reply("Передавать очки могут только игроки хотя бы с 1 уровнем эволюции.")
        return
    if sender_row[2] < amount:
        await message.reply(f"Недостаточно очков. У тебя {sender_row[2]}.")
        return

    receiver_row = await ensure_user(receiver.id, receiver_username)

    new_sender_score = sender_row[2] - amount
    new_receiver_score = receiver_row[2] + amount
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_sender_score, sender.id))
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_receiver_score, receiver.id))

    await message.reply(f"{esc(sender_username)} передал {amount} очков игроку {esc(receiver_username)}.")
    await maybe_announce_levelup(message, receiver_username, receiver_row[2], new_receiver_score,
                                  receiver_row[3], bool(receiver_row[11]))


@dp.message(F.text.regexp(r"(?i)^дать коин \d+(?:\.\d+)?к{0,4}$"))
async def peer_give_coin(message: Message):
    match = PEER_GIVE_COIN_RE.match(message.text.strip().lower())
    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply("Некорректное количество.")
        return

    if not message.reply_to_message:
        await message.reply("Ответь этой командой на сообщение того, кому передаёшь монеты.")
        return

    receiver = message.reply_to_message.from_user
    sender = message.from_user
    if receiver.id == sender.id:
        await message.reply("Нельзя передать монеты самому себе.")
        return

    sender_username = sender.username or sender.first_name or "Без имени"
    receiver_username = receiver.username or receiver.first_name or "Без имени"

    sender_row = await ensure_user(sender.id, sender_username)
    if sender_row[3] < 1:
        await message.reply("Передавать монеты могут только игроки хотя бы с 1 уровнем эволюции.")
        return
    if sender_row[5] < amount:
        await message.reply(f"Недостаточно монет. У тебя {sender_row[5]}.")
        return

    await ensure_user(receiver.id, receiver_username)
    await db_exec("UPDATE users SET coins = coins - ? WHERE user_id = ?", (amount, sender.id))
    await db_exec("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, receiver.id))

    await message.reply(f"{esc(sender_username)} передал {amount} 🪙 игроку {esc(receiver_username)}.")


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


async def sell_item(message: Message, prefix: str, only_passive: bool):
    item_query = message.text[len(prefix):].strip()
    item_key = find_item_by_name(item_query, only_passive=only_passive)
    if not item_key:
        wrong_cmd = "продать п" if only_passive is False else "продать б"
        await message.reply(f"Не нашёл такой предмет среди {'предметов' if only_passive else 'бустеров'}. "
                             f"Если это не то — попробуй «{wrong_cmd} <название>».")
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    removed = await remove_item(user_id, item_key, 1)
    emoji, name, _, _ = ITEMS[item_key]
    if not removed:
        await message.reply(f"У тебя нет предмета «{esc(name)}».")
        return

    row = await get_user(user_id)
    if row[6] == item_key:
        remaining = await get_inventory(user_id)
        has_more = any(k == item_key and q > 0 for k, q in remaining)
        if not has_more:
            await db_exec("UPDATE users SET active_item = NULL WHERE user_id = ?", (user_id,))

    price = SELL_PRICE.get(item_key, 1)
    await db_exec("UPDATE users SET coins = coins + ? WHERE user_id = ?", (price, user_id))

    await message.reply(f"Продал {emoji} {esc(name)} за {price} 🪙.")


@dp.message(F.text.lower().startswith("продать б "))
async def sell_booster(message: Message):
    await sell_item(message, "продать б ", only_passive=False)


@dp.message(F.text.lower().startswith("продать п "))
async def sell_passive(message: Message):
    await sell_item(message, "продать п ", only_passive=True)


def format_inventory_menu_text(active_item):
    if active_item and active_item in ITEMS:
        emoji, name, percent, _ = ITEMS[active_item]
        equipped_text = f"Экипировано: {emoji} {esc(name)} (+{percent}%)"
    else:
        equipped_text = "Экипировано: ничего"
    return f"🎒 <b>Твой инвентарь</b>\n{equipped_text}\n\nВыбери раздел:"


def inventory_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧪 Бустеры", callback_data=f"inv_cat:{user_id}:boosters")],
        [InlineKeyboardButton(text="📦 Предметы", callback_data=f"inv_cat:{user_id}:items")],
    ])


def boosters_keyboard(rows, active_item: str, user_id: int) -> InlineKeyboardMarkup:
    kb_rows = []
    for item_key, qty in rows:
        if item_key in PASSIVE_ITEMS:
            continue
        emoji, name, percent, _ = ITEMS[item_key]
        mark = " ✅" if active_item == item_key else ""
        kb_rows.append([InlineKeyboardButton(
            text=f"{name} {plain_emoji(emoji)} (+{percent}%) x{qty}{mark}",
            callback_data=f"equip:{user_id}:{item_key}",
        )])
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"inv_menu:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)


def items_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"inv_menu:{user_id}")]])


def format_boosters_text(rows):
    boosters = [(k, q) for k, q in rows if k not in PASSIVE_ITEMS]
    if not boosters:
        return "🧪 У тебя нет бустеров. Можно носить только 1 за раз."
    return "🧪 Твои бустеры (можно носить максимум 1):"


def format_items_text(rows):
    passive = [(k, q) for k, q in rows if k in PASSIVE_ITEMS]
    if not passive:
        return "📦 У тебя нет предметов."
    lines = ["📦 Твои предметы (нельзя экипировать, действуют пассивно):\n"]
    for item_key, qty in passive:
        emoji, name, _, _ = ITEMS[item_key]
        lines.append(f"{emoji} {esc(name)} x{qty}")
    return "\n".join(lines)


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

    await message.reply(format_inventory_menu_text(active_item), reply_markup=inventory_menu_keyboard(user_id))


@dp.callback_query(F.data.startswith("inv_menu:"))
async def inventory_back_to_menu(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer("Это не твой инвентарь!", show_alert=True)
        return

    row = await get_user(owner_id)
    active_item = row[6]
    await callback.message.edit_text(format_inventory_menu_text(active_item), reply_markup=inventory_menu_keyboard(owner_id))
    await callback.answer()


@dp.callback_query(F.data.startswith("inv_cat:"))
async def inventory_open_category(callback: CallbackQuery):
    _, owner_str, category = callback.data.split(":")
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer("Это не твой инвентарь!", show_alert=True)
        return

    rows = await get_inventory(owner_id)
    if category == "boosters":
        row = await get_user(owner_id)
        active_item = row[6]
        await callback.message.edit_text(format_boosters_text(rows), reply_markup=boosters_keyboard(rows, active_item, owner_id))
    else:
        await callback.message.edit_text(format_items_text(rows), reply_markup=items_keyboard(owner_id))
    await callback.answer()


@dp.callback_query(F.data.startswith("equip:"))
async def toggle_equip(callback: CallbackQuery):
    _, owner_str, item_key = callback.data.split(":")
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer("Это не твой инвентарь!", show_alert=True)
        return
    if item_key in PASSIVE_ITEMS:
        await callback.answer("Этот предмет нельзя экипировать — он действует пассивно, пока лежит в инвентаре.", show_alert=True)
        return

    row = await get_user(owner_id)
    active_item = row[6]
    new_active = None if active_item == item_key else item_key
    await db_exec("UPDATE users SET active_item = ? WHERE user_id = ?", (new_active, owner_id))
    rows = await get_inventory(owner_id)

    await callback.message.edit_text(format_boosters_text(rows), reply_markup=boosters_keyboard(rows, new_active, owner_id))
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

    required = level_threshold(39, evolution_level)
    if score < required:
        await message.reply(f"Нужно достичь «ногу мгг» (39 ур, {required} очков), чтобы эволюционировать.")
        return

    new_evolution = evolution_level + 1
    await db_exec("UPDATE users SET score = 0, evolution_level = ? WHERE user_id = ?", (new_evolution, user_id))

    unlock_text = ""
    if new_evolution == 1:
        unlock_text = f"\nОткрыта фарма {FARM_EVOLVED[0]}-{FARM_EVOLVED[1]} очков и эмодзи 🦿 ({MEK_POINT} очков, до {MEK_LIMIT} раз в соо)!"
    elif new_evolution == 2:
        await add_item(user_id, "star")
        unlock_text = "\nПолучена ⭐️ Звезда перерождения — экипируй в инвентарь!"

    await message.reply(
        f"🎆 ЭВОЛЮЦИЯ! Прогресс сброшен, теперь у тебя {new_evolution} уровень эволюции навсегда.\n"
        f"⚠️ Прокачка уровней теперь на {round(EVO_HARDNESS_RATE * new_evolution * 100)}% сложнее.{unlock_text}"
    )


@dp.message(F.text.lower() == "!ивент ноги")
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
        await message.reply("Напиши текст новости после команды: !новость <текст>")
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


@dp.message(F.text.lower().startswith("!дать ног"))
async def admin_give_legs(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_GIVE_LEGS_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !дать ног <количество> [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply("Некорректное количество.")
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_score = row[2] + amount
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_score, target.id))
    await maybe_announce_levelup(message, target_username, row[2], new_score, row[3], bool(row[11]))

    await message.reply(f"Выдано {amount} очков ноги игроку {esc(target_username)}. Теперь у него: {new_score}")


@dp.message(F.text.lower().startswith("!снять ноги"))
async def admin_take_legs(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_TAKE_LEGS_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !снять ноги <количество> [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply("Некорректное количество.")
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_score = max(0, row[2] - amount)
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_score, target.id))

    await message.reply(f"Снято очков у {esc(target_username)}. Теперь у него: {new_score}")


@dp.message(F.text.lower().startswith("!дать эво"))
async def admin_give_evo(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_GIVE_EVO_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !дать эво <количество> [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply("Некорректное количество.")
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_evo = row[3] + amount
    await db_exec("UPDATE users SET evolution_level = ? WHERE user_id = ?", (new_evo, target.id))

    await message.reply(f"Выдано {amount} уровней эволюции игроку {esc(target_username)}. Теперь: {new_evo}")


@dp.message(F.text.lower().startswith("!снять эво"))
async def admin_take_evo(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_TAKE_EVO_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !снять эво <количество> [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply("Некорректное количество.")
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_evo = max(0, row[3] - amount)
    await db_exec("UPDATE users SET evolution_level = ? WHERE user_id = ?", (new_evo, target.id))

    await message.reply(f"Снято {amount} уровней эволюции у {esc(target_username)}. Теперь: {new_evo}")


@dp.message(F.text.lower().startswith("!дать коин"))
async def admin_give_coin(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_GIVE_COIN_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !дать коин <количество> [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply("Некорректное количество.")
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_coins = row[5] + amount
    await db_exec("UPDATE users SET coins = ? WHERE user_id = ?", (new_coins, target.id))

    await message.reply(f"Выдано {amount} 🪙 игроку {esc(target_username)}. Теперь: {new_coins}")


@dp.message(F.text.lower().startswith("!снять коин"))
async def admin_take_coin(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_TAKE_COIN_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !снять коин <количество> [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply("Некорректное количество.")
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_coins = max(0, row[5] - amount)
    await db_exec("UPDATE users SET coins = ? WHERE user_id = ?", (new_coins, target.id))

    await message.reply(f"Снято {amount} 🪙 у {esc(target_username)}. Теперь: {new_coins}")


@dp.message(F.text.lower().startswith("!дать б "))
async def admin_give_boost(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_GIVE_BOOST_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !дать б <название бустера> [себе] (в ответ на сообщение игрока)")
        return

    item_key = find_item_by_name(match.group(1), only_passive=False)
    if not item_key:
        await message.reply("Не нашёл такой бустер. Для пассивных предметов используй «!дать п».")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await add_item(target.id, item_key)

    emoji, name, _, _ = ITEMS[item_key]
    await message.reply(f"Выдан бустер {emoji} {esc(name)} игроку {esc(target_username)}.")


@dp.message(F.text.lower().startswith("!снять б "))
async def admin_take_boost(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_TAKE_BOOST_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !снять б <название бустера> [себе] (в ответ на сообщение игрока)")
        return

    item_key = find_item_by_name(match.group(1), only_passive=False)
    if not item_key:
        await message.reply("Не нашёл такой бустер. Для пассивных предметов используй «!снять п».")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    removed = await remove_item(target.id, item_key)

    emoji, name, _, _ = ITEMS[item_key]
    if removed:
        await message.reply(f"Снят бустер {emoji} {esc(name)} у игрока {esc(target_username)}.")
    else:
        await message.reply(f"У игрока {esc(target_username)} нет предмета «{esc(name)}».")


@dp.message(F.text.lower().startswith("!дать п "))
async def admin_give_passive(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_GIVE_ITEM_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !дать п <название предмета> [себе] (в ответ на сообщение игрока)")
        return

    item_key = find_item_by_name(match.group(1), only_passive=True)
    if not item_key:
        await message.reply("Не нашёл такой пассивный предмет. Для бустеров используй «!дать б».")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await add_item(target.id, item_key)

    emoji, name, _, _ = ITEMS[item_key]
    await message.reply(f"Выдан предмет {emoji} {esc(name)} игроку {esc(target_username)}.")


@dp.message(F.text.lower().startswith("!снять п "))
async def admin_take_passive(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_TAKE_ITEM_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !снять п <название предмета> [себе] (в ответ на сообщение игрока)")
        return

    item_key = find_item_by_name(match.group(1), only_passive=True)
    if not item_key:
        await message.reply("Не нашёл такой пассивный предмет. Для бустеров используй «!снять б».")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    removed = await remove_item(target.id, item_key)

    emoji, name, _, _ = ITEMS[item_key]
    if removed:
        await message.reply(f"Снят предмет {emoji} {esc(name)} у игрока {esc(target_username)}.")
    else:
        await message.reply(f"У игрока {esc(target_username)} нет предмета «{esc(name)}».")


@dp.message(F.text.lower().startswith("!дать вип"))
async def admin_give_vip(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_GIVE_VIP_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !дать вип <дней> [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    days = parse_amount(match.group(1))
    if not days or days <= 0:
        await message.reply("Некорректное количество дней.")
        return
    target_username = target.username or target.first_name or "Без имени"
    row = await ensure_user(target.id, target_username)

    now = int(time.time())
    base = row[12] if row[12] and row[12] > now else now
    new_vip_until = base + days * 86400

    await db_exec("UPDATE users SET vip_until = ? WHERE user_id = ?", (new_vip_until, target.id))
    was_vip_before = is_vip_active(row[12])
    if not was_vip_before:
        await add_item(target.id, "vip_charm")

    await message.reply(f"Выдан VIP на {days} дн. игроку {esc(target_username)}.")


@dp.message(F.text.lower().startswith("!снять вип"))
async def admin_take_vip(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_TAKE_VIP_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !снять вип [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(1)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await db_exec("UPDATE users SET vip_until = 0 WHERE user_id = ?", (target.id,))

    await message.reply(f"VIP снят у игрока {esc(target_username)}.")


@dp.message(F.text.lower().startswith("!сбросить"))
async def admin_reset(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_RESET_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !сбросить [себе] (в ответ на сообщение игрока)")
        return

    target = await resolve_target(message, bool(match.group(1)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)

    await db_exec(
        "UPDATE users SET score = 0, evolution_level = 0, coins = 0, active_item = NULL, "
        "cases_opened = 0, total_farmed = 0, last_bonus = 0, bonus_streak = 0, vip_until = 0 "
        "WHERE user_id = ?",
        (target.id,),
    )
    await db_exec("DELETE FROM inventory WHERE user_id = ?", (target.id,))

    await message.reply(f"Полный сброс прогресса игрока {esc(target_username)} выполнен.")


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
