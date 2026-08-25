"""
economy.py — экономический слой бота: доступ к базе данных (Turso/libsql,
асинхронная очередь воркеров) и вся расчётная игровая логика, которая
читает/пишет пользователя (уровни, апгрейды, зелья, фарм-бонусы, кейсы,
крафт-бонусы, "процы" случайных предметов).

Объединён в один модуль, т.к. в исходном коде эти функции взаимно
рекурсивны (расчёт бонусов вызывает запись в БД, а обвязка над БД
использует форматирование зелий/бонусов).
"""
import asyncio
import functools
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor

import libsql
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from premium_emoji import (
    PREMIUM_BADGE_CASE, PREMIUM_BADGE_CHAOS_MASTER, PREMIUM_BADGE_EVO,
    PREMIUM_BADGE_EVO5, PREMIUM_BADGE_EVO10, PREMIUM_BADGE_EVO25,
    PREMIUM_BADGE_EVO50, PREMIUM_BADGE_EVO100, PREMIUM_BADGE_EVO250,
    PREMIUM_BADGE_EVO500, PREMIUM_BADGE_EVO1000, PREMIUM_BADGE_EVO5000,
    PREMIUM_BADGE_EVO10000, PREMIUM_BADGE_FARM, PREMIUM_BADGE_INVESTOR,
    PREMIUM_BADGE_POWER, PREMIUM_BADGE_SUPPORT, PREMIUM_BADGE_TESTER,
    PREMIUM_BADGE_TOP1_PAST, PREMIUM_BITCOIN, PREMIUM_CRAFT_COIN,
    PREMIUM_GODLY_NOGOST_COIN, PREMIUM_GODLY_VASE, PREMIUM_GOLDEN_VASE,
    PREMIUM_NOGOST_COIN, PREMIUM_OLD_VASE, PREMIUM_OWNER_BADGE,
    PREMIUM_REBIRTH_COIN, PREMIUM_VIP_BADGE,
)
from config import (
    ADMIN_USERNAME, ALL_THRESHOLDS, BADGE_EVO_TOTAL,
    BLAZING_NECKLACE_PRESTIGE_CHANCE, BLAZING_NECKLACE_PRESTIGE_RANGE,
    BLAZING_NECKLACE_REBIRTH_CHANCE, BLAZING_NECKLACE_REBIRTH_RANGE,
    CUSTOM_LEVELS, EVO_BOOST_STEP, EVO_HARDNESS_RATE, EXTRA_TIERS, FARM_BASE,
    FARM_COOLDOWN, FARM_EVOLVED, MAX_LEVEL_SCORE, MGG_MEGA_EMOJI,
    MGG_MEGA_LEVEL, MGG_MEGA_NAME, STAR_NECKLACE_CASE1_DROP_CHANCE,
    TURSO_TOKEN, TURSO_URL, ULTRA_LEG_EMOJI, ULTRA_LEG_LEVEL,
    ULTRA_LEG_NAME, ULTRA_LEVEL_CAP, ULTRA_REBIRTH_BOOST,
    ULTRA_REQUIRED_LEG_LEVEL, ULTRA_TIERS, VIP_BOOST,
)
from game_data import (
    AUTO_FARM_COINS_RATES, AUTO_FARM_LEGS_RATES, BADGES_PAGE_SIZE, CASES,
    CHAOS_ORB_FARM_CHANCE,
    CHAOS_ORB_FARM_MAX, CHAOS_ORB_FARM_MIN, CHRONOS_BOOST_INTERVAL,
    CHRONOS_BOOST_MIN, CHRONOS_BOOST_MAX,
    CHRONOS_ORB_BADGE_CHANCE, CHRONOS_ORB_BOOSTER_CHANCE,
    CHRONOS_ORB_COIN_CHANCE, CHRONOS_ORB_COIN_MIN, CHRONOS_ORB_COIN_MAX,
    CHRONOS_ORB_FARM_MULT_MIN, CHRONOS_ORB_FARM_MULT_MAX,
    CHRONOS_ORB_LEGS_CHANCE, CHRONOS_ORB_LEGS_MIN, CHRONOS_ORB_LEGS_MAX,
    CHRONOS_ORB_NO_CD_CHANCE, CHRONOS_ORB_OLD_VASE_CHANCE,
    CHRONOS_ORB_POTION_CHANCE, CHRONOS_ORB_PRESTIGE_CHANCE,
    CHRONOS_ORB_PRESTIGE_MIN, CHRONOS_ORB_PRESTIGE_MAX,
    CHRONOS_ORB_REBIRTH_CHANCE, CHRONOS_ORB_REBIRTH_MIN, CHRONOS_ORB_REBIRTH_MAX,
    CHRONOS_ORB_STRANGE_COIN_CHANCE,
    EVO_MILESTONE_BADGES,
    GOD_ESSENCE_FARM_SPEED, GOD_ESSENCE_TIMER_CUT, GOD_TIER_LIKE,
    ITEMS, ITEM_FLAT_BONUS, NON_TRADABLE_ITEMS, NO_CD_CHARGES_KEY, POTIONS,
    POTION_ORDER, PRESTIGE_UPGRADES, REBIRTH_HARDNESS_STEP, RECIPES,
    SELL_PRICE, TIME_PARTICLE_FARM_SPEED, UPGRADES,
    _normalize_active_items, craft_coin_cost_with_discount,
    get_active_unique_tier, parse_equipped, prestige_bonus, prestige_level,
    sell_bonus_coins, upgrade_level,
)
from text_utils import esc, plain_emoji

def build_regular_visual(level: int) -> str:
    if level <= 5:
        return "🦵" * level
    idx = level - 6
    tier = idx // 5
    pos = idx % 5 + 1
    tier_emoji = ["🦵🏻", "🦵🏽", "🦿"][tier]
    prev_emoji = ["🦵", "🦵🏻", "🦵🏽"][tier]
    return tier_emoji * pos + prev_emoji * (5 - pos)

# Начиная с level 20002 (старт ULTRA-диапазона) стоимость КАЖДОГО отдельного уровня растёт
# по своей отдельной шкале: level 20002 стоит ровно 100 000 000 очков, дальше — «почучуть»
# (полиномиально, степень n^1.15) относительно позиции n = level - 20001 в этом диапазоне.
# Формула суммируется точно (прямой цикл) до ULTRA_EXACT_SUM_CUTOFF, а выше — через
# приближение Эйлера-Маклорена (расхождение < 0.002% уже на границе, дальше меньше) —
# без этого точный цикл был бы слишком медленным на экстремальных уровнях (level ~ 10^100).
ULTRA_STEP_BASE_COST = 100_000_000
ULTRA_STEP_POWER = 1.15
ULTRA_EXACT_SUM_CUTOFF = 1000

@functools.lru_cache(maxsize=4096)
def _ultra_step_cost(n: int) -> int:
    """Стоимость перехода на n-й уровень ULTRA-диапазона (n=1 -> level 20002 -> 100 000 000)."""
    return round(ULTRA_STEP_BASE_COST * n ** ULTRA_STEP_POWER)

@functools.lru_cache(maxsize=4096)
def _ultra_extra_score(n: int) -> int:
    """Сумма стоимостей уровней 1..n сверх базового threshold(level=20001), n = level - 20001."""
    if n <= 0:
        return 0
    if n <= ULTRA_EXACT_SUM_CUTOFF:
        return sum(_ultra_step_cost(i) for i in range(1, n + 1))
    p = ULTRA_STEP_POWER
    approx = n ** (p + 1) / (p + 1) + n ** p / 2 + p * n ** (p - 1) / 12 - p * (p - 1) * (p - 2) * n ** (p - 3) / 720
    return round(ULTRA_STEP_BASE_COST * approx)

