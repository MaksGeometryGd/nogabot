import asyncio
import os
import random
import re
import time

import libsql
import aiohttp
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery,
)
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

# Крафтовые предметы: реальных emoji-id для них ещё нет, поэтому используем обычные
# emoji без обёртки <tg-emoji>. С фейковым emoji-id Telegram отклонял всё сообщение
# (Bad Request), из-за чего падал показ ЛЮБЫХ премиум-иконок в этом же сообщении —
# в том числе валидных (кейс, вип и т.д.). Когда появятся настоящие emoji-id, верни
# обёртку '<tg-emoji emoji-id="...">...</tg-emoji>' по аналогии с PREMIUM_MK_* выше.
PREMIUM_POWER_AMULET = '<tg-emoji emoji-id="5364047860713143546">📿💪</tg-emoji>'
PREMIUM_GALAXY_POWER_AMULET = '<tg-emoji emoji-id="5451648825431175858">🌌✨</tg-emoji>'
PREMIUM_GALAXY_MIGHT_AMULET = '<tg-emoji emoji-id="5335070858828344908">🌌💥</tg-emoji>'
PREMIUM_HYBRID_AMULET = '<tg-emoji emoji-id="5204242195032336769">🧬</tg-emoji>'
PREMIUM_FRIENDSHIP_ESSENCE = '<tg-emoji emoji-id="5341581827385599962">🤝🔅</tg-emoji>'
PREMIUM_TIME_PARTICLE = '<tg-emoji emoji-id="5985570245950053733">⏳</tg-emoji>'
PREMIUM_GOD_ESSENCE = '<tg-emoji emoji-id="5046631025711515524">🌌🧿</tg-emoji>'
PREMIUM_DEVOTION_COIN = '<tg-emoji emoji-id="5987990962532521711">🪙⚛️</tg-emoji>'
PREMIUM_OLD_VASE = '<tg-emoji emoji-id="6334461494649948210">🏺</tg-emoji>'
PREMIUM_GOLDEN_VASE = '<tg-emoji emoji-id="5954115825324527429">⚱️</tg-emoji>'
PREMIUM_GODLY_VASE = '<tg-emoji emoji-id="5283163228413641567">⚱️🌌</tg-emoji>'
PREMIUM_LUCKY_CHARM = '<tg-emoji emoji-id="5435935451355555165">🍀📿</tg-emoji>'
PREMIUM_SWIFT_PILL = '<tg-emoji emoji-id="5886217713839246898">💊☢️</tg-emoji>'
PREMIUM_PARTY_SET = '<tg-emoji emoji-id="5852607601883221665">🎁✨</tg-emoji>'
PREMIUM_WARM_CANDLE = '<tg-emoji emoji-id="5253717838870363235">🕯</tg-emoji>'

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
REVERSE_EXCHANGE_RATE = 150  # 1 коин = 150 очков ног (обратный обменник, п.5 ТЗ)

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
    "mk_veron03":   (PREMIUM_MK_VERON03, "Амулет Veron03", 60, 19),  # нерф буста: было 75% -> 60%
    "vip_charm":    (PREMIUM_VIP_ITEM, "VIP-амулет", 250, 0),
    "strange_coin": (PREMIUM_STRANGE_COIN, "Странная монета", 0, 1),

    # ---------- Крафтовые предметы (система крафтов) ----------
    "power_amulet":        (PREMIUM_POWER_AMULET, "Амулет силы", 40, 0),
    "galaxy_power_amulet": (PREMIUM_GALAXY_POWER_AMULET, "Амулет силы галактики", 80, 0),
    "galaxy_might_amulet": (PREMIUM_GALAXY_MIGHT_AMULET, "Амулет Мощи галактики", 100, 0),
    "hybrid_amulet":       (PREMIUM_HYBRID_AMULET, "Неактивированный гибридный амулет", 0, 0),
    "friendship_essence":  (PREMIUM_FRIENDSHIP_ESSENCE, "Эссенция дружбы", 0, 0),
    "time_particle":       (PREMIUM_TIME_PARTICLE, "Частица времени", 0, 0),
    "god_essence":         (PREMIUM_GOD_ESSENCE, "Эссенция Бога", 700, 0),
    "devotion_coin":       (PREMIUM_DEVOTION_COIN, "Монета боготворства", 0, 0),
    "old_vase":            (PREMIUM_OLD_VASE, "Старая ваза", 0, 0.5),
    "golden_vase":         (PREMIUM_GOLDEN_VASE, "Золотая ваза", 0, 0),
    "godly_vase":          (PREMIUM_GODLY_VASE, "Боготворная ваза", 0, 0),

    # ---------- Базовые крафты (ур.0) ----------
    "lucky_charm":  (PREMIUM_LUCKY_CHARM, "Малый амулет удачи", 15, 0),
    "swift_pill":   (PREMIUM_SWIFT_PILL, "Ускоренная таблетка", 12, 0),
    "party_set":    (PREMIUM_PARTY_SET, "Праздничный набор", 18, 0),
    "warm_candle":  (PREMIUM_WARM_CANDLE, "Тёплая свеча", 0, 0),
}

# Предметы, которые нельзя продать/передать/уничтожить — личные заглушки/значки.
NON_TRADABLE_ITEMS = {"vip_charm"}

PASSIVE_ITEMS = {
    "strange_coin",
    # крафтовые пассивки и чистые крафт-материалы (не экипируются)
    "hybrid_amulet", "friendship_essence", "time_particle", "devotion_coin",
    "old_vase", "golden_vase", "godly_vase", "warm_candle",
}

SELL_PRICE = {
    "amulet": 8, "orb": 6, "pill": 5, "candle": 4, "gift": 20, "star": 15, "daily_charm": 10,
    "mk_mgg": 60, "mk_sandsmoon": 18, "mk_fixsahal1": 14, "mk_mk": 22, "mk_panther": 10,
    "mk_vector": 18, "mk_broken": 8, "mk_mary": 20, "mk_veron03": 30, "vip_charm": 50,
    "strange_coin": 12,
    "power_amulet": 40, "galaxy_power_amulet": 90, "galaxy_might_amulet": 150,
    "hybrid_amulet": 200, "friendship_essence": 260, "time_particle": 220,
    "god_essence": 1000, "devotion_coin": 60, "old_vase": 15, "golden_vase": 120, "godly_vase": 500,
    "lucky_charm": 20, "swift_pill": 18, "party_set": 25, "warm_candle": 14,
}

ITEM_FLAT_BONUS = {
    "amulet": 1, "orb": 1, "pill": 1, "candle": 1,
    "star": 2, "gift": 3,
}

CASES = {
    1: {"name": "Базовый кейс", "price": 20, "pool": ["amulet", "orb", "pill", "candle", "gift", "old_vase"]},
    2: {"name": "Кейс Сапортов", "price": 50,
        "pool": ["mk_mgg", "mk_sandsmoon", "mk_fixsahal1", "mk_mk", "mk_panther", "mk_vector",
                 "mk_broken", "mk_mary", "mk_veron03", "strange_coin"]},
}

# Все "амулеты игроков", которые может сожрать рецепт Неактивированного гибридного амулета —
# все предметы с "амулет" в названии КРОМЕ VIP-амулета и Сломанного амулета (см. уточнение ТЗ).
ALL_PLAYER_AMULETS = [
    "amulet", "mk_mgg", "mk_sandsmoon", "mk_fixsahal1", "mk_mk",
    "mk_panther", "mk_vector", "mk_mary", "mk_veron03",
]

# ---------- Система крафтов ----------
# Уровень крафта игрока = уровень апгрейда "crafts" (0/1/2, апгрейд "апгрейд"/"прокачка").
# ingredients: {item_key: qty}. special_ingredients поддерживает доп. требования
# (валюта и "все амулеты игрока"), которых нет в обычных ITEMS-рецептах.
RECIPES = {
    # ---------- Базовые крафты (ур.0) ----------
    "lucky_charm": {
        "level": 0,
        "ingredients": {"amulet": 1, "orb": 1},
    },
    "swift_pill": {
        "level": 0,
        "ingredients": {"pill": 2, "candle": 1},
    },
    "party_set": {
        "level": 0,
        "ingredients": {"gift": 1, "candle": 1, "pill": 1},
    },
    "warm_candle": {
        "level": 0,
        "ingredients": {"candle": 3},
    },

    "power_amulet": {
        "level": 0,
        "ingredients": {"pill": 1, "mk_broken": 1},
    },
    "galaxy_power_amulet": {
        "level": 1,
        "ingredients": {"power_amulet": 1, "candle": 1, "amulet": 1},
    },
    "galaxy_might_amulet": {
        "level": 1,
        "ingredients": {"galaxy_power_amulet": 1, "power_amulet": 1},
    },
    "hybrid_amulet": {
        "level": 2,
        "ingredients": {"orb": 1, "galaxy_might_amulet": 1},
        "needs_all_amulets": True,  # + по 1 шт. каждого предмета из ALL_PLAYER_AMULETS
    },
    "friendship_essence": {
        "level": 2,
        "ingredients": {"hybrid_amulet": 1, "star": 1, "gift": 1},
    },
    "time_particle": {
        "level": 1,
        "ingredients": {"pill": 1, "orb": 1, "amulet": 1, "candle": 1, "gift": 1},
    },
    "god_essence": {
        "level": 2,
        "ingredients": {"time_particle": 1, "friendship_essence": 1, "mk_broken": 1},
    },
    "devotion_coin": {
        "level": 1,
        "ingredients": {"strange_coin": 1},
        "coin_cost": 1000,
    },
    "golden_vase": {
        "level": 1,
        "ingredients": {"old_vase": 1},
        "score_cost": 50000,
    },
    "godly_vase": {
        "level": 2,
        "ingredients": {"golden_vase": 1, "devotion_coin": 1},
    },
}

# Иерархия "уникальных" бустеров (от слабого к сильному) — используется для правила
# "при конфликте активен сильнейший": его сообщение/эмодзи/лимиты, но проценты всех
# экипированных бустеров всё равно суммируются как обычно через get_multiplier().
UNIQUE_BOOSTER_TIERS = ["power_amulet", "galaxy_power_amulet", "galaxy_might_amulet", "god_essence"]

# Модификации лимитов эмодзи 🦵/🦿/🌌/⭐️ за сообщение, которые даёт САМЫЙ сильный из
# экипированных уникальных бустеров (не суммируется с более слабыми).
# 🌌 и ⭐️ работают ТОЧНО КАК роботноги 🦿 (считаются в сообщении, дают MEK_POINT за штуку),
# но только пока экипирован соответствующий бустер — иначе их лимит 0 и они не считаются.
UNIQUE_LIMIT_OVERRIDES = {
    "power_amulet": {"mek_limit": 15},
    "galaxy_power_amulet": {"galaxy_limit": 1},
    "galaxy_might_amulet": {"galaxy_limit": 1},
    "god_essence": {"mek_limit": 30, "leg_limit": 15, "galaxy_limit": 5, "star_limit": 1},
}
GOD_ESSENCE_TIMER_CUT = 5         # -5 сек к кулдауну фермы, пока экипирована
GOD_ESSENCE_FARM_SPEED = 5        # фарм в 5 раз быстрее
TIME_PARTICLE_FARM_SPEED = 4      # фарм в 4 раза быстрее (пассивно, лежит в инвентаре)

GOD_ESSENCE_FLAVOR = f"{PREMIUM_GOD_ESSENCE} Сила бога активирована."  # заменяет обычный префикс ответа фермы


def get_active_unique_tier(active_items):
    """Самый сильный уникальный крафт-бустер среди экипированных, либо None."""
    equipped = set(_normalize_active_items(active_items))
    best = None
    for key in UNIQUE_BOOSTER_TIERS:
        if key in equipped:
            best = key
    return best