def base_level_threshold(level: int) -> int:
    if level <= 39:
        return ALL_THRESHOLDS[level - 1]
    if level <= ULTRA_REQUIRED_LEG_LEVEL:  # <= 20001, старая формула без изменений
        return MAX_LEVEL_SCORE + round(200 * (level - 39) ** 1.5)
    t20001 = MAX_LEVEL_SCORE + round(200 * (ULTRA_REQUIRED_LEG_LEVEL - 39) ** 1.5)
    return t20001 + _ultra_extra_score(level - ULTRA_REQUIRED_LEG_LEVEL)

def level_threshold(level: int, evolution_level: int, rebirth_count: int = 0, active_items=None) -> int:
    evo_extra = EVO_HARDNESS_RATE * evolution_level
    rebirth_extra = REBIRTH_HARDNESS_STEP * rebirth_count
    if active_items and "paradox_charm" in set(_normalize_active_items(active_items)):
        evo_extra *= 0.5
        rebirth_extra *= 0.5
    hardness = (1 + evo_extra) * (1 + rebirth_extra)
    return round(base_level_threshold(level) * hardness)

def get_level_index(score: int, evolution_level: int = 0, rebirth_count: int = 0,
                     ultra_rebirth: bool = False) -> int:
    cap = ULTRA_LEVEL_CAP if ultra_rebirth else ULTRA_REQUIRED_LEG_LEVEL
    lo, hi = 0, cap
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
    if level >= ULTRA_LEG_LEVEL:
        for start, end, emoji, name in ULTRA_TIERS:
            if start <= level <= end:
                return emoji, name, True
        return ULTRA_LEG_EMOJI, ULTRA_LEG_NAME, True
    if level >= MGG_MEGA_LEVEL:
        return MGG_MEGA_EMOJI, MGG_MEGA_NAME, True
    for start, end, emoji, name in EXTRA_TIERS:
        if start <= level <= end:
            return emoji, name, True
    return "❓", "неизвестный уровень", True

def next_level_text(score: int, evolution_level: int, rebirth_count: int = 0,
                     ultra_rebirth: bool = False) -> str:
    level = get_level_index(score, evolution_level, rebirth_count, ultra_rebirth)
    cap = ULTRA_LEVEL_CAP if ultra_rebirth else ULTRA_REQUIRED_LEG_LEVEL
    if level >= cap:
        return "Ты достиг абсолютного предела ноги — дальше только легенды 🌌"
    nxt = level_threshold(level + 1, evolution_level, rebirth_count)
    return f"До {level + 1} уровня осталось {nxt - score} очков"

def coin_tree_slot_bonus(inventory_map: dict) -> int:
    """+1 слот экипировки за 🟣 Монету Перерождения, +1 слот за ⚪️ Монету Пробуждения
    (суммируются, если есть обе — по 1 шт. каждой достаточно, лёжа в инвентаре, экипировать
    не нужно)."""
    bonus = 0
    if inventory_map.get("rebirth_coin", 0) > 0:
        bonus += 1
    if inventory_map.get("awakening_coin", 0) > 0:
        bonus += 1
    return bonus

def equipped_slots_max(upgrades: dict, prestige_upgrades: dict = None, bonus_slots: int = 0) -> int:
    prestige_upgrades = prestige_upgrades or {}
    return 1 + upgrade_level(upgrades, "equip_slots") + prestige_bonus(prestige_upgrades, "p_slots") + bonus_slots

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

def parse_potions(potions_str: str) -> dict:
    """'key:value,key:value' -> {key: value}. Для time-based зелий value = unix until_ts,
    для charge-based (no_cd) value = оставшиеся заряды."""
    result = {}
    for part in (potions_str or "").split(","):
        if not part or ":" not in part:
            continue
        key, _, val = part.partition(":")
        if key in POTIONS:
            try:
                result[key] = int(val)
            except ValueError:
                pass
    return result

def format_potions(potions: dict) -> str:
    return ",".join(f"{k}:{v}" for k, v in potions.items() if v > 0)

def active_potions_now(potions_str: str, now: int = None, active_items=None) -> dict:
    """Отфильтровывает истёкшие time-based зелья (charge-based остаются, пока заряды > 0).
    ⏰ Часы Хроноса: пока экипированы, время action-зелий не тикает (не удаляем по истечению) —
    сама запись until_ts в БД не трогается, поэтому после снятия предмета зелье честно
    доедает оставшееся время."""
    now = now or int(time.time())
    frozen = bool(active_items and "chronos_clock" in set(_normalize_active_items(active_items)))
    parsed = parse_potions(potions_str)
    result = {}
    for key, val in parsed.items():
        cfg = POTIONS[key]
        if cfg["effect"] == "no_cd":
            if val > 0:
                result[key] = val
        else:
            if val > now or frozen:
                result[key] = val
    return result

def potion_duration_seconds(key: str, upgrades: dict) -> int:
    base = POTIONS[key]["duration_seconds"]
    bonus = 1 + 0.20 * upgrade_level(upgrades, "brew_duration")
    return round(base * bonus)

CHAOS_ORB_BREW_CUT = 0.90

def brew_seconds_for(key: str, upgrades: dict, prestige_upgrades: dict = None, active_items=None) -> int:
    base = POTIONS[key]["brew_seconds"]
    cut = 1 - 0.10 * upgrade_level(upgrades, "brew_speed")
    if prestige_upgrades:
        p_speed = prestige_bonus(prestige_upgrades, "p_brew_speed")
        if p_speed:
            cut -= 0.02 * p_speed
    if active_items and "chaos_orb" in set(_normalize_active_items(active_items)):
        cut -= CHAOS_ORB_BREW_CUT
    cut = max(0.1, cut)
    return max(30, round(base * cut))

def has_potion_effect(potions: dict, effect: str) -> bool:
    return any(POTIONS[k]["effect"] == effect for k in potions)

async def consume_no_cd_charge(user_id: int, potions: dict) -> dict:
    """Списывает 1 заряд зелья 'без КД', если оно активно. Возвращает обновлённый potions dict."""
    if NO_CD_CHARGES_KEY not in potions:
        return potions
    left = potions[NO_CD_CHARGES_KEY] - 1
    new_potions = dict(potions)
    if left > 0:
        new_potions[NO_CD_CHARGES_KEY] = left
    else:
        new_potions.pop(NO_CD_CHARGES_KEY, None)
    await db_exec("UPDATE users SET active_potions = ? WHERE user_id = ?", (format_potions(new_potions), user_id))
    return new_potions

def parse_potion_stock(stock_str: str) -> dict:
    """Сваренные, но не выпитые зелья: 'key:qty,key:qty' -> {key: qty}."""
    result = {}
    for part in (stock_str or "").split(","):
        if not part or ":" not in part:
            continue
        key, _, qty = part.partition(":")
        if key in POTIONS:
            try:
                q = int(qty)
                if q > 0:
                    result[key] = q
            except ValueError:
                pass
    return result

def format_potion_stock(stock: dict) -> str:
    return ",".join(f"{k}:{v}" for k, v in stock.items() if v > 0)

def get_multiplier(evolution_level: int, active_items, vip_active: bool, upgrades: dict = None,
                    ultra_rebirth: bool = False, chronos_boost_pct: int = 100) -> float:
    mult = 1.0
    if evolution_level >= 2:
        mult += EVO_BOOST_STEP
    if evolution_level >= 3:
        mult += EVO_BOOST_STEP * (evolution_level - 2)
    equipped_set = set(_normalize_active_items(active_items))
    total_boost_percent = 0
    for item_key in equipped_set:
        if item_key in ITEMS and item_key != "chronos_orb":
            total_boost_percent += ITEMS[item_key][2]
    mult += total_boost_percent / 100
    if "chronos_orb" in equipped_set:
        mult += chronos_boost_pct / 100
    if vip_active:
        mult += VIP_BOOST
    if upgrades:
        mult += 0.05 * upgrade_level(upgrades, "booster")
    if ultra_rebirth:
        mult += ULTRA_REBIRTH_BOOST
    return mult

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