def active_farm_limits(active_items) -> dict:
    """Лимиты за сообщение (🦵/🦿/🌌/⭐️) с учётом сильнейшего уникального бустера."""
    tier = get_active_unique_tier(active_items)
    overrides = UNIQUE_LIMIT_OVERRIDES.get(tier, {})
    return {
        "mek_limit": overrides.get("mek_limit", MEK_LIMIT),
        "leg_limit": overrides.get("leg_limit", LEG_LIMIT),
        "galaxy_limit": overrides.get("galaxy_limit", 0),
        "star_limit": overrides.get("star_limit", 0),
    }


def recipe_missing_ingredients(inventory_map: dict, coins: int, score: int, recipe: dict) -> list:
    """Список недостающих требований рецепта в виде читаемых строк. Пустой список = всё есть."""
    missing = []
    for ing_key, qty in recipe.get("ingredients", {}).items():
        have = inventory_map.get(ing_key, 0)
        if have < qty:
            name = ITEMS[ing_key][1]
            missing.append(f"{name}: {have}/{qty}")
    if recipe.get("needs_all_amulets"):
        for ing_key in ALL_PLAYER_AMULETS:
            if inventory_map.get(ing_key, 0) < 1:
                missing.append(f"{ITEMS[ing_key][1]}: 0/1")
    coin_cost = recipe.get("coin_cost", 0)
    if coin_cost and coins < coin_cost:
        missing.append(f"Монеты: {coins}/{coin_cost} 🪙")
    score_cost = recipe.get("score_cost", 0)
    if score_cost and score < score_cost:
        missing.append(f"Очки ног: {score}/{score_cost}")
    return missing


def format_recipe_requirements(recipe: dict) -> str:
    parts = [f"{qty}x {ITEMS[k][1]}" for k, qty in recipe.get("ingredients", {}).items()]
    if recipe.get("needs_all_amulets"):
        parts.append("по 1x каждого амулета игрока (кроме VIP и Сломанного)")
    if recipe.get("coin_cost"):
        parts.append(f"{recipe['coin_cost']} 🪙")
    if recipe.get("score_cost"):
        parts.append(f"{recipe['score_cost']} очков ног")
    return " + ".join(parts)


# ---------- Перерождение (Rebirth) ----------
REBIRTH_EVO_PER_POINT = 5          # 5 уровней эволюции = 1 Очко Перерождения
REBIRTH_HARDNESS_STEP = 0.125      # +12.5% к сложности эволюций за каждое перерождение (середина диапазона 10-15%)

# ---------- Меню прокачки (апгрейды за Очки Перерождения) ----------
# Каждый апгрейд: max_level, базовая цена (лвл 1), правило прироста цены за уровень.
# cost(level) — цена, чтобы поднять апгрейд С (level-1) НА level.

def _linear_cost(base: int, step: int):
    return lambda level: base + step * (level - 1)