def upgrade_next_cost(key: str, upgrades: dict):
    cfg = UPGRADES[key]
    if cfg.get("wip") or cfg["cost"] is None:
        return None
    level = upgrade_level(upgrades, key)
    if level >= cfg["max_level"]:
        return None
    return cfg["cost"](level + 1)

def upgrade_next_extra_cost(key: str, upgrades: dict):
    """Доп. стоимость в другой валюте для следующего уровня апгрейда (напр. крафты ур.3 = 🉑+💠).
    Возвращает (currency_field, amount) либо None, если для этого уровня доп. валюты нет."""
    cfg = UPGRADES[key]
    if cfg.get("wip") or cfg["cost"] is None or not cfg.get("extra_cost"):
        return None
    level = upgrade_level(upgrades, key)
    if level >= cfg["max_level"]:
        return None
    return cfg["extra_cost"](level + 1)

def parse_prestige_upgrades(upgrades_str: str) -> dict:
    result = {}
    for part in (upgrades_str or "").split(","):
        if not part or ":" not in part:
            continue
        key, _, lvl = part.partition(":")
        if key in PRESTIGE_UPGRADES:
            try:
                result[key] = int(lvl)
            except ValueError:
                pass
    return result

def format_prestige_upgrades(upgrades: dict) -> str:
    return ",".join(f"{k}:{v}" for k, v in upgrades.items() if v > 0)

def prestige_next_cost(key: str, upgrades: dict) -> int:
    """Бесконечная ветка — цена следующего уровня всегда определена, потолка нет."""
    level = prestige_level(upgrades, key)
    return PRESTIGE_UPGRADES[key]["cost"](level + 1)

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

def farm_cd_seconds(upgrades: dict, active_items=None, has_time_particle: bool = False,
                     prestige_upgrades: dict = None) -> int:
    reduction = 120 * upgrade_level(upgrades, "farm_cd")
    cooldown = max(60, FARM_COOLDOWN - reduction)

    tier = get_active_unique_tier(active_items) if active_items is not None else None
    if tier in GOD_TIER_LIKE:
        cooldown = cooldown / GOD_ESSENCE_FARM_SPEED - GOD_ESSENCE_TIMER_CUT
    elif has_time_particle:
        cooldown = cooldown / TIME_PARTICLE_FARM_SPEED

    if prestige_upgrades:
        p_speed = prestige_bonus(prestige_upgrades, "p_farm_speed")
        if p_speed:
            cooldown *= max(0.1, 1 - 0.01 * p_speed)

    return max(30, round(cooldown))

def booster_upgrade_multiplier(upgrades: dict) -> float:
    return 1 + 0.05 * upgrade_level(upgrades, "booster")

def case_discount(upgrades: dict) -> float:
    return 0.10 * upgrade_level(upgrades, "discount")

def case_price_with_discount(base_price: int, upgrades: dict) -> int:
    discount = case_discount(upgrades)
    return max(1, round(base_price * (1 - discount)))

def badge_list(username: str, evolution_level: int, cases_opened: int, total_farmed: int, vip_active: bool,
                promo_badges: set = frozenset()):
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
    for key, emoji, label, threshold in EVO_MILESTONE_BADGES:
        if evolution_level >= threshold:
            result.append((key, emoji, label))
    for key in promo_badges:
        if key in PROMO_BADGES:
            emoji, name = PROMO_BADGES[key]
            result.append((key, emoji, name))
    return result

def get_badges(username: str, evolution_level: int, cases_opened: int, total_farmed: int, vip_active: bool,
                hidden: set = frozenset(), promo_badges: set = frozenset()) -> str:
    earned = badge_list(username, evolution_level, cases_opened, total_farmed, vip_active, promo_badges)
    return "".join(emoji for key, emoji, _ in earned if key not in hidden)

def badges_keyboard(earned, hidden: set, user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(earned) - 1) // BADGES_PAGE_SIZE + 1)
    page = max(0, min(page, total_pages - 1))
    start = page * BADGES_PAGE_SIZE
    rows = []
    for key, emoji, label in earned[start:start + BADGES_PAGE_SIZE]:
        state = "🙈 скрыт" if key in hidden else "✅ показан"
        rows.append([InlineKeyboardButton(
            text=f"{plain_emoji(emoji)} {label} — {state}",
            callback_data=f"badge:{user_id}:{page}:{key}",
        )])

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"badge_page:{user_id}:{page - 1}", style="primary"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="badge_noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"badge_page:{user_id}:{page + 1}", style="primary"))
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def farm_range(evolution_level: int):
    return FARM_EVOLVED if evolution_level >= 1 else FARM_BASE


DB_WORKER_COUNT = int(os.environ.get("DB_WORKER_COUNT", "1"))

_db_queues: list = []
_db_worker_tasks: list = []
_db_conns: list = []
_db_executor = ThreadPoolExecutor(max_workers=DB_WORKER_COUNT, thread_name_prefix="db-worker")

_user_cache: dict = {}
_USERS_WRITE_RE = re.compile(r"\b(?:UPDATE|DELETE\s+FROM)\s+users\b", re.IGNORECASE)

def _invalidate_user_cache(user_id):
    _user_cache.pop(user_id, None)

def _connect(worker_idx):
    if _db_conns[worker_idx] is None:
        _db_conns[worker_idx] = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
    return _db_conns[worker_idx]

def _exec_sync(worker_idx, sql, params):
    conn = _connect(worker_idx)
    conn.execute(sql, params)
    conn.commit()

def _exec_many_sync(worker_idx, sql, params_list):
    conn = _connect(worker_idx)
    conn.executemany(sql, params_list)
    conn.commit()

def _query_sync(worker_idx, sql, params):
    conn = _connect(worker_idx)
    cur = conn.execute(sql, params)
    return cur.fetchall()

async def _db_worker(worker_idx):
    """Один из DB_WORKER_COUNT потоков. Каждый воркер берёт задачи строго из
    СВОЕЙ очереди по одной — его соединение всегда используется из одного и
    того же потока (никаких гонок внутри соединения), но разные воркеры со
    своими соединениями могут работать параллельно, а не ждать друг друга."""
    loop = asyncio.get_event_loop()
    queue = _db_queues[worker_idx]
    while True:
        fn, sql, params, future = await queue.get()
        try:
            result = await loop.run_in_executor(_db_executor, fn, worker_idx, sql, params)
            if not future.done():
                future.set_result(result)
        except Exception as e:
            if not future.done():
                future.set_exception(e)
        finally:
            queue.task_done()

def _ensure_db_workers():
    global _db_queues, _db_worker_tasks, _db_conns
    if not _db_queues:
        _db_queues = [asyncio.Queue() for _ in range(DB_WORKER_COUNT)]
        _db_conns = [None] * DB_WORKER_COUNT
        _db_worker_tasks = [None] * DB_WORKER_COUNT
    for i in range(DB_WORKER_COUNT):
        if _db_worker_tasks[i] is None or _db_worker_tasks[i].done():
            _db_worker_tasks[i] = asyncio.create_task(_db_worker(i))

def _pick_worker(params):
    for p in params:
        if isinstance(p, int) and not isinstance(p, bool):
            return p % DB_WORKER_COUNT
    return 0

async def _db_submit(fn, sql, params):
    _ensure_db_workers()
    worker_idx = _pick_worker(params)
    future = asyncio.get_event_loop().create_future()
    await _db_queues[worker_idx].put((fn, sql, params, future))
    return await future

async def db_exec(sql, params=()):
    await _db_submit(_exec_sync, sql, params)
    if _USERS_WRITE_RE.search(sql):
        if "WHERE user_id = ?" in sql and params:
            _invalidate_user_cache(params[-1])
        else:
            _user_cache.clear()

async def db_exec_many(sql, params_list):
    """Как db_exec, но один запрос в очередь воркера выполняет executemany
    сразу для списка наборов параметров — используется для батчинга (см.
    _flush_player_log_buffer), чтобы N записей стоили очереди воркера как одна."""
    if not params_list:
        return
    await _db_submit(_exec_many_sync, sql, params_list)

async def db_query(sql, params=()):
    return await _db_submit(_query_sync, sql, params)

async def db_query_one(sql, params=()):
    rows = await db_query(sql, params)
    return rows[0] if rows else None

USER_COLUMNS = (
    "user_id, username, score, evolution_level, last_farm, coins, active_item, "
    "cases_opened, total_farmed, last_bonus, bonus_streak, levelup_notify, vip_until, hidden_badges, "
    "rebirth_points, rebirth_count, upgrades, last_auto_claim, equipped_items, nickname, top_banned, "
    "ultra_rebirth, auto_evolve, active_potions, brewing_potion, brewing_until, potion_stock, "
    "prestige_points, prestige_upgrades, auto_rebirth, auto_sell, auto_sell_items, craft_points, "
    "promo_badges, chronos_boost_pct"
)