def _per_n_levels_cost(base: int, step: int, n: int):
    # цена растёт на `step` каждые `n` уровней (используется для Бустера: +1 🉑 каждые 3 лвл)
    return lambda level: base + step * ((level - 1) // n)


UPGRADES = {
    "farm_yield": {
        "name": "Ферма ДОБЫЧА",
        "desc": "+10% к добыче фермы за лвл",
        "max_level": 10,
        "cost": _linear_cost(1, 1),
        "category": 1,
    },
    "farm_cd": {
        "name": "Ферма КД",
        "desc": "-2 мин к КД фермы за лвл",
        "max_level": 5,
        "cost": _linear_cost(1, 2),
        "category": 1,
    },
    "auto_farm_legs": {
        "name": "Авто-Ферма НОГИ",
        "desc": "1:10 ног/мин · 2:100 ног/30с · 3:1000 ног/10с",
        "max_level": 3,
        "cost": _linear_cost(1, 4),
        "category": 1,
    },
    "auto_farm_coins": {
        "name": "Авто-Ферма КОИНЫ",
        "desc": "1:1 коин/5мин · 2:5 коин/5мин · 3:10 коин/3мин",
        "max_level": 3,
        "cost": _linear_cost(1, 2),  # базовая прогрессия 1/3/5
        "category": 1,
    },
    "booster": {
        "name": "Бустер",
        "desc": "+5% буст ко всему за лвл",
        "max_level": 50,
        "cost": _per_n_levels_cost(1, 1, 3),
        "category": 2,
    },
    "equip_slots": {
        "name": "Слоты экипировки",
        "desc": "+1 слот экипировки за лвл (база 1, макс 3 слота на 2 лвл)",
        "max_level": 2,
        "cost": _linear_cost(5, 5),
        "category": 2,
    },
    "discount": {
        "name": "Скидка",
        "desc": "-10% к цене кейсов за лвл",
        "max_level": 3,
        "cost": _linear_cost(1, 1),
        "category": 2,
    },
    "sell_boost": {
        "name": "Продажа",
        "desc": "+2 коина к продаже за лвл (3 лвл: 1% шанс +1 🉑 при продаже)",
        "max_level": 3,
        "cost": _linear_cost(2, 2),
        "category": 2,
    },
    "crafts": {
        "name": "Крафты", "desc": "Открывает уровни рецептов крафта (0/1/2) за 🉑",
        "max_level": 2, "cost": _linear_cost(15, 20), "category": 3,
    },
    # В разработке — не покупаемы, только отображаются
    "brew_speed": {"name": "Скорость готовки зелья", "desc": "В разработке", "max_level": 5, "cost": None, "category": 3, "wip": True},
    "brew_duration": {"name": "Длительность зелья", "desc": "В разработке", "max_level": 3, "cost": None, "category": 3, "wip": True},
    "exchanger": {"name": "Обменник", "desc": "В разработке", "max_level": 2, "cost": None, "category": 3, "wip": True},
}
UPGRADE_ORDER = list(UPGRADES.keys())
UPGRADE_CATEGORIES = {1: "🌾 Ферма", 2: "🎒 Экономика", 3: "🔨 Крафты и прочее"}

AUTO_FARM_LEGS_RATES = {1: (10, 60), 2: (100, 30), 3: (1000, 10)}     # лвл: (кол-во ног, за X секунд)
AUTO_FARM_COINS_RATES = {1: (1, 300), 2: (5, 300), 3: (10, 180)}       # лвл: (кол-во коинов, за X секунд)

# ---------- Regex ----------
AMOUNT = r"(\d+(?:\.\d+)?к{0,4})"
_AMOUNT_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?к{0,4}$", re.IGNORECASE)

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
ADMIN_GIVE_REBIRTH_RE = re.compile(rf"^!дать очкп {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_REBIRTH_RE = re.compile(rf"^!снять очкп {AMOUNT}(\s+себе)?$", re.IGNORECASE)

PEER_GIVE_LEGS_RE = re.compile(rf"^дать ног {AMOUNT}$", re.IGNORECASE)
PEER_GIVE_COIN_RE = re.compile(rf"^дать коин {AMOUNT}$", re.IGNORECASE)

EXCHANGE_RE = re.compile(rf"^обменять {AMOUNT}$", re.IGNORECASE)
REVERSE_EXCHANGE_RE = re.compile(rf"^обменять {AMOUNT} коин$", re.IGNORECASE)
CASE_NUM_RE = re.compile(r"^кейс (\d+)$", re.IGNORECASE)
INFO_RE = re.compile(r"^инфо\s+@?(\w+)$", re.IGNORECASE)

NEWS_PREFIX = "!новость "

FIXED_COMMANDS = {
    "моя нога", "топ ног", "гл топ ног", "топ эво", "гл топ эво", "топ коин", "гл топ коин",
    "ферма", "фарма", "инвентарь", "эволюция", "кейс", "кейсы", "бонус",
    "смс выкл", "смс вкл", "вип", "!ивент ноги", "бейджи",
    "перерождение", "апгрейд", "прокачка", "апг", "баланс", "топ очкп", "гл топ очкп", "помощь",
    "топ ноги вся", "топ коин вся", "топ эво вся", "топ очкп вся", "топ вся", "гл топ", "крафты", "крафт",
    "мои предметы", "предметы", "мои бустеры", "бустеры", "мой инвентарь",
}
PREFIX_COMMANDS = (
    "обменять ", "!дать ног", "!снять ноги", "!дать эво", "!снять эво",
    "!дать коин", "!снять коин", "!дать б", "!снять б", "!дать п", "!снять п", "!дать вип", "!снять вип", "!сбросить",
    "передать ", "дать ", "кейс ", NEWS_PREFIX, "инфо ", "продать",
    "!дать очкп", "!снять очкп", "открыть кейс", "осмотреть кейс", "осмотр кейс", "крафты ", "крафт ", "уничтожение",
)


def is_command_text(text: str) -> bool:
    t = text.lower()
    if t in FIXED_COMMANDS:
        return True
    return any(t.startswith(p) for p in PREFIX_COMMANDS)


# ---------- Алиасы команд ----------
# Полный явный словарь "фраза целиком (нижний регистр) -> канонический текст команды".
# Строится из групп синонимов, но раскладывается только в те КОНКРЕТНЫЕ фразы, которые реально
# соответствуют существующим хендлерам — так синонимы никогда не пересекаются с другими командами
# ("б"/"п" в "дать б"/"продать б", "кейсы" как отдельная команда от "кейс", и т.п.).

_TOP_WORDS = ["топ", "топчик", "ладдер", "лидеры", "лиддеры", "рейтинг", "top", "ladder", "lider", "liders", "leaders", "rating"]
_LEG_WORDS = ["ног", "ноги", "ногой", "leg", "legs", "foot", "feet"]
_COIN_WORDS = ["коин", "коины", "коинов", "монета", "монеты", "монет", "coin", "coins", "money", "валюта"]
_EVO_WORDS = ["эво", "эволюция", "эволюции", "эволюционировать", "evolution", "evolutions", "evo"]
_BALANCE_WORDS = ["баланс", "бал", "кошелек", "кошелёк", "деньги", "bal", "balance", "cash", "счет", "счёт"]
_REBIRTH_WORDS = ["перерождение", "перерождения", "ребёрт", "реберт", "ребёрты", "ребирты", "рб", "rebirth", "rb", "rebith"]
_CASE_WORDS = ["кейс", "сундук", "коробка", "case", "box"]
_CASES_WORDS = ["кейсы", "сундуки", "коробки", "cases", "boxes"]
_VIP_WORDS = ["вип", "vip", "випка", "premium", "премиум"]
_EXCHANGE_WORDS = ["обменять", "обмен", "обменник", "свап", "swap", "exchange"]
_HELP_WORDS = ["помощь", "команды", "хелп", "help", "cmds", "commands"]

ALIAS_PHRASES = {}


def _register_phrases(canon: str, words):
    for w in words:
        ALIAS_PHRASES[w.lower()] = canon


# Одиночные слова-команды (весь текст = ровно одно из этих слов)
_register_phrases("вип", _VIP_WORDS)
_register_phrases("баланс", _BALANCE_WORDS)
_register_phrases("перерождение", _REBIRTH_WORDS)
_register_phrases("эволюция", _EVO_WORDS)
_register_phrases("кейс", _CASE_WORDS)
_register_phrases("кейсы", _CASES_WORDS)
_register_phrases("помощь", _HELP_WORDS)
ALIAS_PHRASES["моя ношка"] = "моя нога"
ALIAS_PHRASES["моя ножка"] = "моя нога"
ALIAS_PHRASES["моя ноги"] = "моя нога"

# "топ <термин>" и "гл топ <термин>" — декартово произведение топ-синонимов на синонимы термина
for _top in _TOP_WORDS:
    for _leg in _LEG_WORDS:
        ALIAS_PHRASES[f"{_top} {_leg}"] = "топ ног"
        ALIAS_PHRASES[f"гл {_top} {_leg}"] = "гл топ ног"
        ALIAS_PHRASES[f"{_top} {_leg} вся"] = "топ ноги вся"
    for _coin in _COIN_WORDS:
        ALIAS_PHRASES[f"{_top} {_coin}"] = "топ коин"
        ALIAS_PHRASES[f"гл {_top} {_coin}"] = "гл топ коин"
        ALIAS_PHRASES[f"{_top} {_coin} вся"] = "топ коин вся"
    for _evo in _EVO_WORDS:
        ALIAS_PHRASES[f"{_top} {_evo}"] = "топ эво"
        ALIAS_PHRASES[f"гл {_top} {_evo}"] = "гл топ эво"
        ALIAS_PHRASES[f"{_top} {_evo} вся"] = "топ эво вся"
    for _rb in _REBIRTH_WORDS:
        ALIAS_PHRASES[f"{_top} {_rb}"] = "топ очкп"
        ALIAS_PHRASES[f"гл {_top} {_rb}"] = "гл топ очкп"
        ALIAS_PHRASES[f"{_top} {_rb} вся"] = "топ очкп вся"
    ALIAS_PHRASES[f"{_top} вся"] = "топ вся"
# сами канонические фразы не должны затираться (на случай, если слово входит в несколько списков)
ALIAS_PHRASES.pop("топ топ", None)


def normalize_alias_text(text: str) -> str:
    """Заменяет известную фразу-алиас на канонический текст команды. Не трогает команды
    с параметрами (числа, названия предметов, юзернеймы) — под них есть отдельная токенная
    замена ниже (normalize_alias_prefix), не полнофразовая."""
    if not text:
        return text
    stripped = text.strip()
    if not stripped:
        return text
    lowered = stripped.lower()
    return ALIAS_PHRASES.get(lowered, text)


# ---------- Алиасы для команд с параметрами (дать/снять/передать/обменять/кейс N и т.д.) ----------
# Тут заменяем только ПЕРВОЕ слово (глагол/термин сразу после "!дать"/"!снять"/само по себе),
# аргументы (числа, юзернеймы, названия предметов) не трогаем.
_PARAM_TERM_TO_CANON = {}
for _w in _LEG_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "ног"
for _w in _COIN_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "коин"
for _w in _EVO_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "эво"
for _w in _REBIRTH_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "очкп"
for _w in _EXCHANGE_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "обменять"
for _w in _CASE_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "кейс"

# Защищённые токены — никогда не алиасятся, даже если случайно совпали с чем-то (бустер "б"/предмет "п")
_PARAM_PROTECTED = {"б", "п"}


_CASE_WORDS_SET = {w.lower() for w in _CASE_WORDS}


def normalize_case_number(text: str) -> str:
    """'сундук 2' / 'box 2' -> 'кейс 2'. Первое слово само является термином кейса,
    число (аргумент) не трогаем."""
    if not text:
        return text
    stripped = text.strip()
    if not stripped:
        return text
    parts = stripped.split(" ", 1)
    if len(parts) != 2:
        return text
    first, rest = parts[0].lower(), parts[1]
    if first in _CASE_WORDS_SET and first != "кейс" and rest.strip().isdigit():
        return "кейс " + rest
    return text


def normalize_alias_prefix(text: str) -> str:
    """Для команд вида '<преф> <термин> <аргументы...>' заменяет только термин сразу после
    известного префикса (!дать/!снять/дать/продать/обменять/кейс), не трогая аргументы."""
    if not text:
        return text
    stripped = text.strip()
    if not stripped:
        return text

    lowered = stripped.lower()
    known_prefixes = ("!дать ", "!снять ", "дать ")
    matched_prefix = None
    for p in known_prefixes:
        if lowered.startswith(p):
            matched_prefix = p
            break
    if matched_prefix is None:
        return text

    original_prefix = stripped[:len(matched_prefix)]
    rest = stripped[len(matched_prefix):]
    if not rest:
        return text

    rest_words = rest.split(" ", 1)
    term = rest_words[0]
    tail = rest_words[1] if len(rest_words) > 1 else ""
    lterm = term.lower()

    if lterm in _PARAM_PROTECTED:
        return text
    if lterm not in _PARAM_TERM_TO_CANON:
        return text

    canon_term = _PARAM_TERM_TO_CANON[lterm]
    # спецслучай: реальный хендлер несимметричен — "!дать ног" / "!снять ноги" (разные словоформы)
    if matched_prefix == "!снять " and canon_term == "ног":
        canon_term = "ноги"

    if canon_term == lterm:
        return text  # уже канонический вид, нечего менять

    new_text = original_prefix + canon_term + (" " + tail if tail else "")
    return new_text


def normalize_exchange_suffix(text: str) -> str:
    """'обменять 10 монет' / 'обменять 10 coin' -> 'обменять 10 коин'. Не трогает 'обменять 10'
    (старая команда очки->монеты, без термина в хвосте)."""
    if not text:
        return text
    stripped = text.strip()
    lowered = stripped.lower()
    if not lowered.startswith("обменять "):
        return text
    rest = stripped[len("обменять "):].strip()
    if not rest:
        return text
    parts = rest.split(" ", 1)
    if len(parts) != 2:
        return text  # только число, без термина — не трогаем (старая команда)
    amount_word, term = parts[0], parts[1].strip()
    if not _AMOUNT_TOKEN_RE.match(amount_word):
        return text
    lterm = term.lower()
    if lterm not in _PARAM_TERM_TO_CANON:
        return text
    canon_term = _PARAM_TERM_TO_CANON[lterm]
    if canon_term != "коин" or canon_term == lterm:
        return text
    return f"обменять {amount_word} {canon_term}"


def apply_command_aliases(text: str) -> str:
    """Единая точка входа: применяет все виды алиасинга по порядку. Возвращает исходный текст,
    если ни один нормализатор не нашёл, что менять (в т.ч. для обычных сообщений с ногами 🦵/🦿 —
    там нет алиасов, и текст останется как есть)."""
    if not text:
        return text
    result = normalize_alias_text(text)
    if result != text:
        return result
    result = normalize_case_number(text)
    if result != text:
        return result
    result = normalize_exchange_suffix(text)
    if result != text:
        return result
    result = normalize_alias_prefix(text)
    return result


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


def strip_premium_emoji(text: str) -> str:
    """Убирает все <tg-emoji> обёртки из готового текста, оставляя фолбэк-символы."""
    return TG_EMOJI_RE.sub(lambda m: m.group(1), text or "")


async def safe_reply(message: Message, text: str, reply_markup=None):
    """Как message.reply(), но если Telegram отклонил сообщение из-за невалидного
    emoji-id в premium-эмодзи (битый/непризнанный custom_emoji_id) — повторяет
    отправку с обычными эмодзи вместо того, чтобы command тихо "не открывался"."""
    try:
        return await message.reply(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        return await message.reply(strip_premium_emoji(text), reply_markup=reply_markup)


async def safe_edit_text(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        return await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        return await callback.message.edit_text(strip_premium_emoji(text), reply_markup=reply_markup)


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


def level_threshold(level: int, evolution_level: int, rebirth_count: int = 0) -> int:
    hardness = (1 + EVO_HARDNESS_RATE * evolution_level) * rebirth_hardness_multiplier(rebirth_count)
    return round(base_level_threshold(level) * hardness)


def get_level_index(score: int, evolution_level: int = 0, rebirth_count: int = 0) -> int:
    lo, hi = 0, 200000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if level_threshold(mid, evolution_level, rebirth_count) <= score:
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


def next_level_text(score: int, evolution_level: int, rebirth_count: int = 0) -> str:
    level = get_level_index(score, evolution_level, rebirth_count)
    if level >= MGG_MEGA_LEVEL:
        return "Ты достиг абсолютного предела ноги — дальше только легенды 🌌"
    nxt = level_threshold(level + 1, evolution_level, rebirth_count)
    return f"До {level + 1} уровня осталось {nxt - score} очков"


def equipped_slots_max(upgrades: dict) -> int:
    return 1 + upgrade_level(upgrades, "equip_slots")  # база 1 слот + купленные уровни прокачки (0/1/2 -> 1/2/3 слота)


def parse_equipped(equipped_str: str) -> list:
    """Очередь экипированных предметов: индекс 0 = надет раньше всех (первым вылетит при переполнении)."""
    return [k for k in (equipped_str or "").split(",") if k]


def format_equipped(items: list) -> str:
    return ",".join(items)


def equip_item(equipped_str: str, item_key: str, max_slots: int) -> list:
    """Добавляет item_key в конец очереди. Если он уже был в очереди — переставляет в конец
    (эквивалент «снял и заново надел»). При переполнении вылетает элемент с индекса 0."""
    items = [k for k in parse_equipped(equipped_str) if k != item_key]
    items.append(item_key)
    while len(items) > max_slots:
        items.pop(0)
    return items


def unequip_item(equipped_str: str, item_key: str) -> list:
    """Убирает item_key из очереди, если он там есть."""
    return [k for k in parse_equipped(equipped_str) if k != item_key]


def get_multiplier(evolution_level: int, active_items, vip_active: bool, upgrades: dict = None) -> float:
    mult = 1.0
    if evolution_level >= 2:
        mult += EVO_BOOST_STEP
    if evolution_level >= 3:
        mult += EVO_BOOST_STEP * (evolution_level - 2)
    for item_key in _normalize_active_items(active_items):
        if item_key in ITEMS:
            mult += ITEMS[item_key][2] / 100
    if vip_active:
        mult += VIP_BOOST
    if upgrades:
        mult += 0.05 * upgrade_level(upgrades, "booster")
    return mult


def _normalize_active_items(active_items):
    """Принимает список/кортеж ключей предметов, либо None. Строки сюда не передаём —
    для строки очереди сначала вызывай parse_equipped()."""
    if active_items is None:
        return []
    if isinstance(active_items, str):
        # подстраховка на случай передачи "сырого" item_key одной строкой
        return [active_items] if active_items in ITEMS else parse_equipped(active_items)
    return [k for k in active_items if k]


def total_flat_bonus(active_items) -> int:
    return sum(ITEM_FLAT_BONUS.get(k, 0) for k in _normalize_active_items(active_items))


def parse_hidden(hidden_str: str) -> set:
    return set(h for h in (hidden_str or "").split(",") if h)


def parse_upgrades(upgrades_str: str) -> dict:
    result = {}
    for part in (upgrades_str or "").split(","):
        if not part or ":" not in part:
            continue
        key, _, lvl = part.partition(":")
        if key in UPGRADES:
            try:
                result[key] = int(lvl)
            except ValueError:
                pass
    return result


def format_upgrades(upgrades: dict) -> str:
    return ",".join(f"{k}:{v}" for k, v in upgrades.items() if v > 0)


def upgrade_level(upgrades: dict, key: str) -> int:
    return upgrades.get(key, 0)


def upgrade_next_cost(key: str, upgrades: dict):
    cfg = UPGRADES[key]
    if cfg.get("wip") or cfg["cost"] is None:
        return None
    level = upgrade_level(upgrades, key)
    if level >= cfg["max_level"]:
        return None
    return cfg["cost"](level + 1)


async def claim_offline_auto_farm(user_id: int, row) -> tuple:
    """Начисляет оффлайн-доход от Авто-Фермы НОГИ/КОИНЫ по разнице времени.
    Возвращает (legs_gained, coins_gained, new_score, new_coins)."""
    upgrades = parse_upgrades(row[16])
    legs_lvl = upgrade_level(upgrades, "auto_farm_legs")
    coins_lvl = upgrade_level(upgrades, "auto_farm_coins")
    score, coins = row[2], row[5]
    last_claim = row[17] or 0
    now = int(time.time())

    if not legs_lvl and not coins_lvl:
        # нечего копить — просто обновим метку, чтобы не копился долг на будущее
        if not last_claim:
            await db_exec("UPDATE users SET last_auto_claim = ? WHERE user_id = ?", (now, user_id))
        return 0, 0, score, coins

    if not last_claim:
        await db_exec("UPDATE users SET last_auto_claim = ? WHERE user_id = ?", (now, user_id))
        return 0, 0, score, coins

    elapsed = max(0, now - last_claim)
    legs_gained = 0
    coins_gained = 0

    if legs_lvl:
        amount, per_seconds = AUTO_FARM_LEGS_RATES[legs_lvl]
        legs_gained = int(elapsed // per_seconds) * amount
    if coins_lvl:
        amount, per_seconds = AUTO_FARM_COINS_RATES[coins_lvl]
        coins_gained = int(elapsed // per_seconds) * amount

    if legs_gained == 0 and coins_gained == 0:
        return 0, 0, score, coins

    new_score = score + legs_gained
    new_coins = coins + coins_gained
    await db_exec(
        "UPDATE users SET score = ?, coins = ?, total_farmed = total_farmed + ?, last_auto_claim = ? WHERE user_id = ?",
        (new_score, new_coins, legs_gained, now, user_id),
    )
    return legs_gained, coins_gained, new_score, new_coins


def rebirth_hardness_multiplier(rebirth_count: int) -> float:
    return 1 + REBIRTH_HARDNESS_STEP * rebirth_count


def farm_yield_multiplier(upgrades: dict) -> float:
    return 1 + 0.10 * upgrade_level(upgrades, "farm_yield")


def farm_cd_seconds(upgrades: dict, active_items=None, has_time_particle: bool = False) -> int:
    reduction = 120 * upgrade_level(upgrades, "farm_cd")
    cooldown = max(60, FARM_COOLDOWN - reduction)  # не даём КД уйти в ноль/минус

    tier = get_active_unique_tier(active_items) if active_items is not None else None
    if tier == "god_essence":
        cooldown = cooldown / GOD_ESSENCE_FARM_SPEED - GOD_ESSENCE_TIMER_CUT
    elif has_time_particle:
        cooldown = cooldown / TIME_PARTICLE_FARM_SPEED

    return max(30, round(cooldown))


def booster_upgrade_multiplier(upgrades: dict) -> float:
    return 1 + 0.05 * upgrade_level(upgrades, "booster")


def case_discount(upgrades: dict) -> float:
    return 0.10 * upgrade_level(upgrades, "discount")


def case_price_with_discount(base_price: int, upgrades: dict) -> int:
    discount = case_discount(upgrades)
    return max(1, round(base_price * (1 - discount)))


def sell_bonus_coins(upgrades: dict) -> int:
    return 2 * upgrade_level(upgrades, "sell_boost")


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


def case_drop_table(case_num: int) -> list:
    """Список (item_key, эмодзи, имя, буст%, шанс_в_процентах) для конкретного кейса,
    отсортированный по убыванию шанса."""
    pool = CASES[case_num]["pool"]
    weights = [ITEMS[k][3] for k in pool]
    total = sum(weights)
    rows = []
    for k, w in zip(pool, weights):
        emoji, name, percent, _ = ITEMS[k]
        chance = round(w / total * 100, 2) if total else 0
        rows.append((k, emoji, name, percent, chance))
    rows.sort(key=lambda r: r[4], reverse=True)
    return rows


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
    "cases_opened, total_farmed, last_bonus, bonus_streak, levelup_notify, vip_until, hidden_badges, "
    "rebirth_points, rebirth_count, upgrades, last_auto_claim, equipped_items"
)
# Индексы полей выше при обращении по row[...]:
#  0 user_id, 1 username, 2 score, 3 evolution_level, 4 last_farm, 5 coins, 6 active_item (устарело, не используется),
#  7 cases_opened, 8 total_farmed, 9 last_bonus, 10 bonus_streak, 11 levelup_notify, 12 vip_until,
#  13 hidden_badges, 14 rebirth_points, 15 rebirth_count, 16 upgrades (строка "key:lvl,key:lvl"), 17 last_auto_claim,
#  18 equipped_items — очередь экипированных предметов "key1,key2,key3" (индекс 0 = надет раньше всех,
#     последний = надет позже всех; новый/повторный клик уходит в конец, при переполнении вылетает индекс 0)


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
        "ALTER TABLE users ADD COLUMN rebirth_points INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN rebirth_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN upgrades TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN last_auto_claim INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN active_item2 TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN equipped_items TEXT DEFAULT ''",
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
        now = int(time.time())
        return (user_id, username, 0, 0, 0, 0, None, 0, 0, 0, 0, 1, 0, "", 0, 0, "", now, "")
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


async def apply_farm_bonuses(user_id: int, active_items, inventory_map: dict) -> dict:
    """Считает все монетные пассивки (Странная монета, Тёплая свеча, Монета боготворства) одним
    общим числом монет + гарант Эссенции Бога (монеты/очки перерождения/эволюция). Один UPDATE.
    Возвращает {'coins': N, 'rebirth': N, 'evo': N, 'is_god': bool}."""
    coin_bonus = 0
    if inventory_map.get("strange_coin", 0) > 0:
        coin_bonus += 1
    if inventory_map.get("warm_candle", 0) > 0:
        coin_bonus += 1
    if inventory_map.get("devotion_coin", 0) > 0:
        coin_bonus += 10
        if random.random() < 0.10:
            coin_bonus += 20

    rebirth_bonus = 0
    evo_bonus = 0
    is_god = get_active_unique_tier(active_items) == "god_essence"
    if is_god:
        coin_bonus += random.randint(1, 200)
        rebirth_bonus += random.randint(1, 5)
        evo_bonus += 1

    if coin_bonus or rebirth_bonus or evo_bonus:
        await db_exec(
            "UPDATE users SET coins = coins + ?, rebirth_points = rebirth_points + ?, evolution_level = evolution_level + ? "
            "WHERE user_id = ?",
            (coin_bonus, rebirth_bonus, evo_bonus, user_id),
        )
    return {"coins": coin_bonus, "rebirth": rebirth_bonus, "evo": evo_bonus, "is_god": is_god}


async def apply_vase_proc(user_id: int, inventory_map: dict) -> str:
    """Проки пассивных ваз при фарме ног. Срабатывает только самая сильная имеющаяся ваза."""
    if inventory_map.get("godly_vase", 0) > 0:
        roll = random.random()
        if roll < 0.01:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 5, evolution_level = evolution_level + 5 WHERE user_id = ?", (user_id,))
            return "\n🏺 Боготворная ваза взорвалась удачей: +5🉑 +5 эволюций!"
        if roll < 0.06:
            await db_exec("UPDATE users SET evolution_level = evolution_level + 1 WHERE user_id = ?", (user_id,))
            return "\n🏺 Боготворная ваза: +1 эволюция!"
        if roll < 0.16:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 1 WHERE user_id = ?", (user_id,))
            return "\n🏺 Боготворная ваза: +1🉑!"
        return ""
    if inventory_map.get("golden_vase", 0) > 0:
        roll = random.random()
        if roll < 0.01:
            await db_exec("UPDATE users SET evolution_level = evolution_level + 1 WHERE user_id = ?", (user_id,))
            return "\n🏺 Золотая ваза: +1 эволюция!"
        if roll < 0.06:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 1 WHERE user_id = ?", (user_id,))
            return "\n🏺 Золотая ваза: +1🉑!"
        return ""
    if inventory_map.get("old_vase", 0) > 0:
        if random.random() < 0.01:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 1 WHERE user_id = ?", (user_id,))
            return "\n🏺 Старая ваза: +1🉑!"
        return ""
    return ""


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
            f"SELECT username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges, rebirth_points, rebirth_count "
            f"FROM users ORDER BY {order_column} DESC LIMIT ?",
            (limit,),
        )
    else:
        rows = await db_query(
            f"""SELECT u.username, u.score, u.evolution_level, u.coins, u.cases_opened, u.total_farmed, u.vip_until, u.hidden_badges, u.rebirth_points, u.rebirth_count
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


class AliasNormalizeMiddleware(BaseMiddleware):
    """Переписывает message.text на канонический вид команды ДО того, как текст попадёт
    в остальные middleware/хендлеры (is_command_text, ThrottleMiddleware, сами @dp.message)."""
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.text:
            new_text = apply_command_aliases(event.text)
            if new_text != event.text:
                event = event.model_copy(update={"text": new_text})
        return await handler(event, data)


class PrivateBlockMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        chat = get_chat(event)
        if chat is not None and chat.type == "private":
            user = event.from_user
            if not (user and (user.username or "").lower() == ADMIN_USERNAME.lower()):
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer()
                    except Exception:
                        pass
                return
        return await handler(event, data)


class TrackMembershipMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.chat.type in ("group", "supergroup") and event.from_user:
            await track_membership(event.from_user.id, event.chat.id)
        return await handler(event, data)


class ThrottleMiddleware(BaseMiddleware):
    """Троттлинг для текстовых команд."""
    def __init__(self, rate: float = 1.5):
        self.rate = rate
        self.last_call = {}

    async def __call__(self, handler, event, data):
        user_id = event.from_user.id if event.from_user else None
        if user_id is None:
            return await handler(event, data)

        text = getattr(event, "text", None)
        if not text or not is_command_text(text):
            return await handler(event, data)

        now = time.monotonic()
        key = (user_id, "cmd")
        if now - self.last_call.get(key, 0) < self.rate:
            return
        self.last_call[key] = now
        return await handler(event, data)


class CallbackThrottleMiddleware(BaseMiddleware):
    """Троттлинг для инлайн-кнопок. Короткий кулдаун (350-500мс) и, что критично,
    ВСЕГДА отвечает на callback_query — иначе Telegram держит кнопку в состоянии
    "загрузка" до собственного таймаута, что выглядит как зависшая/незажимаемая кнопка."""
    def __init__(self, rate: float = 0.4):
        self.rate = rate
        self.last_call = {}

    async def __call__(self, handler, event: CallbackQuery, data):
        user_id = event.from_user.id if event.from_user else None
        if user_id is None:
            return await handler(event, data)

        now = time.monotonic()
        key = (user_id, event.data)  # троттлим повтор ТОЙ ЖЕ кнопки, а не любых кнопок подряд
        if now - self.last_call.get(key, 0) < self.rate:
            try:
                await event.answer()  # гасим "часики" немедленно, без show_alert — не мешаем игроку
            except Exception:
                pass
            return
        self.last_call[key] = now
        return await handler(event, data)


dp.message.outer_middleware(AliasNormalizeMiddleware())
dp.message.middleware(PrivateBlockMiddleware())
dp.callback_query.middleware(PrivateBlockMiddleware())
dp.message.middleware(TrackMembershipMiddleware())
dp.message.middleware(ThrottleMiddleware(1.5))
dp.callback_query.middleware(CallbackThrottleMiddleware(0.4))

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
                                  evolution_level: int, notify: bool, rebirth_count: int = 0):
    if not notify:
        return
    old_level = get_level_index(old_score, evolution_level, rebirth_count)
    new_level = get_level_index(new_score, evolution_level, rebirth_count)
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


VIP_STARS_PRICE = 15
VIP_FOREVER_SECONDS = 100 * 365 * 86400  # "навсегда" — технически 100 лет


def buy_vip_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"⭐️ Купить VIP навсегда за {VIP_STARS_PRICE} звёзд", callback_data=f"buy_vip:{user_id}")
    ]])


@dp.message(F.text.lower() == "вип")
async def vip_info_command(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    vip_until = row[12]

    if is_vip_active(vip_until):
        await message.reply("У тебя уже есть VIP-статус! 💎")
        return

    await message.reply(
        f"💎 VIP даёт постоянный буст +{round(VIP_BOOST * 100)}% к добыче.\n"
        f"Можно купить прямо в боте за {VIP_STARS_PRICE} звёзд Telegram — выдаётся навсегда.",
        reply_markup=buy_vip_keyboard(user_id),
    )


@dp.callback_query(F.data.startswith("buy_vip:"))
async def buy_vip_invoice(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer("Это не твоя покупка!", show_alert=True)
        return

    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title="VIP статус навсегда",
        description=f"Постоянный буст +{round(VIP_BOOST * 100)}% к добыче ноги.",
        payload=f"vip:{owner_id}",
        currency="XTR",
        prices=[LabeledPrice(label="VIP навсегда", amount=VIP_STARS_PRICE)],
        provider_token="",  # для Telegram Stars provider_token не нужен
    )
    await callback.answer()


@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    payload = pre_checkout_query.invoice_payload or ""
    if payload.startswith("vip:"):
        await pre_checkout_query.answer(ok=True)
    else:
        await pre_checkout_query.answer(ok=False, error_message="Неизвестный товар.")


@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload or ""
    if not payload.startswith("vip:"):
        return
    target_id = int(payload.split(":")[1])
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(target_id, username)

    was_vip_before = is_vip_active(row[12])
    new_vip_until = int(time.time()) + VIP_FOREVER_SECONDS
    await db_exec("UPDATE users SET vip_until = ? WHERE user_id = ?", (new_vip_until, target_id))
    if not was_vip_before:
        await add_item(target_id, "vip_charm")

    await message.reply("💎 Оплата прошла! VIP-статус выдан навсегда. Спасибо за поддержку!")


@dp.message(F.text.lower() == "помощь")
async def help_command(message: Message):
    await message.reply(
        "📜 <b>Команды:</b>\n"
        "● моя нога — твой профиль\n"
        "● ферма — фарм очков (по кулдауну)\n"
        "● топ ног / топ коин / топ эво / топ очкп — топы (+ «гл» для глобальных)\n"
        "● инвентарь — бустеры и предметы\n"
        "● кейс, кейсы — открытие кейсов\n"
        "● эволюция — перейти на след. уровень эволюции\n"
        "● перерождение — сброс ног/эво за 🉑\n"
        "● апгрейд / прокачка — меню прокачки за 🉑\n"
        "● баланс — монеты и 🉑\n"
        "● обменять <число> — очки в монеты\n"
        "● вип — купить VIP-статус за звёзды\n"
        "● крафты [предмет] — доступные рецепты крафта\n"
        "● продать б/п <название> — продать бустер/предмет\n"
        "● уничтожение б/п <название> — уничтожить без награды\n"
        "● бонус — ежедневный бонус\n"
        "● бейджи — управление бейджами"
    )


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
    rebirth_count = row[15]
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    vip_active = is_vip_active(vip_until)

    flat_bonus = total_flat_bonus(active_items)
    limits = active_farm_limits(active_items)

    legs = min(text.count("🦵"), limits["leg_limit"])
    gained = legs * LEG_POINT

    mek = 0
    if evolution_level >= 1:
        mek = min(text.count("🦿"), limits["mek_limit"])
        gained += mek * MEK_POINT

    # 🌌 и ⭐️ — НЕ отдельные очки, а множители к итогу фарма (работают, только пока
    # экипирован соответствующий бустер — иначе их лимит 0 и они не учитываются).
    galaxy = min(text.count("🌌"), limits["galaxy_limit"])
    star = min(text.count("⭐️"), limits["star_limit"])

    if gained == 0:
        return

    gained += flat_bonus  # гарант-бонус применяется один раз к итогу, а не за каждую ногу
    gained = round(gained * farm_yield_multiplier(upgrades))

    mult = get_multiplier(evolution_level, active_items, vip_active, upgrades)
    event_mult = 2 if await is_event_active() else 1
    total = round(gained * mult * event_mult)
    if galaxy:
        total = round(total * (1 + 0.20 * galaxy))   # 🌌: +20% к итогу за каждую штуку
    if star:
        total = round(total * (2 ** star))            # ⭐️: ×2 к итогу за каждую штуку
    new_score = score + total

    await db_exec(
        "UPDATE users SET score = ?, total_farmed = total_farmed + ? WHERE user_id = ?",
        (new_score, total, user_id),
    )

    await maybe_announce_levelup(message, username, score, new_score, evolution_level, bool(levelup_notify), rebirth_count)

    inv = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv}
    vase_text = await apply_vase_proc(user_id, inventory_map)
    bonus = await apply_farm_bonuses(user_id, active_items, inventory_map)

    now = time.monotonic()
    chat_id = message.chat.id
    if now - _last_leg_reply.get(chat_id, 0) < LEG_REPLY_COOLDOWN:
        return
    _last_leg_reply[chat_id] = now

    parts = f"+{legs}🦵"
    if mek:
        parts += f" +{mek}🦿"
    if galaxy:
        parts += f" +{galaxy}🌌"
    if star:
        parts += f" +{star}⭐️"

    coin_text = f" +{bonus['coins']}🪙" if bonus["coins"] else ""

    if bonus["is_god"]:
        god_extra = f" +{bonus['rebirth']}🉑 +{bonus['evo']}эво" if (bonus["rebirth"] or bonus["evo"]) else ""
        await safe_reply(
            message,
            f"{GOD_ESSENCE_FLAVOR} {parts} → +{total} очков{coin_text} {god_extra}(Всего: {new_score}){vase_text}"
        )
        return

    await message.reply(
        f"Лютый рофл засчитан! {parts} → +{total} очков{coin_text} (Всего: {new_score}){vase_text}"
    )


@dp.message(F.text.lower() == "моя нога")
async def my_profile(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level, coins, active_item = row[2], row[3], row[5], row[6]
    vip_until = row[12]
    rebirth_points, rebirth_count = row[14], row[15]
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    vip_active = is_vip_active(vip_until)

    level = get_level_index(score, evolution_level, rebirth_count)
    emoji, name, show_level = get_level_visual(level)
    nxt = next_level_text(score, evolution_level, rebirth_count)
    mult = get_multiplier(evolution_level, active_items, vip_active, upgrades)
    flat_bonus = total_flat_bonus(active_items)

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
    rebirth_line = f"● Перерождений: {rebirth_count} (🉑 {rebirth_points})\n" if rebirth_count else ""
    equipped_names = [ITEMS[k][1] for k in (active_items) if k and k in ITEMS]
    equip_line = f"● Экипировано: {', '.join(equipped_names)}\n" if equipped_names else ""

    text = (
        f"👣 <b>ТВОЯ ЛЮТАЯ НОГОСТЬ:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"● Очки: <code>{score}</code>\n"
        f"● Монеты: <code>{coins}</code> 🪙\n"
        f"● Вид ног: {emoji}{name_part}\n"
        f"{lvl_line}"
        f"● Уровень эволюции: {evolution_level}\n"
        f"{rebirth_line}"
        f"{equip_line}"
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
    rebirth_count = row[15] if len(row) > 15 else 0
    hidden = parse_hidden(row[13] if len(row) > 13 else "")
    vip_active = is_vip_active(vip_until)
    level = get_level_index(score, evolution_level, rebirth_count)
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
        f"● VIP: {vip_text}"
    )
    await message.reply(text)


async def send_legs_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "score")

    if not rows:
        await message.reply("В топе пока пусто, никто еще не кинул ногу... 🧍")
        return

    text = f"🏆 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges, rebirth_points, rebirth_count) in enumerate(rows, 1):
        level = get_level_index(score, evolution_level, rebirth_count)
        emoji, name, show_level = get_level_visual(level)
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_hidden(hidden_badges))
        lvl_part = f" ({level} лвл)" if show_level else ""
        name_part = f" {esc(name)}" if name else ""
        text += f"{i}. {esc(username)}{badges} — <code>{score}</code>\n   └ {emoji}{name_part}{lvl_part} · эво {evolution_level}\n\n"

    await message.reply(text)


async def send_evo_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "evolution_level")

    if not rows:
        await message.reply("В топе пока пусто.")
        return

    text = f"🎆 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges, rebirth_points, rebirth_count) in enumerate(rows, 1):
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_hidden(hidden_badges))
        text += f"{i}. {esc(username)}{badges} — эво {evolution_level} ({score} очков)\n"

    await message.reply(text)


async def send_coin_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "coins")

    if not rows:
        await message.reply("В топе пока пусто.")
        return

    text = f"🪙 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges, rebirth_points, rebirth_count) in enumerate(rows, 1):
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_hidden(hidden_badges))
        text += f"{i}. {esc(username)}{badges} — {coins} 🪙\n"

    await message.reply(text)


async def send_rebirth_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "rebirth_points")

    if not rows:
        await message.reply("В топе пока пусто.")
        return

    text = f"🉑 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges, rebirth_points, rebirth_count) in enumerate(rows, 1):
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_hidden(hidden_badges))
        text += f"{i}. {esc(username)}{badges} — {rebirth_points} 🉑 (перерождений: {rebirth_count})\n"

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


@dp.message(F.text.lower() == "топ очкп")
async def top_rebirth_local(message: Message):
    await send_rebirth_top(message, message.chat.id, "ТОП ОЧКОВ ПЕРЕРОЖДЕНИЯ ЭТОГО ЧАТА")


@dp.message(F.text.lower() == "гл топ очкп")
async def top_rebirth_global(message: Message):
    await send_rebirth_top(message, None, "ТОП ОЧКОВ ПЕРЕРОЖДЕНИЯ ВЕЗДЕ")


@dp.message(F.text.lower() == "топ ноги вся")
async def top_legs_global_suffix(message: Message):
    await send_legs_top(message, None, "ТОП-10 НОГ ВЕЗДЕ")


@dp.message(F.text.lower() == "топ коин вся")
async def top_coin_global_suffix(message: Message):
    await send_coin_top(message, None, "ТОП МОНЕТ ВЕЗДЕ")


@dp.message(F.text.lower() == "топ эво вся")
async def top_evo_global_suffix(message: Message):
    await send_evo_top(message, None, "ТОП ЭВОЛЮЦИЙ ВЕЗДЕ")


@dp.message(F.text.lower() == "топ очкп вся")
async def top_rebirth_global_suffix(message: Message):
    await send_rebirth_top(message, None, "ТОП ОЧКОВ ПЕРЕРОЖДЕНИЯ ВЕЗДЕ")


@dp.message(F.text.lower().in_({"топ вся", "гл топ"}))
async def top_overall_global(message: Message):
    await send_legs_top(message, None, "ОБЩИЙ ТОП ВЕЗДЕ (по очкам ноги)")


@dp.message(F.text.lower().in_({"ферма", "фарма"}))
async def farm(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    now = int(time.time())

    row = await ensure_user(user_id, username)
    score, evolution_level, active_item = row[2], row[3], row[6]
    last_farm, levelup_notify, vip_until = row[4], row[11], row[12]
    rebirth_count = row[15]
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    vip_active = is_vip_active(vip_until)

    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}
    has_time_particle = inventory_map.get("time_particle", 0) > 0

    cooldown = farm_cd_seconds(upgrades, active_items, has_time_particle)
    if now - last_farm < cooldown:
        left = cooldown - (now - last_farm)
        m, s = divmod(left, 60)
        await message.reply(f"Ферма на кулдауне ⏳ Осталось {m} мин {s} сек")
        return

    # оффлайн-доход от Авто-Фермы — начисляем при действии игрока
    auto_legs, auto_coins, score, _coins_after = await claim_offline_auto_farm(user_id, row)

    low, high = farm_range(evolution_level)
    mult = get_multiplier(evolution_level, active_items, vip_active, upgrades)
    event_mult = 2 if await is_event_active() else 1
    gained = round(random.randint(low, high) * farm_yield_multiplier(upgrades) * mult * event_mult)
    new_score = score + gained

    await db_exec(
        "UPDATE users SET score = ?, last_farm = ?, total_farmed = total_farmed + ? WHERE user_id = ?",
        (new_score, now, gained, user_id),
    )

    vase_text = await apply_vase_proc(user_id, inventory_map)
    bonus = await apply_farm_bonuses(user_id, active_items, inventory_map)

    await maybe_announce_levelup(message, username, score, new_score, evolution_level, bool(levelup_notify), rebirth_count)
    auto_text = ""
    if auto_legs or auto_coins:
        bits = []
        if auto_legs:
            bits.append(f"+{auto_legs} очков")
        if auto_coins:
            bits.append(f"+{auto_coins} 🪙")
        auto_text = f"\n⚙️ Авто-Ферма накопила: {', '.join(bits)}"

    coin_text = f" +{bonus['coins']}🪙" if bonus["coins"] else ""

    if bonus["is_god"]:
        god_extra = f" +{bonus['rebirth']}🉑 +{bonus['evo']}эво" if (bonus["rebirth"] or bonus["evo"]) else ""
        await safe_reply(
            message,
            f"{GOD_ESSENCE_FLAVOR} 🦵 +{gained} очков (Всего: {new_score}){coin_text}{god_extra}{auto_text}{vase_text}"
        )
        return

    await message.reply(
        f"Наферметил ногу! 🦵 +{gained} очков (Всего: {new_score}){coin_text}{auto_text}{vase_text}"
    )


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


@dp.message(F.text.regexp(REVERSE_EXCHANGE_RE))
async def reverse_exchange(message: Message):
    """обменять <кол-во> коин -> списывает коины, начисляет очки ног (1 коин = 150 очков)."""
    match = REVERSE_EXCHANGE_RE.match(message.text.strip())
    coins_wanted = parse_amount(match.group(1))
    if not coins_wanted or coins_wanted <= 0:
        await message.reply("Количество монет должно быть больше нуля.")
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, coins, evolution_level = row[2], row[5], row[3]
    rebirth_count = row[15]
    levelup_notify = row[11]

    if coins_wanted > coins:
        await message.reply(f"Недостаточно монет. У тебя {coins} 🪙.")
        return

    gained = coins_wanted * REVERSE_EXCHANGE_RATE
    new_coins = coins - coins_wanted
    new_score = score + gained

    await db_exec("UPDATE users SET score = ?, coins = ? WHERE user_id = ?", (new_score, new_coins, user_id))

    await maybe_announce_levelup(message, username, score, new_score, evolution_level, bool(levelup_notify), rebirth_count)
    await message.reply(f"Обменял {coins_wanted} 🪙 → +{gained} очков ноги (Всего очков: {new_score})")


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
    rebirth_count = row[15]

    spent = coins_wanted * EXCHANGE_RATE
    if spent > score:
        max_coins = score // EXCHANGE_RATE
        await message.reply(f"Недостаточно очков. У тебя {score}, максимум можешь обменять на {max_coins} 🪙.")
        return

    old_level = get_level_index(score, evolution_level, rebirth_count)
    new_score = score - spent
    new_level = get_level_index(new_score, evolution_level, rebirth_count)
    new_coins = coins + coins_wanted

    await db_exec("UPDATE users SET score = ?, coins = ? WHERE user_id = ?", (new_score, new_coins, user_id))

    warn = f"\n⚠️ Уровень упал с {old_level} до {new_level}!" if new_level < old_level else ""
    await message.reply(f"Обменял {spent} очков → +{coins_wanted} 🪙 монет (Всего монет: {new_coins}){warn}")


async def transfer_currency(message: Message, currency: str, amount: int):
    """currency: 'ног' или 'коин'. Общая логика для дать/передать <число> <валюта>."""
    if not message.reply_to_message:
        await message.reply("Ответь этой командой на сообщение того, кому передаёшь.")
        return

    receiver = message.reply_to_message.from_user
    sender = message.from_user
    if receiver.id == sender.id:
        await message.reply("Нельзя передать самому себе.")
        return

    sender_username = sender.username or sender.first_name or "Без имени"
    receiver_username = receiver.username or receiver.first_name or "Без имени"

    sender_row = await ensure_user(sender.id, sender_username)
    if sender_row[3] < 1:
        await message.reply("Передавать можно только с 1 уровня эволюции.")
        return

    if currency == "ног":
        if sender_row[2] < amount:
            await message.reply(f"Недостаточно очков. У тебя {sender_row[2]}.")
            return
        receiver_row = await ensure_user(receiver.id, receiver_username)
        new_sender = sender_row[2] - amount
        new_receiver = receiver_row[2] + amount
        await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_sender, sender.id))
        await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_receiver, receiver.id))
        await message.reply(f"{esc(sender_username)} передал {amount} очков игроку {esc(receiver_username)}.")
        await maybe_announce_levelup(message, receiver_username, receiver_row[2], new_receiver,
                                      receiver_row[3], bool(receiver_row[11]), receiver_row[15])
    else:  # коин
        if sender_row[5] < amount:
            await message.reply(f"Недостаточно монет. У тебя {sender_row[5]}.")
            return
        await ensure_user(receiver.id, receiver_username)
        await db_exec("UPDATE users SET coins = coins - ? WHERE user_id = ?", (amount, sender.id))
        await db_exec("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, receiver.id))
        await message.reply(f"{esc(sender_username)} передал {amount} 🪙 игроку {esc(receiver_username)}.")


async def transfer_item_direct(message: Message, item_query: str):
    """Прямой поиск предмета по вхождению строки, без разделения на бустеры/пассивки (п.2 ТЗ)."""
    if not message.reply_to_message:
        await message.reply("Ответь этой командой на сообщение того, кому передаёшь предмет.")
        return

    item_key = find_item_by_name(item_query)
    if not item_key:
        await message.reply(f"❌ Такого предмета не существует: «{esc(item_query)}». Проверь название в «инвентарь».")
        return

    if item_key in NON_TRADABLE_ITEMS:
        emoji, name, _, _ = ITEMS[item_key]
        await message.reply(f"🚫 {emoji} {esc(name)} нельзя передать — это личный значок, не предмет.")
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
    remaining = await get_inventory(sender_id)
    has_more = any(k == item_key and q > 0 for k, q in remaining)
    if not has_more:
        new_equipped = unequip_item(sender_row[18], item_key)
        await db_exec("UPDATE users SET equipped_items = ? WHERE user_id = ?", (format_equipped(new_equipped), sender_id))

    await add_item(receiver.id, item_key)

    await safe_reply(message, f"{emoji} {esc(name)} передан игроку {esc(receiver_username)}!")


# Токены-валюты для распознавания синтаксиса "[число] [валюта]" в дать/передать
_TRANSFER_CURRENCY_TOKENS = {"ног": "ног", "коин": "коин"}


@dp.message(F.text.regexp(r"(?i)^(дать|передать)\s+(.+)$"))
async def give_or_transfer(message: Message):
    """Умный хендлер: 'дать 888 коин' -> валюта, 'дать свеча' / 'передать свеча' -> предмет.
    Синтаксис определяется автоматически по структуре аргументов."""
    text = message.text.strip()
    verb, _, args = text.partition(" ")
    args = args.strip()
    if not args:
        await message.reply("Укажи, что передать: число+валюту («дать 100 коин») или название предмета («передать свеча»).")
        return

    parts = args.split(" ", 1)
    first_word = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""

    # Синтаксис 1: [число] [валюта] — "888 коин" / "50 ног"
    if _AMOUNT_TOKEN_RE.match(first_word) and rest:
        currency_word = rest.split(" ", 1)[0].lower()
        if currency_word in _TRANSFER_CURRENCY_TOKENS:
            amount = parse_amount(first_word)
            if not amount or amount <= 0:
                await message.reply("Некорректное количество.")
                return
            await transfer_currency(message, _TRANSFER_CURRENCY_TOKENS[currency_word], amount)
            return
        else:
            await message.reply(f"❌ Такой валюты не существует: «{esc(currency_word)}». Доступно: ног, коин.")
            return

    # Синтаксис 2: [валюта] [число] — "коин 50" (на случай другого порядка слов)
    if first_word.lower() in _TRANSFER_CURRENCY_TOKENS and rest and _AMOUNT_TOKEN_RE.match(rest.split(" ", 1)[0]):
        amount_word = rest.split(" ", 1)[0]
        amount = parse_amount(amount_word)
        if not amount or amount <= 0:
            await message.reply("Некорректное количество.")
            return
        await transfer_currency(message, _TRANSFER_CURRENCY_TOKENS[first_word.lower()], amount)
        return

    # Синтаксис 3: название предмета целиком (прямой поиск по вхождению, без фильтров б/п)
    await transfer_item_direct(message, args)


async def sell_item(message: Message, prefix: str, only_passive: bool):
    item_query = message.text[len(prefix):].strip()
    item_key = find_item_by_name(item_query, only_passive=only_passive)
    if not item_key:
        wrong_cmd = "продать п" if only_passive is False else "продать б"
        await message.reply(f"Не нашёл такой предмет среди {'предметов' if only_passive else 'бустеров'}. "
                             f"Если это не то — попробуй «{wrong_cmd} <название>».")
        return

    if item_key in NON_TRADABLE_ITEMS:
        emoji, name, _, _ = ITEMS[item_key]
        await message.reply(f"🚫 {emoji} {esc(name)} нельзя продать — это личный значок, не предмет.")
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
    remaining = await get_inventory(user_id)
    has_more = any(k == item_key and q > 0 for k, q in remaining)
    if not has_more:
        new_equipped = unequip_item(row[18], item_key)
        await db_exec("UPDATE users SET equipped_items = ? WHERE user_id = ?", (format_equipped(new_equipped), user_id))

    upgrades = parse_upgrades(row[16])
    sell_lvl = upgrade_level(upgrades, "sell_boost")
    price = SELL_PRICE.get(item_key, 1) + sell_bonus_coins(upgrades)

    bonus_rebirth = 0
    if sell_lvl >= 3 and random.random() < 0.01:
        bonus_rebirth = 1

    if bonus_rebirth:
        await db_exec(
            "UPDATE users SET coins = coins + ?, rebirth_points = rebirth_points + ? WHERE user_id = ?",
            (price, bonus_rebirth, user_id),
        )
    else:
        await db_exec("UPDATE users SET coins = coins + ? WHERE user_id = ?", (price, user_id))

    bonus_text = " 🎉 Повезло! +1 🉑!" if bonus_rebirth else ""
    await safe_reply(message, f"Продал {emoji} {esc(name)} за {price} 🪙.{bonus_text}")


@dp.message(F.text.lower().startswith("продать б "))
async def sell_booster(message: Message):
    await sell_item(message, "продать б ", only_passive=False)


@dp.message(F.text.lower().startswith("продать п "))
async def sell_passive(message: Message):
    await sell_item(message, "продать п ", only_passive=True)


@dp.message(F.text.regexp(r"(?i)^продать(\s+.*)?$"))
async def sell_wrong_format(message: Message):
    """Ловит 'продать <название>' без б/п (или вообще без аргумента) — чтобы не было тишины."""
    lower = message.text.lower()
    if lower.startswith("продать б ") or lower.startswith("продать п "):
        return  # уже обработано специализированными хендлерами выше
    await message.reply(
        "Не понял формат. Укажи тип: «продать б <название>» — для бустеров, «продать п <название>» — для предметов."
    )


async def destroy_item(message: Message, prefix: str, only_passive: bool):
    item_query = message.text[len(prefix):].strip()
    item_key = find_item_by_name(item_query, only_passive=only_passive)
    if not item_key:
        wrong_cmd = "уничтожение п" if only_passive is False else "уничтожение б"
        await message.reply(f"Не нашёл такой предмет среди {'предметов' if only_passive else 'бустеров'}. "
                             f"Если это не то — попробуй «{wrong_cmd} <название>».")
        return

    if item_key in NON_TRADABLE_ITEMS:
        emoji, name, _, _ = ITEMS[item_key]
        await message.reply(f"🚫 {emoji} {esc(name)} нельзя уничтожить — это личный значок, не предмет.")
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
    remaining = await get_inventory(user_id)
    has_more = any(k == item_key and q > 0 for k, q in remaining)
    if not has_more:
        new_equipped = unequip_item(row[18], item_key)
        await db_exec("UPDATE users SET equipped_items = ? WHERE user_id = ?", (format_equipped(new_equipped), user_id))

    await safe_reply(message, f"🗑 Уничтожил {emoji} {esc(name)}. Без награды — назад не вернуть.")


@dp.message(F.text.lower().startswith("уничтожение б "))
async def destroy_booster(message: Message):
    await destroy_item(message, "уничтожение б ", only_passive=False)


@dp.message(F.text.lower().startswith("уничтожение п "))
async def destroy_passive(message: Message):
    await destroy_item(message, "уничтожение п ", only_passive=True)


@dp.message(F.text.regexp(r"(?i)^уничтожение(\s+.*)?$"))
async def destroy_wrong_format(message: Message):
    lower = message.text.lower()
    if lower.startswith("уничтожение б ") or lower.startswith("уничтожение п "):
        return
    await message.reply(
        "Не понял формат. Укажи тип: «уничтожение б <название>» — для бустеров, «уничтожение п <название>» — для предметов."
    )


def format_inventory_menu_text(active_items, upgrades: dict = None):
    items = _normalize_active_items(active_items)
    max_slots = equipped_slots_max(upgrades or {})
    equipped = [f"{ITEMS[k][0]} {esc(ITEMS[k][1])} (+{ITEMS[k][2]}%)" for k in items if k in ITEMS]
    equipped_text = f"Экипировано ({len(equipped)}/{max_slots}): " + (", ".join(equipped) if equipped else "ничего")
    return f"🎒 <b>Твой инвентарь</b>\n{equipped_text}\n\nВыбери раздел:"


def inventory_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧪 Бустеры", callback_data=f"inv_cat:{user_id}:boosters")],
        [InlineKeyboardButton(text="📦 Предметы", callback_data=f"inv_cat:{user_id}:items")],
    ])


def boosters_keyboard(rows, active_items, user_id: int) -> InlineKeyboardMarkup:
    equipped = set(_normalize_active_items(active_items))
    kb_rows = []
    for item_key, qty in rows:
        if item_key in PASSIVE_ITEMS:
            continue
        emoji, name, percent, _ = ITEMS[item_key]
        mark = " ✅" if item_key in equipped else ""
        kb_rows.append([InlineKeyboardButton(
            text=f"{name} {plain_emoji(emoji)} (+{percent}%) x{qty}{mark}",
            callback_data=f"equip:{user_id}:{item_key}",
        )])
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"inv_menu:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)


def items_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"inv_menu:{user_id}")]])


def format_boosters_text(rows, max_slots: int = 1):
    boosters = [(k, q) for k, q in rows if k not in PASSIVE_ITEMS]
    if not boosters:
        return f"🧪 У тебя нет бустеров. Можно носить одновременно {max_slots}."
    return f"🧪 Твои бустеры (можно носить одновременно {max_slots}):"


def format_items_text(rows):
    passive = [(k, q) for k, q in rows if k in PASSIVE_ITEMS]
    if not passive:
        return "📦 У тебя нет предметов."
    lines = ["📦 Твои предметы (нельзя экипировать, действуют пассивно):\n"]
    for item_key, qty in passive:
        emoji, name, _, _ = ITEMS[item_key]
        lines.append(f"{emoji} {esc(name)} x{qty}")
    return "\n".join(lines)


@dp.message(F.text.lower().in_({"инвентарь", "мой инвентарь"}))
async def inventory(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    rows = await get_inventory(user_id)

    if not rows:
        await message.reply("🎒 Инвентарь пуст.")
        return

    await safe_reply(message, format_inventory_menu_text(active_items, upgrades), reply_markup=inventory_menu_keyboard(user_id))


@dp.message(F.text.lower().in_({"мои предметы", "предметы"}))
async def my_items_tab(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)
    rows = await get_inventory(user_id)
    await safe_reply(message, format_items_text(rows), reply_markup=items_keyboard(user_id))


@dp.message(F.text.lower().in_({"мои бустеры", "бустеры"}))
async def my_boosters_tab(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    max_slots = equipped_slots_max(upgrades)
    rows = await get_inventory(user_id)
    await message.reply(format_boosters_text(rows, max_slots), reply_markup=boosters_keyboard(rows, active_items, user_id))


@dp.callback_query(F.data.startswith("inv_menu:"))
async def inventory_back_to_menu(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer("Это не твой инвентарь!", show_alert=True)
        return

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    await safe_edit_text(callback, format_inventory_menu_text(active_items, upgrades), reply_markup=inventory_menu_keyboard(owner_id))
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
        upgrades = parse_upgrades(row[16])
        active_items = parse_equipped(row[18])
        max_slots = equipped_slots_max(upgrades)
        await callback.message.edit_text(format_boosters_text(rows, max_slots), reply_markup=boosters_keyboard(rows, active_items, owner_id))
    else:
        await safe_edit_text(callback, format_items_text(rows), reply_markup=items_keyboard(owner_id))
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
    upgrades = parse_upgrades(row[16])
    max_slots = equipped_slots_max(upgrades)

    before = parse_equipped(row[18])
    kicked = before[0] if item_key not in before and len(before) >= max_slots else None
    new_equipped = equip_item(row[18], item_key, max_slots)

    await db_exec("UPDATE users SET equipped_items = ? WHERE user_id = ?", (format_equipped(new_equipped), owner_id))
    rows = await get_inventory(owner_id)

    await callback.message.edit_text(format_boosters_text(rows, max_slots), reply_markup=boosters_keyboard(rows, new_equipped, owner_id))
    if kicked and kicked in ITEMS:
        await callback.answer(f"Надел! {ITEMS[item_key][1]} вытеснил {ITEMS[kicked][1]} (слоты заняты).")
    else:
        await callback.answer("Готово!")


# ---------- Крафты ("крафты [предмет]") ----------

CRAFT_RE = re.compile(r"^крафт(?:ы)?(?:\s+(.+))?$", re.IGNORECASE)


def craft_level_of(upgrades: dict) -> int:
    return upgrade_level(upgrades, "crafts")


def available_recipes(craft_level: int, query: str = None) -> list:
    """Рецепты, доступные по уровню крафта игрока, отфильтрованные по подстроке в названии результата."""
    result = []
    for key, recipe in RECIPES.items():
        if recipe["level"] > craft_level:
            continue
        if query and query.lower() not in ITEMS[key][1].lower():
            continue
        result.append(key)
    return result


def crafts_keyboard(recipe_keys: list, user_id: int) -> InlineKeyboardMarkup:
    rows = []
    for key in recipe_keys:
        emoji, name, _, _ = ITEMS[key]
        rows.append([InlineKeyboardButton(
            text=f"{plain_emoji(emoji)} Скрафтить {name}",
            callback_data=f"craft:{user_id}:{key}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_crafts_text(recipe_keys: list, craft_level: int, query: str) -> str:
    if not recipe_keys:
        if query:
            return f"🔨 Нет доступных рецептов по запросу «{esc(query)}» (либо не хватает уровня крафта {craft_level}/2)."
        return f"🔨 Нет доступных рецептов на твоём уровне крафта ({craft_level}/2). Качай апгрейд «Крафты» в прокачке!"
    lines = [f"🔨 <b>Доступные рецепты</b> (уровень крафта {craft_level}/2):\n"]
    for key in recipe_keys:
        emoji, name, _, _ = ITEMS[key]
        lines.append(f"{plain_emoji(emoji)} <b>{esc(name)}</b> = {esc(format_recipe_requirements(RECIPES[key]))}")
    return "\n".join(lines)


@dp.message(F.text.regexp(r"(?i)^крафт(ы)?(\s+.+)?$"))
async def crafts_command(message: Message):
    match = CRAFT_RE.match(message.text.strip())
    if not match:
        return
    query = (match.group(1) or "").strip() or None

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    upgrades = parse_upgrades(row[16])
    craft_level = craft_level_of(upgrades)

    recipe_keys = available_recipes(craft_level, query)
    await message.reply(
        format_crafts_text(recipe_keys, craft_level, query or ""),
        reply_markup=crafts_keyboard(recipe_keys, user_id) if recipe_keys else None,
    )


@dp.callback_query(F.data.startswith("craft:"))
async def craft_do(callback: CallbackQuery):
    _, owner_str, recipe_key = callback.data.split(":")
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer("Это не твой крафт!", show_alert=True)
        return
    if recipe_key not in RECIPES:
        await callback.answer("Рецепт не найден.", show_alert=True)
        return

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    craft_level = craft_level_of(upgrades)
    recipe = RECIPES[recipe_key]

    if recipe["level"] > craft_level:
        await callback.answer(f"Нужен уровень крафта {recipe['level']}, у тебя {craft_level}.", show_alert=True)
        return

    coins, score = row[5], row[2]
    inv_rows = await get_inventory(owner_id)
    inventory_map = {k: q for k, q in inv_rows}

    missing = recipe_missing_ingredients(inventory_map, coins, score, recipe)
    if missing:
        await callback.answer("Не хватает: " + "; ".join(missing), show_alert=True)
        return

    # Списываем ингредиенты
    for ing_key, qty in recipe.get("ingredients", {}).items():
        await remove_item(owner_id, ing_key, qty)
    if recipe.get("needs_all_amulets"):
        for ing_key in ALL_PLAYER_AMULETS:
            await remove_item(owner_id, ing_key, 1)
    if recipe.get("coin_cost"):
        await db_exec("UPDATE users SET coins = coins - ? WHERE user_id = ?", (recipe["coin_cost"], owner_id))
    if recipe.get("score_cost"):
        await db_exec("UPDATE users SET score = score - ? WHERE user_id = ?", (recipe["score_cost"], owner_id))

    await add_item(owner_id, recipe_key, 1)

    emoji, name, _, _ = ITEMS[recipe_key]
    result_text = f"✅ Скрафтил {plain_emoji(emoji)} {name}!"

    await callback.message.reply(result_text)
    await callback.answer("Готово!")


def case_offer_keyboard(case_num: int, user_id: int, price: int) -> InlineKeyboardMarkup:
    case = CASES[case_num]
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"🎁 Открыть {case['name']} ({price} 🪙)", callback_data=f"buy_case:{case_num}:{user_id}")
    ]])


def format_case_inspect_text(case_num: int, price: int, base_price: int) -> str:
    case = CASES[case_num]
    discount_line = f" (скидка, было {base_price} 🪙)" if price != base_price else ""
    lines = [f"📦 <b>{esc(case['name'])}</b>", f"Цена: {price} 🪙{discount_line}", "", "Возможный дроп:"]
    for _k, emoji, name, percent, chance in case_drop_table(case_num):
        boost_part = f" (+{percent}%)" if percent else ""
        lines.append(f"{plain_emoji(emoji)} {esc(name)}{boost_part} — {chance}%")
    return "\n".join(lines)


async def send_case_inspect(message: Message, case_num: int):
    """Меню осмотра кейса: список дропа с процентами + кнопка открытия."""
    case = CASES.get(case_num)
    if not case:
        await message.reply("Такого кейса нет.")
        return
    row = await ensure_user(message.from_user.id, message.from_user.username or message.from_user.first_name or "Без имени")
    upgrades = parse_upgrades(row[16])
    price = case_price_with_discount(case["price"], upgrades)
    await message.reply(
        format_case_inspect_text(case_num, price, case["price"]),
        reply_markup=case_offer_keyboard(case_num, message.from_user.id, price),
    )


async def open_case_instant(message: Message, case_num: int):
    """'открыть кейс N' — мгновенная рулетка, минуя меню осмотра."""
    case = CASES.get(case_num)
    if not case:
        await message.reply("Такого кейса нет.")
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    coins = row[5]
    upgrades = parse_upgrades(row[16])
    price = case_price_with_discount(case["price"], upgrades)

    if coins < price:
        await message.reply(f"Не хватает монет. Нужно {price} 🪙, у тебя {coins} 🪙.")
        return

    item_key = roll_case_item(case_num)
    emoji, name, percent, _ = ITEMS[item_key]

    await db_exec(
        "UPDATE users SET coins = coins - ?, cases_opened = cases_opened + 1 WHERE user_id = ?",
        (price, user_id),
    )
    await add_item(user_id, item_key)
    new_coins = coins - price

    await message.reply(f"🎉 Выпало: {emoji} {esc(name)} (+{percent}%)!\nОстаток монет: {new_coins} 🪙")


@dp.message(F.text.lower() == "кейс")
async def case_default(message: Message):
    await send_case_inspect(message, 1)


@dp.message(F.text.lower().regexp(r"^кейс \d+$"))
async def case_numbered(message: Message):
    match = CASE_NUM_RE.match(message.text.strip().lower())
    await send_case_inspect(message, int(match.group(1)))


@dp.message(F.text.lower().regexp(r"^(осмотреть кейс|осмотр кейс)\s+(\d+)$"))
async def case_inspect_command(message: Message):
    match = re.match(r"^(?:осмотреть кейс|осмотр кейс)\s+(\d+)$", message.text.strip().lower())
    await send_case_inspect(message, int(match.group(1)))


@dp.message(F.text.lower().regexp(r"^открыть кейс\s+(\d+)$"))
async def case_open_command(message: Message):
    match = re.match(r"^открыть кейс\s+(\d+)$", message.text.strip().lower())
    await open_case_instant(message, int(match.group(1)))


@dp.message(F.text.lower() == "кейсы")
async def case_list(message: Message):
    user_id = message.from_user.id
    row = await ensure_user(user_id, message.from_user.username or message.from_user.first_name or "Без имени")
    upgrades = parse_upgrades(row[16])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{case['name']} ({case_price_with_discount(case['price'], upgrades)} 🪙)",
            callback_data=f"inspect_case:{num}:{user_id}",
        )]
        for num, case in CASES.items()
    ])
    await message.reply("Доступные кейсы:", reply_markup=kb)


@dp.callback_query(F.data.startswith("inspect_case:"))
async def inspect_case_callback(callback: CallbackQuery):
    _, case_num_str, owner_str = callback.data.split(":")
    case_num = int(case_num_str)
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer("Это не твоё меню!", show_alert=True)
        return

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    case = CASES[case_num]
    price = case_price_with_discount(case["price"], upgrades)

    await callback.message.edit_text(
        format_case_inspect_text(case_num, price, case["price"]),
        reply_markup=case_offer_keyboard(case_num, owner_id, price),
    )
    await callback.answer()


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
    upgrades = parse_upgrades(row[16])
    price = case_price_with_discount(case["price"], upgrades)

    if coins < price:
        await callback.answer(f"Не хватает монет. Нужно {price} 🪙", show_alert=True)
        return

    item_key = roll_case_item(case_num)
    emoji, name, percent, _ = ITEMS[item_key]

    await db_exec(
        "UPDATE users SET coins = coins - ?, cases_opened = cases_opened + 1 WHERE user_id = ?",
        (price, owner_id),
    )
    await add_item(owner_id, item_key)
    new_coins = coins - price

    await callback.message.edit_text(
        f"🎉 Выпало: {emoji} {esc(name)} (+{percent}%)!\nОстаток монет: {new_coins} 🪙",
        reply_markup=case_offer_keyboard(case_num, owner_id, price),
    )
    await callback.answer("Кейс открыт!")


@dp.message(F.text.lower() == "эволюция")
async def evolve(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level = row[2], row[3]
    rebirth_count = row[15]

    required = level_threshold(39, evolution_level, rebirth_count)
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


# ---------- Меню прокачки ("апгрейд" / "прокачка" / "апг") ----------

def format_upgrade_page_text(upgrades: dict, rebirth_points: int, category: int) -> str:
    header = (
        f"⚙️ <b>МЕНЮ ПРОКАЧКИ</b> — {UPGRADE_CATEGORIES[category]}\n"
        f"🉑 Очки перерождения: <code>{rebirth_points}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
    )
    return header


def upgrade_page_keyboard(upgrades: dict, user_id: int, category: int) -> InlineKeyboardMarkup:
    rows = []
    for key in UPGRADE_ORDER:
        cfg = UPGRADES[key]
        if cfg["category"] != category:
            continue
        level = upgrade_level(upgrades, key)
        if cfg.get("wip"):
            label = f"🔧 {cfg['name']} — {level}/{cfg['max_level']} (в разработке)"
            rows.append([InlineKeyboardButton(text=label, callback_data="upg_noop")])
            continue
        cost = upgrade_next_cost(key, upgrades)
        if cost is None:
            label = f"✅ {cfg['name']} — {level}/{cfg['max_level']} (макс)"
            rows.append([InlineKeyboardButton(text=label, callback_data="upg_noop")])
        else:
            label = f"{cfg['name']} — {level}/{cfg['max_level']} ({cost} 🉑)"
            rows.append([InlineKeyboardButton(text=label, callback_data=f"upg_buy:{user_id}:{category}:{key}")])

    nav = []
    for cat in (1, 2, 3):
        marker = "• " if cat == category else ""
        nav.append(InlineKeyboardButton(text=f"{marker}{cat}", callback_data=f"upg_page:{user_id}:{cat}"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(F.text.lower().in_({"апгрейд", "прокачка", "апг"}))
async def upgrade_menu(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    upgrades = parse_upgrades(row[16])
    rebirth_points = row[14]

    await message.reply(
        format_upgrade_page_text(upgrades, rebirth_points, 1),
        reply_markup=upgrade_page_keyboard(upgrades, user_id, 1),
    )


@dp.callback_query(F.data == "upg_noop")
async def upgrade_noop(callback: CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data.startswith("upg_page:"))
async def upgrade_change_page(callback: CallbackQuery):
    _, owner_str, category_str = callback.data.split(":")
    owner_id = int(owner_str)
    category = int(category_str)
    if callback.from_user.id != owner_id:
        await callback.answer("Это не твоё меню прокачки!", show_alert=True)
        return

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    rebirth_points = row[14]
    await callback.message.edit_text(
        format_upgrade_page_text(upgrades, rebirth_points, category),
        reply_markup=upgrade_page_keyboard(upgrades, owner_id, category),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("upg_buy:"))
async def upgrade_buy(callback: CallbackQuery):
    _, owner_str, category_str, key = callback.data.split(":")
    owner_id = int(owner_str)
    category = int(category_str)
    if callback.from_user.id != owner_id:
        await callback.answer("Это не твоё меню прокачки!", show_alert=True)
        return
    if key not in UPGRADES or UPGRADES[key].get("wip"):
        await callback.answer("Этот раздел ещё в разработке.", show_alert=True)
        return

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    rebirth_points = row[14]
    cost = upgrade_next_cost(key, upgrades)

    if cost is None:
        await callback.answer("Максимальный уровень уже достигнут.", show_alert=True)
        return
    if rebirth_points < cost:
        await callback.answer(f"Не хватает 🉑. Нужно {cost}, у тебя {rebirth_points}.", show_alert=True)
        return

    upgrades[key] = upgrade_level(upgrades, key) + 1
    new_points = rebirth_points - cost
    await db_exec(
        "UPDATE users SET rebirth_points = ?, upgrades = ? WHERE user_id = ?",
        (new_points, format_upgrades(upgrades), owner_id),
    )

    await callback.message.edit_text(
        format_upgrade_page_text(upgrades, new_points, category),
        reply_markup=upgrade_page_keyboard(upgrades, owner_id, category),
    )
    await callback.answer(f"Улучшено! {UPGRADES[key]['name']} → {upgrades[key]} лвл")


# ---------- Перерождение ----------

@dp.message(F.text.lower() == "перерождение")
async def rebirth(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level = row[2], row[3]
    rebirth_points, rebirth_count = row[14], row[15]

    if evolution_level < REBIRTH_EVO_PER_POINT:
        await message.reply(
            f"Перерождение доступно с {REBIRTH_EVO_PER_POINT} уровня эволюции "
            f"(сейчас у тебя {evolution_level}). Каждые {REBIRTH_EVO_PER_POINT} уровней эво = 1 🉑."
        )
        return

    points_gained = evolution_level // REBIRTH_EVO_PER_POINT
    new_rebirth_points = rebirth_points + points_gained
    new_rebirth_count = rebirth_count + 1

    await db_exec(
        "UPDATE users SET score = 0, evolution_level = 0, rebirth_points = ?, rebirth_count = ? WHERE user_id = ?",
        (new_rebirth_points, new_rebirth_count, user_id),
    )

    new_hardness = round(REBIRTH_HARDNESS_STEP * new_rebirth_count * 100)
    await message.reply(
        f"🉑 <b>ПЕРЕРОЖДЕНИЕ!</b>\n"
        f"Очки ноги и эволюция сброшены. Получено: +{points_gained} 🉑 (Всего: {new_rebirth_points}).\n"
        f"⚠️ Эволюции теперь на {new_hardness}% сложнее, чем с нуля.\n"
        f"Прокачки из меню «апгрейд» остались с тобой навсегда."
    )


@dp.message(F.text.lower() == "баланс")
async def show_balance(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, coins = row[2], row[5]
    vip_until = row[12]
    rebirth_points, rebirth_count = row[14], row[15]
    vip_active = is_vip_active(vip_until)

    vip_line = f"{PREMIUM_VIP_BADGE} VIP активен" if vip_active else "VIP не активен"

    await message.reply(
        f"💰 <b>Твой баланс</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👣 Очки ноги: <code>{score}</code>\n"
        f"🪙 Монеты: <code>{coins}</code>\n"
        f"🉑 Очки перерождения: <code>{rebirth_points}</code> (перерождений: {rebirth_count})\n"
        f"{vip_line}"
    )


@dp.message(F.text.lower().startswith("!дать очкп"))
async def admin_give_rebirth(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_GIVE_REBIRTH_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !дать очкп <количество> [себе] (в ответ на сообщение игрока)")
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
    new_points = row[14] + amount
    await db_exec("UPDATE users SET rebirth_points = ? WHERE user_id = ?", (new_points, target.id))
    await message.reply(f"Выдано {amount} 🉑 игроку {esc(target_username)} (Всего: {new_points})")


@dp.message(F.text.lower().startswith("!снять очкп"))
async def admin_take_rebirth(message: Message):
    if not is_admin(message):
        return
    match = ADMIN_TAKE_REBIRTH_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !снять очкп <количество> [себе] (в ответ на сообщение игрока)")
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
    new_points = max(0, row[14] - amount)
    await db_exec("UPDATE users SET rebirth_points = ? WHERE user_id = ?", (new_points, target.id))
    await message.reply(f"Снято {amount} 🉑 у игрока {esc(target_username)} (Осталось: {new_points})")


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
    await safe_reply(message, f"Выдан бустер {emoji} {esc(name)} игроку {esc(target_username)}.")


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
        await safe_reply(message, f"Снят бустер {emoji} {esc(name)} у игрока {esc(target_username)}.")
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
    await safe_reply(message, f"Выдан предмет {emoji} {esc(name)} игроку {esc(target_username)}.")


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
        await safe_reply(message, f"Снят предмет {emoji} {esc(name)} у игрока {esc(target_username)}.")
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
        "UPDATE users SET score = 0, evolution_level = 0, coins = 0, active_item = NULL, equipped_items = '', "
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