def display_name(username: str, nickname: str = None) -> str:
    """Имя для отображения: ник, если задан, иначе обычный telegram-username."""
    return nickname if nickname else username

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
    await db_exec("""
        CREATE TABLE IF NOT EXISTS personal_boosts (
            user_id INTEGER PRIMARY KEY,
            multiplier REAL DEFAULT 1,
            until INTEGER DEFAULT 0
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER,
            admin_username TEXT,
            command TEXT
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS player_action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER,
            user_id INTEGER,
            username TEXT,
            command TEXT
        )
    """)
    await db_exec("""
        CREATE INDEX IF NOT EXISTS idx_player_action_log_user_ts
        ON player_action_log (user_id, ts)
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS banned_chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            banned_by TEXT,
            banned_at INTEGER
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            banned_by TEXT,
            banned_at INTEGER,
            reason TEXT DEFAULT 'manual'
        )
    """)
    try:
        await db_exec("ALTER TABLE banned_users ADD COLUMN reason TEXT DEFAULT 'manual'")
    except Exception:
        pass
    await db_exec("""
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            reward_type TEXT NOT NULL,
            reward_key TEXT DEFAULT '',
            amount INTEGER NOT NULL,
            activations_left INTEGER NOT NULL,
            created_by TEXT,
            created_at INTEGER
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS promocode_uses (
            user_id INTEGER,
            code TEXT,
            used_at INTEGER,
            PRIMARY KEY (user_id, code)
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
        "ALTER TABLE users ADD COLUMN nickname TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN top_banned INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN ultra_rebirth INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN auto_evolve INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN active_potions TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN brewing_potion TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN brewing_until INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN potion_stock TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN prestige_points INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN prestige_upgrades TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN auto_rebirth INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN auto_sell INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN auto_sell_items TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN craft_points INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN promo_badges TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN chronos_boost_pct INTEGER DEFAULT 100",
    ):
        try:
            await db_exec(stmt)
        except Exception:
            pass

async def get_user(user_id: int):
    if user_id in _user_cache:
        return _user_cache[user_id]
    row = await db_query_one(f"SELECT {USER_COLUMNS} FROM users WHERE user_id = ?", (user_id,))
    if row is not None:
        _user_cache[user_id] = row
    return row

async def get_user_by_username(username: str):
    return await db_query_one(f"SELECT {USER_COLUMNS} FROM users WHERE lower(username) = lower(?)", (username,))

async def ensure_user(user_id: int, username: str):
    row = await get_user(user_id)
    if row is None:
        await db_exec("INSERT INTO users (user_id, username, score) VALUES (?, ?, 0)", (user_id, username))
        now = int(time.time())
        new_row = (user_id, username, 0, 0, 0, 0, None, 0, 0, 0, 0, 1, 0, "", 0, 0, "", now, "", None, 0, 0, 0, "", None, 0, "", 0, "", 0, "", "", 0, "", 100)
        _user_cache[user_id] = new_row
        return new_row
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

async def apply_case_reward(user_id: int, item_key: str, upgrades: dict,
                             auto_sell_enabled: bool, auto_sell_items: set) -> tuple[int, str]:
    """Выдаёт выпавший из кейса предмет — либо в инвентарь как обычно, либо, если включена
    авто-продажа и этот предмет отмечен в конфиге, сразу продаёт его за монеты.
    Возвращает (получено_монет, текст-пометка для ответа, например ' (авто-продано за 8🪙)')."""
    if auto_sell_enabled and item_key in auto_sell_items and item_key not in NON_TRADABLE_ITEMS:
        sell_lvl = upgrade_level(upgrades, "sell_boost")
        price = SELL_PRICE.get(item_key, 1) + sell_bonus_coins(upgrades)
        await db_exec("UPDATE users SET coins = coins + ? WHERE user_id = ?", (price, user_id))
        return price, f" (авто-продано за {price}🪙)"
    await add_item(user_id, item_key)
    return 0, ""

PROMO_TYPE_ALIASES = {
    "ноги": "legs", "нога": "legs", "ног": "legs",
    "эво": "evo", "эволюция": "evo",
    "коин": "coin", "коины": "coin", "монеты": "coin",
    "очкп": "rebirth", "перерождение": "rebirth",
    "крафт": "craft", "очкк": "craft",
}
PROMO_TYPE_COLUMN = {
    "legs": "score",
    "evo": "evolution_level",
    "coin": "coins",
    "rebirth": "rebirth_points",
    "craft": "craft_points",
}
PROMO_TYPE_LABEL = {
    "legs": "🦵 очков ноги",
    "evo": "🧬 очков эволюции",
    "coin": "🪙 монет",
    "rebirth": "🉑 очков перерождения",
    "craft": "💠 очков крафта",
}

PROMO_BADGES = {
    "tester":       (PREMIUM_BADGE_TESTER, "Фанат Мику"),
    "support":      (PREMIUM_BADGE_SUPPORT, "Сапорт"),
    "power":        (PREMIUM_BADGE_POWER, "Потужность"),
    "top1_past":    (PREMIUM_BADGE_TOP1_PAST, "Топ 1 в прошлом"),
    "chaos_master": (PREMIUM_BADGE_CHAOS_MASTER, "Мастер Хаоса⚡️"),
    "investor":     (PREMIUM_BADGE_INVESTOR, "Инвестировал в #####"),
}
PROMO_BADGE_ALIASES = {
    "фанат мику": "tester",
    "сапорт": "support",
    "потужность": "power",
    "топ1 в прошлом": "top1_past",
    "топ 1 в прошлом": "top1_past",
    "мастер хаоса": "chaos_master",
    "инвестировал в #####": "investor",
}

# Справочник для команды «помощь бейдж <название>»: ключ (как в badge_list/PROMO_BADGES) ->
# (эмодзи, русские алиасы для поиска, текст объяснения). Алиасы через запятую в подсказке —
# просто самый первый считается «каноничным» именем бейджа.
HELP_BADGES = {
    "owner":       (PREMIUM_OWNER_BADGE, ["владелец", "овнер", "admin", "админ"],
                    "Этот бейдж есть только у владельца бота — выдаётся автоматически по нику, вручную получить нельзя."),
    "vip":         (PREMIUM_VIP_BADGE, ["vip", "вип"],
                    "Этот бейдж даётся всем игрокам у кого есть VIP-статус. Пропадает, если VIP закончился."),
    "evo":         (PREMIUM_BADGE_EVO, ["1+ эволюция", "эволюция", "эво"],
                    "Даётся за первую эволюцию (39 уровень ноги, «ногу мгг»). Один раз пройдёшь эволюцию — бейдж останется навсегда."),
    "case":        (PREMIUM_BADGE_CASE, ["5+ кейсов", "кейсы", "кейс"],
                    "Даётся за открытие 5 или более кейсов (любых, суммарно)."),
    "farm":        (PREMIUM_BADGE_FARM, ["30k нафармлено", "ферма", "фарм"],
                    f"Даётся, когда суммарно нафармлено {BADGE_EVO_TOTAL} очков ноги (считается всё время, не сбрасывается)."),
    "evo5":        (PREMIUM_BADGE_EVO5, ["5 эволюция", "5эво", "5 эво"],
                    "Даётся по достижению 5 уровня эволюции."),
    "evo_milestone_10":    (PREMIUM_BADGE_EVO10, ["новичок в эво", "10 эво", "10эво"],
                    "Даётся по достижению 10 уровня эволюции."),
    "evo_milestone_25":    (PREMIUM_BADGE_EVO25, ["средний в эво", "25 эво", "25эво"],
                    "Даётся по достижению 25 уровня эволюции."),
    "evo_milestone_50":    (PREMIUM_BADGE_EVO50, ["мастер эво", "50 эво", "50эво"],
                    "Даётся по достижению 50 уровня эволюции."),
    "evo_milestone_100":   (PREMIUM_BADGE_EVO100, ["эво-чемпион", "эво чемпион", "100 эво", "100эво"],
                    "Даётся по достижению 100 уровня эволюции."),
    "evo_milestone_250":   (PREMIUM_BADGE_EVO250, ["король эво", "250 эво", "250эво"],
                    "Даётся по достижению 250 уровня эволюции."),
    "evo_milestone_500":   (PREMIUM_BADGE_EVO500, ["уничтожитель эво", "500 эво", "500эво"],
                    "Даётся по достижению 500 уровня эволюции."),
    "evo_milestone_1000":  (PREMIUM_BADGE_EVO1000, ["всемогущий в эво", "1000 эво", "1000эво"],
                    "Даётся по достижению 1000 уровня эволюции."),
    "evo_milestone_5000":  (PREMIUM_BADGE_EVO5000, ["эво-бог", "эво бог", "5000 эво", "5000эво"],
                    "Даётся по достижению 5000 уровня эволюции."),
    "evo_milestone_10000": (PREMIUM_BADGE_EVO10000, ["эво-титан", "эво титан", "10000 эво", "10000эво"],
                    "Даётся по достижению 10000 уровня эволюции."),
    "tester":      (PREMIUM_BADGE_TESTER, ["фанат мику"],
                    "Выдаётся вручную админом или по промокоду преданным фанатам Мику."),
    "support":     (PREMIUM_BADGE_SUPPORT, ["сапорт", "support"],
                    "Выдаётся вручную админом или по промокоду тем, кто помогает с поддержкой игроков."),
    "power":       (PREMIUM_BADGE_POWER, ["потужность"],
                    "Выдаётся вручную админом или по промокоду — почётный значок за вклад в развитие бота."),
    "top1_past":   (PREMIUM_BADGE_TOP1_PAST, ["топ1 в прошлом", "топ 1 в прошлом", "топ1"],
                    "Выдаётся тем, кто когда-то был на первом месте в топе игроков."),
    "chaos_master": (PREMIUM_BADGE_CHAOS_MASTER, ["мастер хаоса"],
                    "Редкий бейдж, связанный с Шаром Хаоса и Хроносом — выдаётся вручную или по промокоду."),
    "investor":    (PREMIUM_BADGE_INVESTOR, ["инвестировал в #####"],
                    "Выдаётся вручную админом или по промокоду за поддержку проекта."),
}

def find_help_badge_key(query: str):
    """Ищет ключ HELP_BADGES по русскому названию/алиасу. Сначала точное совпадение,
    иначе — по вхождению подстроки в любой из алиасов (как find_item_by_name).
    Возвращает (key, None) при однозначном совпадении, (None, [варианты]) при неоднозначности,
    (None, []) если не найдено."""
    q = (query or "").strip().lower()
    if not q:
        return None, []
    for key, (_, aliases, _) in HELP_BADGES.items():
        if q == key.lower() or q in (a.lower() for a in aliases):
            return key, None
    matches = [key for key, (_, aliases, _) in HELP_BADGES.items() if any(q in a.lower() for a in aliases)]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        matches.sort(key=lambda k: HELP_BADGES[k][1][0])
        return None, matches
    return None, []

def parse_promo_badges(raw: str) -> set:
    return set(x for x in (raw or "").split(",") if x)

def format_promo_badges(badges: set) -> str:
    return ",".join(sorted(badges))

def find_promo_badge_key(name_raw: str):
    """Находит ключ PROMO_BADGES по русскому названию бейджа (из команды создания промокода)."""
    return PROMO_BADGE_ALIASES.get(name_raw.strip().lower())

async def add_promo_badge(user_id: int, badge_key: str):
    row = await db_query_one("SELECT promo_badges FROM users WHERE user_id = ?", (user_id,))
    current = parse_promo_badges(row[0] if row else "")
    current.add(badge_key)
    await db_exec("UPDATE users SET promo_badges = ? WHERE user_id = ?", (format_promo_badges(current), user_id))

def parse_promo_type(raw: str):
    """Разбирает строку типа награды из команды создания промокода.
    Возвращает (reward_type, reward_key) либо None, если тип не распознан.
    "предмет:<ключ>" -> ("item", "<ключ>"); "бейдж" обрабатывается отдельным синтаксисом
    (см. PROMO_CREATE_BADGE_RE); иначе алиас из PROMO_TYPE_ALIASES -> (type, "")."""
    raw = raw.strip().lower()
    if raw.startswith("предмет:") or raw.startswith("предмет "):
        item_key = raw.split(":", 1)[1].strip() if ":" in raw else raw.split(" ", 1)[1].strip()
        if item_key not in ITEMS:
            return None
        return ("item", item_key)
    reward_type = PROMO_TYPE_ALIASES.get(raw)
    if not reward_type:
        return None
    return (reward_type, "")

async def apply_promo_reward(user_id: int, reward_type: str, reward_key: str, amount: int):
    """Выдаёт награду промокода игроку. Возвращает текст для показа в ответе (что именно выдано)."""
    if reward_type == "item":
        await add_item(user_id, reward_key, amount)
        emoji, name, _, _ = ITEMS[reward_key]
        return f"{emoji} {esc(name)} ×{amount}"

    if reward_type == "badge":
        await add_promo_badge(user_id, reward_key)
        emoji, name = PROMO_BADGES[reward_key]
        return f"{emoji} бейдж «{esc(name)}»"

    column = PROMO_TYPE_COLUMN[reward_type]
    await db_exec(
        f"UPDATE users SET {column} = {column} + ? WHERE user_id = ?",
        (amount, user_id),
    )
    return f"{amount} {PROMO_TYPE_LABEL[reward_type]}"

async def remove_item(user_id: int, item_key: str, qty: int = 1) -> bool:
    row = await db_query_one("SELECT qty FROM inventory WHERE user_id = ? AND item_key = ?", (user_id, item_key))
    if not row or row[0] < qty:
        return False
    await db_exec("UPDATE inventory SET qty = ? WHERE user_id = ? AND item_key = ?", (row[0] - qty, user_id, item_key))
    return True

async def apply_farm_bonuses(user_id: int, active_items, inventory_map: dict, luck_boost: bool = False) -> dict:
    """Считает все монетные пассивки (Странная монета, Тёплая свеча, Монета боготворства) одним
    общим числом монет + бонус Эссенции Бога (монеты гарант, очки перерождения — шанс x2 при
    зелье удачи). Один UPDATE. Возвращает {'coins': N, 'rebirth': N, 'evo': 0 (не используется), 'is_god': bool}."""
    coin_bonus = 0
    if inventory_map.get("strange_coin", 0) > 0:
        coin_bonus += 5
    if inventory_map.get("warm_candle", 0) > 0:
        coin_bonus += 3
    if inventory_map.get("devotion_coin", 0) > 0:
        coin_bonus += 15
        if random.random() < 0.10:
            coin_bonus += 20

    rebirth_bonus = 0
    tier = get_active_unique_tier(active_items)
    is_god = tier in GOD_TIER_LIKE
    if is_god:
        max_coin = 70 if tier == "koshko_amulet" else 50
        coin_bonus += random.randint(1, max_coin)
        rebirth_chance = 0.60 if luck_boost else 0.30
        if random.random() < rebirth_chance:
            rebirth_bonus += random.randint(1, 3)

    if coin_bonus or rebirth_bonus:
        await db_exec(
            "UPDATE users SET coins = coins + ?, rebirth_points = rebirth_points + ? "
            "WHERE user_id = ?",
            (coin_bonus, rebirth_bonus, user_id),
        )
    return {"coins": coin_bonus, "rebirth": rebirth_bonus, "evo": 0, "is_god": is_god, "tier": tier}

async def apply_vase_proc(user_id: int, inventory_map: dict, luck_boost: bool = False) -> str:
    """Проки пассивных ваз при фарме ног. Срабатывает только самая сильная имеющаяся ваза.
    luck_boost (зелье удачи) удваивает эффективный ролл — вдвое повышает шанс на каждый порог."""
    roll_scale = 0.5 if luck_boost else 1.0
    if inventory_map.get("godly_vase", 0) > 0:
        roll = random.random() * roll_scale
        if roll < 0.002:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 400 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_GODLY_VASE} Боготворная ваза: СУПЕР УДАЧА! +400🉑!"
        if roll < 0.022:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 20 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_GODLY_VASE} Боготворная ваза: +20🉑!"
        if roll < 0.122:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 10 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_GODLY_VASE} Боготворная ваза: +10🉑!"
        if roll < 0.322:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 6 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_GODLY_VASE} Боготворная ваза: +6🉑!"
        if roll < 1.122:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 2 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_GODLY_VASE} Боготворная ваза: +2🉑!"
        return ""
    if inventory_map.get("golden_vase", 0) > 0:
        if random.random() * roll_scale < 0.06:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 1 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_GOLDEN_VASE} Золотая ваза: +1🉑!"
        return ""
    if inventory_map.get("old_vase", 0) > 0:
        if random.random() * roll_scale < 0.05:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 1 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_OLD_VASE} Старая ваза: +1🉑!"
        return ""
    return ""

def _random_booster_pool() -> list:
    """Все выбиваемые/крафтовые бустеры (boost_percent > 0), кроме предметов 1+ уровня крафта
    (см. RECIPES) — используется шансом на выдачу бустера от 🔮 Шара Хроноса."""
    pool = []
    for key, (_, _, boost_percent, _) in ITEMS.items():
        if boost_percent <= 0:
            continue
        recipe = RECIPES.get(key)
        if recipe and recipe.get("level", 0) >= 1:
            continue
        pool.append(key)
    return pool

async def apply_chaos_orb_proc(user_id: int, active_items) -> str:
    """🌀 Шар хаоса: пока экипирован, шанс 2% при фарме ног поймать бонус-фарму
    (случайное количество очков ноги от 1 до 10 000 000)."""
    if "chaos_orb" not in set(_normalize_active_items(active_items)):
        return ""
    if random.random() >= CHAOS_ORB_FARM_CHANCE:
        return ""
    bonus = random.randint(CHAOS_ORB_FARM_MIN, CHAOS_ORB_FARM_MAX)
    await db_exec("UPDATE users SET score = score + ? WHERE user_id = ?", (bonus, user_id))
    return f"\n🌀 Шар хаоса: РЕДКИЙ ПРОК! +{bonus} очков ноги!"

async def apply_blazing_necklace_proc(user_id: int, active_items) -> str:
    """🔥📿 Ожерелье пылающей звезды: пока экипировано, при фарме ног — шанс 1.7% дать
    1-15 очков перерождения и независимый шанс 1.2% дать 1-3 очка престижа."""
    if "blazing_star_necklace" not in set(_normalize_active_items(active_items)):
        return ""
    text = ""
    if random.random() < BLAZING_NECKLACE_REBIRTH_CHANCE:
        gained = random.randint(*BLAZING_NECKLACE_REBIRTH_RANGE)
        await db_exec("UPDATE users SET rebirth_points = rebirth_points + ? WHERE user_id = ?", (gained, user_id))
        text += f"\n{ITEMS['blazing_star_necklace'][0]} Ожерелье пылающей звезды: +{gained}🉑!"
    if random.random() < BLAZING_NECKLACE_PRESTIGE_CHANCE:
        gained = random.randint(*BLAZING_NECKLACE_PRESTIGE_RANGE)
        await db_exec("UPDATE users SET prestige_points = prestige_points + ? WHERE user_id = ?", (gained, user_id))
        text += f"\n{ITEMS['blazing_star_necklace'][0]} Ожерелье пылающей звезды: +{gained} очков престижа!"
    return text

async def apply_star_necklace_proc(user_id: int, active_items) -> str:
    """📿 Ожерелье из звёзд: пока экипировано, при фарме ног — шанс 2.5% выдать
    случайный предмет из Базового кейса (кейс 1, крафт-уровень 1)."""
    if "star_necklace" not in set(_normalize_active_items(active_items)):
        return ""
    if random.random() >= STAR_NECKLACE_CASE1_DROP_CHANCE:
        return ""
    item_key = random.choice(CASES[1]["pool"])
    await add_item(user_id, item_key)
    emoji, name, _, _ = ITEMS[item_key]
    return f"\n{ITEMS['star_necklace'][0]} Ожерелье из звёзд: выпал {emoji} {name}!"

def apply_coin_tree_farm_roll(gained: int, active_items) -> tuple:
    """🟤 Монета Ногости / 🔶 Монета Бога Ногости: независимый ролл на КАЖДОМ базовом фарме
    ног (после всех обычных множителей, включая x3/x6 boost_percent самих этих монет —
    те уже учтены в get_multiplier()). Срабатывает только самая сильная экипированная монета
    из пары (Бог > обычная), как и остальные парные бустеры в игре.
    Возвращает (новое gained, текст для ответа)."""
    equipped = set(_normalize_active_items(active_items))
    if "godly_nogost_coin" in equipped:
        roll = random.random()
        if roll < 0.10:
            bonus_gained = gained * 5
            return bonus_gained, f"\n{PREMIUM_GODLY_NOGOST_COIN} Монета Бога Ногости: x5 к фарму! +{bonus_gained - gained} очков ноги!"
        if roll < 0.30:
            bonus_gained = gained * 3
            return bonus_gained, f"\n{PREMIUM_GODLY_NOGOST_COIN} Монета Бога Ногости: x3 к фарму! +{bonus_gained - gained} очков ноги!"
        return gained, ""
    if "nogost_coin" in equipped:
        roll = random.random()
        if roll < 0.05:
            bonus_gained = gained * 5
            return bonus_gained, f"\n{PREMIUM_NOGOST_COIN} Монета Ногости: x5 к фарму! +{bonus_gained - gained} очков ноги!"
        if roll < 0.25:
            bonus_gained = gained * 3
            return bonus_gained, f"\n{PREMIUM_NOGOST_COIN} Монета Ногости: x3 к фарму! +{bonus_gained - gained} очков ноги!"
        return gained, ""
    return gained, ""

async def apply_godly_nogost_coin_case_proc(user_id: int, inventory_map: dict) -> str:
    """🔶 Монета Бога Ногости: пассивно (даже не экипирована — работает лёжа в инвентаре, как
    и остальные пассивные монеты) шанс 0.7% при базовом фарме ног дать +100 очков престижа
    и +5 000 000 (5кк) очков ноги одним общим проком за фарм."""
    if inventory_map.get("godly_nogost_coin", 0) <= 0:
        return ""
    if random.random() >= 0.007:
        return ""
    await db_exec(
        "UPDATE users SET score = score + 5000000, prestige_points = prestige_points + 100 WHERE user_id = ?",
        (user_id,),
    )
    return f"\n{PREMIUM_GODLY_NOGOST_COIN} Монета Бога Ногости: УДАЧА! +100🔮 и +5 000 000 очков ноги!"

async def apply_craft_coin_proc(user_id: int, inventory_map: dict) -> str:
    """🔘 Монета Крафта: пассивно (лёжа в инвентаре) шанс 5% при отправке в чат сообщения
    с эмодзи ноги (🦵/🦿) дать +1 💠 очко крафта."""
    if inventory_map.get("craft_coin", 0) <= 0:
        return ""
    if random.random() >= 0.05:
        return ""
    await db_exec("UPDATE users SET craft_points = craft_points + 1 WHERE user_id = ?", (user_id,))
    return f"\n{PREMIUM_CRAFT_COIN} Монета Крафта: +1💠 очко крафта!"

async def apply_bitcoin_proc(user_id: int, inventory_map: dict) -> str:
    """🟠 Биткоин: пассивно (лёжа в инвентаре) шанс 0.05% при базовом фарме ног дать
    +15 000 000 (15кк) 🪙 монет."""
    if inventory_map.get("bitcoin", 0) <= 0:
        return ""
    if random.random() >= 0.0005:
        return ""
    await db_exec("UPDATE users SET coins = coins + 15000000 WHERE user_id = ?", (user_id,))
    return f"\n{PREMIUM_BITCOIN} Биткоин: КРИПТО-ДЖЕКПОТ! +15 000 000{PREMIUM_BITCOIN}!"

async def apply_rebirth_coin_proc(user_id: int, inventory_map: dict) -> str:
    """🟣 Монета Перерождения: пассивно (лёжа в инвентаре) при КАЖДОМ базовом фарме ног
    даёт +2 🉑 очка перерождения гарантированно."""
    if inventory_map.get("rebirth_coin", 0) <= 0:
        return ""
    await db_exec("UPDATE users SET rebirth_points = rebirth_points + 2 WHERE user_id = ?", (user_id,))
    return f"\n{PREMIUM_REBIRTH_COIN} Монета Перерождения: +2🉑!"

async def apply_chronos_orb_procs(user_id: int, active_items) -> tuple:
    """🔮 Хвост Джевила: пока экипирован, при каждом фарме ног независимо проверяются все
    эффекты — несколько могут сработать за один фарм одновременно.
    Возвращает (текст_для_ответа, сбросить_кулдаун: bool, доп_множитель_фарма: float)."""
    if "chronos_orb" not in set(_normalize_active_items(active_items)):
        return "", False, 1.0

    lines = []
    reset_cd = False
    farm_extra_mult = random.uniform(CHRONOS_ORB_FARM_MULT_MIN, CHRONOS_ORB_FARM_MULT_MAX)
    lines.append(f"\n🔮 Хвост Джевила: рандом-множитель фарма x{farm_extra_mult:.2f}")

    if random.random() < CHRONOS_ORB_REBIRTH_CHANCE:
        amount = random.randint(CHRONOS_ORB_REBIRTH_MIN, CHRONOS_ORB_REBIRTH_MAX)
        await db_exec("UPDATE users SET rebirth_points = rebirth_points + ? WHERE user_id = ?", (amount, user_id))
        lines.append(f"🔮 Хвост Джевила: +{amount} 🉑!")

    if random.random() < CHRONOS_ORB_COIN_CHANCE:
        amount = random.randint(CHRONOS_ORB_COIN_MIN, CHRONOS_ORB_COIN_MAX)
        await db_exec("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
        lines.append(f"🔮 Хвост Джевила: +{amount} 🪙!")

    if random.random() < CHRONOS_ORB_LEGS_CHANCE:
        amount = random.randint(CHRONOS_ORB_LEGS_MIN, CHRONOS_ORB_LEGS_MAX)
        await db_exec("UPDATE users SET score = score + ? WHERE user_id = ?", (amount, user_id))
        lines.append(f"🔮 Хвост Джевила: +{amount} очков ноги!")

    if random.random() < CHRONOS_ORB_NO_CD_CHANCE:
        reset_cd = True
        lines.append("🔮 Хвост Джевила: кулдаун фермы обнулён!")

    if random.random() < CHRONOS_ORB_PRESTIGE_CHANCE:
        amount = random.randint(CHRONOS_ORB_PRESTIGE_MIN, CHRONOS_ORB_PRESTIGE_MAX)
        if amount > 0:
            await db_exec("UPDATE users SET prestige_points = prestige_points + ? WHERE user_id = ?", (amount, user_id))
            lines.append(f"🔮 Хвост Джевила: +{amount} 🔮 очков престижа!")

    if random.random() < CHRONOS_ORB_POTION_CHANCE:
        potion_key = random.choice(POTION_ORDER)
        stock_row = await db_query_one("SELECT potion_stock FROM users WHERE user_id = ?", (user_id,))
        stock = parse_potion_stock(stock_row[0] if stock_row else "")
        stock[potion_key] = stock.get(potion_key, 0) + 1
        await db_exec("UPDATE users SET potion_stock = ? WHERE user_id = ?", (format_potion_stock(stock), user_id))
        cfg = POTIONS[potion_key]
        lines.append(f"🔮 Хвост Джевила: +1 {cfg['emoji']} {esc(cfg['name'])}!")

    if random.random() < CHRONOS_ORB_BOOSTER_CHANCE:
        pool = _random_booster_pool()
        if pool:
            booster_key = random.choice(pool)
            await add_item(user_id, booster_key, 1)
            emoji, name, _, _ = ITEMS[booster_key]
            lines.append(f"🔮 Хвост Джевила: +1 {emoji} {esc(name)}!")

    if random.random() < CHRONOS_ORB_BADGE_CHANCE:
        await add_promo_badge(user_id, "chaos_master")
        emoji, name = PROMO_BADGES["chaos_master"]
        lines.append(f"🔮 Хвост Джевила: ПОЛУЧЕН БЕЙДЖ {emoji} «{esc(name)}»!!!")

    if random.random() < CHRONOS_ORB_STRANGE_COIN_CHANCE:
        await add_item(user_id, "strange_coin", 1)
        lines.append(f"🔮 Хвост Джевила: +1 {ITEMS['strange_coin'][0]} Странная монета!")

    if random.random() < CHRONOS_ORB_OLD_VASE_CHANCE:
        await add_item(user_id, "old_vase", 1)
        lines.append(f"🔮 Хвост Джевила: +1 {ITEMS['old_vase'][0]} Старая ваза!")

    return "\n".join(lines), reset_cd, farm_extra_mult

async def chronos_orb_boost_loop():
    """Фоновый таск: раз в CHRONOS_BOOST_INTERVAL (5 мин) пересчитывает рандомный % буста
    (10-400%) для ВСЕХ игроков сразу — не только для тех, у кого экипирован Хвост Джевила
    (дёшево одним UPDATE, а не по каждому фарму), см. get_multiplier(). Первый пересчёт —
    сразу при старте бота, чтобы буст не простаивал на 0%/100% до первого 5-минутного тика."""
    while True:
        try:
            new_pct = random.randint(CHRONOS_BOOST_MIN, CHRONOS_BOOST_MAX)
            await db_exec("UPDATE users SET chronos_boost_pct = ?", (new_pct,))
        except Exception as e:
            print(f"chronos_orb_boost_loop ошибка: {e}")
        await asyncio.sleep(CHRONOS_BOOST_INTERVAL)

AUTO_LOG_CLEANUP_INTERVAL = 24 * 60 * 60
AUTO_AUDIT_LOG_DAYS = 7
AUTO_PLAYER_LOG_DAYS = 2

async def auto_log_cleanup_loop():
    """Фоновый таск: раз в сутки сам чистит старые записи логов — те же сроки,
    что и дефолты ручных команд !чистлоги / !чистлоги игроки. player_action_log
    пишется на КАЖДУЮ команду каждого игрока (см. ThrottleMiddleware) и без
    регулярной чистки растёт быстрее всего, раздувая БД и, как следствие, время
    отклика на запросы к ней. Первый прогон — не сразу при старте (сон в начале
    цикла), чтобы не толкаться с init_db на старте бота."""
    while True:
        await asyncio.sleep(AUTO_LOG_CLEANUP_INTERVAL)
        try:
            audit_cutoff = int(time.time()) - AUTO_AUDIT_LOG_DAYS * 86400
            await db_exec("DELETE FROM audit_log WHERE ts < ?", (audit_cutoff,))
            player_cutoff = int(time.time()) - AUTO_PLAYER_LOG_DAYS * 86400
            await db_exec("DELETE FROM player_action_log WHERE ts < ?", (player_cutoff,))
        except Exception as e:
            print(f"auto_log_cleanup_loop ошибка: {e}")

async def is_event_active() -> bool:
    active, _ = await get_event_state()
    return active

_event_state_cache = {"value": None, "until": 0.0}
_EVENT_STATE_TTL = 3.0

async def get_event_state():
    """Возвращает (активен: bool, множитель: float) с учётом автоистечения по времени.
    Кэшируется на _EVENT_STATE_TTL секунд — см. _event_state_cache."""
    now_mono = time.monotonic()
    if _event_state_cache["value"] is not None and now_mono < _event_state_cache["until"]:
        return _event_state_cache["value"]

    rows = await db_query(
        "SELECT key, value FROM settings WHERE key IN ('event_active', 'event_multiplier', 'event_until')"
    )
    d = {k: v for k, v in rows}
    if d.get("event_active") != "1":
        result = (False, 1.0)
    else:
        until = int(d.get("event_until") or 0)
        if until and int(time.time()) > until:
            await db_exec("UPDATE settings SET value = '0' WHERE key = 'event_active'")
            result = (False, 1.0)
        else:
            mult = float(d.get("event_multiplier") or 2)
            result = (True, mult)

    _event_state_cache["value"] = result
    _event_state_cache["until"] = now_mono + _EVENT_STATE_TTL
    return result

def _invalidate_event_state_cache():
    _event_state_cache["value"] = None

async def get_event_multiplier() -> float:
    active, mult = await get_event_state()
    return mult if active else 1.0

async def get_personal_multiplier(user_id: int) -> float:
    """Личный временный буст фермы игроку (!мультипликатор ферма), с автоистечением."""
    row = await db_query_one("SELECT multiplier, until FROM personal_boosts WHERE user_id = ?", (user_id,))
    if not row:
        return 1.0
    multiplier, until = row
    if until and int(time.time()) > until:
        await db_exec("DELETE FROM personal_boosts WHERE user_id = ?", (user_id,))
        return 1.0
    return float(multiplier)

async def log_admin_action(message: Message):
    admin_username = message.from_user.username or str(message.from_user.id)
    await db_exec(
        "INSERT INTO audit_log (ts, admin_username, command) VALUES (?, ?, ?)",
        (int(time.time()), admin_username, message.text.strip()[:200]),
    )

PLAYER_LOG_MIN_INTERVAL = 1.0
_player_log_last = {}
_player_log_skipped = {}
_player_log_calls_since_cleanup = 0
_PLAYER_LOG_CLEANUP_EVERY = 500

PLAYER_LOG_FLUSH_INTERVAL = 5.0
_player_log_buffer: list = []

def _cleanup_player_log_throttle(now: float):
    ttl = PLAYER_LOG_MIN_INTERVAL * 20
    stale = [uid for uid, t in _player_log_last.items() if now - t > ttl]
    for uid in stale:
        del _player_log_last[uid]
        _player_log_skipped.pop(uid, None)

async def _log_player_action(user_id: int, username: str, text: str):
    global _player_log_calls_since_cleanup
    now = time.monotonic()
    last = _player_log_last.get(user_id, 0)
    if now - last < PLAYER_LOG_MIN_INTERVAL:
        _player_log_skipped[user_id] = _player_log_skipped.get(user_id, 0) + 1
        return
    skipped = _player_log_skipped.pop(user_id, 0)
    _player_log_last[user_id] = now

    _player_log_calls_since_cleanup += 1
    if _player_log_calls_since_cleanup >= _PLAYER_LOG_CLEANUP_EVERY:
        _player_log_calls_since_cleanup = 0
        _cleanup_player_log_throttle(now)

    command = text.strip()[:200]
    if skipped:
        command = f"{command} [+{skipped} пропущено за <{PLAYER_LOG_MIN_INTERVAL:.0f}с]"
    _player_log_buffer.append((int(time.time()), user_id, username, command))

async def _flush_player_log_buffer():
    """Фоновый цикл: раз в PLAYER_LOG_FLUSH_INTERVAL сек сбрасывает накопленные
    записи player_action_log ОДНИМ запросом (executemany на стороне воркера),
    вместо отдельного INSERT на каждое действие игрока."""
    while True:
        await asyncio.sleep(PLAYER_LOG_FLUSH_INTERVAL)
        if not _player_log_buffer:
            continue
        batch, _player_log_buffer[:] = _player_log_buffer[:], []
        try:
            await db_exec_many(
                "INSERT INTO player_action_log (ts, user_id, username, command) VALUES (?, ?, ?, ?)",
                batch,
            )
        except Exception as e:
            print(f"_flush_player_log_buffer ошибка: {e}")

async def track_membership(user_id: int, chat_id: int):
    await db_exec("INSERT OR IGNORE INTO chat_members (user_id, chat_id) VALUES (?, ?)", (user_id, chat_id))

async def get_all_chat_ids():
    rows = await db_query("SELECT DISTINCT chat_id FROM chat_members")
    return [r[0] for r in rows]

async def build_top(chat_id, order_column: str, limit: int = 10):
    if chat_id is None:
        rows = await db_query(
            f"SELECT username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges, rebirth_points, rebirth_count, nickname, ultra_rebirth, promo_badges "
            f"FROM users WHERE (top_banned IS NULL OR top_banned = 0) ORDER BY {order_column} DESC LIMIT ?",
            (limit,),
        )
    else:
        rows = await db_query(
            f"""SELECT u.username, u.score, u.evolution_level, u.coins, u.cases_opened, u.total_farmed, u.vip_until, u.hidden_badges, u.rebirth_points, u.rebirth_count, u.nickname, u.ultra_rebirth, u.promo_badges
                FROM users u JOIN chat_members cm ON u.user_id = cm.user_id
                WHERE cm.chat_id = ? AND (u.top_banned IS NULL OR u.top_banned = 0) ORDER BY u.{order_column} DESC LIMIT ?""",
            (chat_id, limit),
        )
    return rows

