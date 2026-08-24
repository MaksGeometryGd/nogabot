"""
handlers_profile.py — профиль игрока: настройки уведомлений/ников,
VIP-статус и покупка VIP за звёзды, авто-режимы (эволюция/перерождение/
продажа), бейджи, счётчик "ног" (текстовые триггеры), карточка профиля,
топы игроков.
"""
from aiogram import F
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice,
    Message, PreCheckoutQuery,
)
import asyncio
import random
import re
import time
from urllib.parse import quote

from premium_emoji import PREMIUM_VIP_BADGE
from config import (
    ADMIN_USERNAME, ADMIN_USER_ID, LEG_FARM_COOLDOWN, LEG_POINT,
    LEG_REPLY_COOLDOWN, MEK_POINT, TEXTS, VIP_BOOST, VIP_FOREVER_SECONDS,
    VIP_STARS_PRICE,
)
from game_data import (
    CASES, CASE_SELLABLE_ITEMS, CHRONOS_ORB_FLAVOR, DRAGON_CLAW_POTION_MULT,
    GOD_ESSENCE_FLAVOR, ITEMS, KOSHKO_AMULET_FLAVOR, PAW_POINT_MULTIPLIER,
    REBIRTH_MIN_EVO, TIDE_WAVE_PROC_CHANCE, active_farm_limits,
    apply_case_reward, format_auto_sell_items, parse_auto_sell_items,
)
from command_patterns import INFO_RE, NICK_SET_RE
from text_utils import esc, safe_edit_text, safe_reply
from state import bot, dp
from economy import (
    _normalize_active_items, active_potions_now, add_item, apply_bitcoin_proc,
    apply_chaos_orb_proc, apply_chronos_orb_procs, apply_craft_coin_proc,
    apply_farm_bonuses, apply_godly_nogost_coin_case_proc, apply_rebirth_coin_proc,
    apply_vase_proc, badge_list, badges_keyboard, build_top,
    case_price_with_discount, db_exec, db_query_one, display_name, ensure_user,
    farm_yield_multiplier, get_badges, get_event_multiplier, get_inventory,
    get_level_index, get_level_visual, get_multiplier, get_personal_multiplier,
    get_user, get_user_by_username, next_level_text, parse_equipped, parse_hidden,
    parse_prestige_upgrades, parse_promo_badges, parse_upgrades, prestige_bonus,
    total_flat_bonus,
)
from game_logic import is_vip_active, roll_case_item
from handlers_inventory import autosell_keyboard, format_autosell_text
from handlers_cases_evo import try_auto_evolve, try_auto_rebirth

async def maybe_announce_levelup(message: Message, username: str, old_score: int, new_score: int,
                                  evolution_level: int, notify: bool, rebirth_count: int = 0,
                                  ultra_rebirth: bool = False):
    if not notify:
        return
    old_level = get_level_index(old_score, evolution_level, rebirth_count, ultra_rebirth)
    new_level = get_level_index(new_score, evolution_level, rebirth_count, ultra_rebirth)
    if new_level <= old_level:
        return
    emoji, name, show_level = get_level_visual(new_level)
    lvl_part = f" ({new_level} лвл)" if show_level else ""
    name_part = f" {esc(name)}" if name else ""
    await message.reply(TEXTS["maybe_announce_levelup_1"].format(v0=esc(username), v1=emoji, v2=name_part, v3=lvl_part))

@dp.message(F.text.lower() == "смс выкл")
async def notify_off(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)
    await db_exec("UPDATE users SET levelup_notify = 0 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["notify_off_1"])

@dp.message(F.text.lower() == "смс вкл")
async def notify_on(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)
    await db_exec("UPDATE users SET levelup_notify = 1 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["notify_on_1"])

@dp.message(F.text.regexp(r"(?i)^\+ник\s+.+$"))
async def set_nickname(message: Message):
    match = NICK_SET_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["nick_set_empty"])
        return

    nickname = match.group(1).strip().strip('"').strip("'").strip()
    if not nickname:
        await message.reply(TEXTS["nick_set_empty"])
        return
    if len(nickname) > 50:
        await message.reply(TEXTS["nick_set_too_long"].format(v0=len(nickname)))
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    taken = await db_query_one(
        "SELECT user_id FROM users WHERE lower(nickname) = lower(?) AND user_id != ?",
        (nickname, user_id),
    )
    if taken:
        await message.reply(TEXTS["nick_set_taken"])
        return

    await db_exec("UPDATE users SET nickname = ? WHERE user_id = ?", (nickname, user_id))
    await safe_reply(message, TEXTS["nick_set_ok"].format(v0=esc(nickname)))

@dp.message(F.text.lower() == "-ник")
async def clear_nickname(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)
    await db_exec("UPDATE users SET nickname = NULL WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["nick_clear_ok"])

def buy_vip_keyboard(user_id: int) -> InlineKeyboardMarkup:
    contact_text = quote("Привет! Хочу оформить VIP-статус")
    contact_url = f"https://t.me/{ADMIN_USERNAME}?text={contact_text}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Написать админу", url=contact_url)],
    ])

@dp.message(F.text.lower() == "вип")
async def vip_info_command(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    vip_until = row[12]

    if is_vip_active(vip_until):
        await message.reply(TEXTS["vip_info_command_1"])
        return

    await message.reply(
        TEXTS["vip_info_command_2"].format(v0=round(VIP_BOOST * 100), v1=VIP_STARS_PRICE),
        reply_markup=buy_vip_keyboard(user_id),
    )

@dp.message(F.text.lower().in_({"авто эво вкл", "авто эволюция вкл"}))
async def auto_evolve_on(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    vip_until = row[12]

    if not is_vip_active(vip_until):
        await message.reply(TEXTS["auto_evolve_not_vip_1"])
        return

    await db_exec("UPDATE users SET auto_evolve = 1 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["auto_evolve_on_1"])

@dp.message(F.text.lower().in_({"авто эво выкл", "авто эволюция выкл"}))
async def auto_evolve_off(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    await db_exec("UPDATE users SET auto_evolve = 0 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["auto_evolve_off_1"])

@dp.message(F.text.lower().in_({"авто перерождение вкл", "авто рб вкл", "авто ребёрт вкл", "авто реберт вкл"}))
async def auto_rebirth_on(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    vip_until = row[12]

    if not is_vip_active(vip_until):
        await message.reply(TEXTS["auto_rebirth_not_vip_1"])
        return

    await db_exec("UPDATE users SET auto_rebirth = 1 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["auto_rebirth_on_1"].format(v0=REBIRTH_MIN_EVO))

@dp.message(F.text.lower().in_({"авто перерождение выкл", "авто рб выкл", "авто ребёрт выкл", "авто реберт выкл"}))
async def auto_rebirth_off(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    await db_exec("UPDATE users SET auto_rebirth = 0 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["auto_rebirth_off_1"])

@dp.message(F.text.lower() == "авто продажа вкл")
async def auto_sell_on(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    await db_exec("UPDATE users SET auto_sell = 1 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["auto_sell_on_1"])

@dp.message(F.text.lower() == "авто продажа выкл")
async def auto_sell_off(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    await db_exec("UPDATE users SET auto_sell = 0 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["auto_sell_off_1"])

@dp.message(F.text.lower().in_({"авто продажа настройка", "авто продажа конфиг", "авто продажа настройки"}))
async def auto_sell_config(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    auto_sell_enabled = bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])
    await message.reply(
        format_autosell_text(auto_sell_enabled, auto_sell_items),
        reply_markup=autosell_keyboard(auto_sell_enabled, auto_sell_items, user_id),
    )

@dp.callback_query(F.data.startswith("autosell_toggle:"))
async def autosell_toggle(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    item_key = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    if item_key not in CASE_SELLABLE_ITEMS:
        await callback.answer()
        return
    await callback.answer()

    row = await get_user(owner_id)
    auto_sell_enabled = bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])

    if item_key in auto_sell_items:
        auto_sell_items.discard(item_key)
    else:
        auto_sell_items.add(item_key)

    await db_exec("UPDATE users SET auto_sell_items = ? WHERE user_id = ?", (format_auto_sell_items(auto_sell_items), owner_id))
    await safe_edit_text(callback, 
        format_autosell_text(auto_sell_enabled, auto_sell_items, page),
        reply_markup=autosell_keyboard(auto_sell_enabled, auto_sell_items, owner_id, page),
    )

@dp.callback_query(F.data.startswith("autosell_switch:"))
async def autosell_switch(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return

    row = await get_user(owner_id)
    auto_sell_enabled = not bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])
    await callback.answer(TEXTS["auto_sell_on_1"] if auto_sell_enabled else TEXTS["auto_sell_off_1"])

    await db_exec("UPDATE users SET auto_sell = ? WHERE user_id = ?", (1 if auto_sell_enabled else 0, owner_id))
    await safe_edit_text(callback, 
        format_autosell_text(auto_sell_enabled, auto_sell_items, page),
        reply_markup=autosell_keyboard(auto_sell_enabled, auto_sell_items, owner_id, page),
    )

@dp.callback_query(F.data.startswith("autosell_page:"))
async def autosell_page_nav(callback: CallbackQuery):
    _, owner_str, page_str = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    auto_sell_enabled = bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])
    await safe_edit_text(callback, 
        format_autosell_text(auto_sell_enabled, auto_sell_items, page),
        reply_markup=autosell_keyboard(auto_sell_enabled, auto_sell_items, owner_id, page),
    )

VIP_CASE_OPEN_RE = re.compile(r"^вип открыть кейс\s+(\d+)\s+(\d+)$", re.IGNORECASE)
VIP_CASE_OPEN_LIMIT = 20

@dp.message(F.text.regexp(r"(?i)^вип открыть кейс\s+"))
async def vip_open_case_bulk(message: Message):
    """VIP-версия owner-команды '!дать кейс' — открывает несколько кейсов разом,
    но платно (списывает монеты за каждый кейс) и только себе, лимит 20 за раз."""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    match = VIP_CASE_OPEN_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["vip_case_open_1"])
        return

    row = await ensure_user(user_id, username)
    vip_until = row[12]
    if not is_vip_active(vip_until):
        await message.reply(TEXTS["vip_case_open_2"])
        return

    case_num = int(match.group(1))
    count = int(match.group(2))
    case = CASES.get(case_num)
    if not case:
        await message.reply(TEXTS["vip_case_open_3"])
        return
    if count < 1 or count > VIP_CASE_OPEN_LIMIT:
        await message.reply(TEXTS["vip_case_open_4"])
        return

    coins = row[5]
    upgrades = parse_upgrades(row[16])
    auto_sell_enabled = bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])
    unit_price = case_price_with_discount(case["price"], upgrades)
    total_price = unit_price * count

    if coins < total_price:
        await message.reply(TEXTS["vip_case_open_5"].format(v0=total_price, v1=coins))
        return

    won = {}
    sold = {}
    sold_coins_total = 0
    for _ in range(count):
        item_key = roll_case_item(case_num)
        coins_got, _ = await apply_case_reward(user_id, item_key, upgrades, auto_sell_enabled, auto_sell_items)
        if coins_got:
            sold[item_key] = sold.get(item_key, 0) + 1
            sold_coins_total += coins_got
        else:
            won[item_key] = won.get(item_key, 0) + 1

    new_coins = coins - total_price + sold_coins_total
    await db_exec(
        "UPDATE users SET coins = coins - ?, cases_opened = cases_opened + ? WHERE user_id = ?",
        (total_price, count, user_id),
    )

    loot_lines = "\n".join(f"● {ITEMS[k][0]} {esc(ITEMS[k][1])} × {qty}" for k, qty in won.items())
    if sold:
        sold_lines = ", ".join(f"{ITEMS[k][0]} {esc(ITEMS[k][1])} × {qty}" for k, qty in sold.items())
        loot_lines += f"\n💰 Авто-продано: {sold_lines} (+{sold_coins_total} 🪙)"
    await safe_reply(
        message,
        TEXTS["vip_case_open_6"].format(v0=count, v1=esc(case["name"]), v2=total_price, v3=new_coins, v4=loot_lines),
    )

@dp.callback_query(F.data.startswith("buy_vip:"))
async def buy_vip_invoice(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["buy_vip_invoice_1"], show_alert=True)
        return

    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title="VIP статус навсегда",
        description=f"Постоянный буст +{round(VIP_BOOST * 100)}% к добыче ноги.",
        payload=f"vip:{owner_id}",
        currency="XTR",
        prices=[LabeledPrice(label="VIP навсегда", amount=VIP_STARS_PRICE)],
        provider_token="",
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

    await message.reply(TEXTS["process_successful_payment_1"])

@dp.message(F.text.lower() == "бейджи")
async def badges_menu(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    evolution_level, cases_opened, total_farmed, vip_until = row[3], row[7], row[8], row[12]
    hidden = parse_hidden(row[13] if len(row) > 13 else "")
    promo_badges = parse_promo_badges(row[33] if len(row) > 33 else "")
    vip_active = is_vip_active(vip_until)

    earned = badge_list(username, evolution_level, cases_opened, total_farmed, vip_active, promo_badges)
    if not earned:
        await message.reply(TEXTS["badges_menu_1"])
        return

    kb = badges_keyboard(earned, hidden, user_id)
    await message.reply(TEXTS["badges_menu_2"], reply_markup=kb)

@dp.callback_query(F.data.startswith("badge:"))
async def toggle_badge(callback: CallbackQuery):
    _, owner_str, key = callback.data.split(":")
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["toggle_badge_1"], show_alert=True)
        return
    await callback.answer(TEXTS["toggle_badge_2"])

    row = await get_user(owner_id)
    username, evolution_level, cases_opened, total_farmed, vip_until = row[1], row[3], row[7], row[8], row[12]
    hidden = parse_hidden(row[13] if len(row) > 13 else "")
    promo_badges = parse_promo_badges(row[33] if len(row) > 33 else "")

    if key in hidden:
        hidden.discard(key)
    else:
        hidden.add(key)

    new_hidden_str = ",".join(sorted(hidden))
    await db_exec("UPDATE users SET hidden_badges = ? WHERE user_id = ?", (new_hidden_str, owner_id))

    vip_active = is_vip_active(vip_until)
    earned = badge_list(username, evolution_level, cases_opened, total_farmed, vip_active, promo_badges)
    kb = badges_keyboard(earned, hidden, owner_id)
    await safe_edit_text(callback, "🏷 Твои значки (жми, чтобы скрыть/показать в топах):", reply_markup=kb)

@dp.message(F.text.regexp(r"[🦵🦿]"))
async def count_legs(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    text = message.text

    if user_id != ADMIN_USER_ID:
        now_mono = time.monotonic()
        last = _leg_farm_last.get(user_id, 0)
        if now_mono - last < LEG_FARM_COOLDOWN:
            return
        _leg_farm_last[user_id] = now_mono

    row = await ensure_user(user_id, username)
    score, evolution_level, active_item = row[2], row[3], row[6]
    levelup_notify, vip_until = row[11], row[12]
    rebirth_points, rebirth_count = row[14], row[15]
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    ultra_rebirth = bool(row[21])
    auto_evolve_enabled = bool(row[22])
    auto_rebirth_enabled = bool(row[29])
    prestige_points = row[27]
    vip_active = is_vip_active(vip_until)
    potions = active_potions_now(row[23], active_items=active_items)
    prestige_upgrades = parse_prestige_upgrades(row[28])
    chronos_boost_pct = row[34] if len(row) > 34 else 100

    flat_bonus = total_flat_bonus(active_items)
    limits = active_farm_limits(active_items, prestige_upgrades)

    legs = min(text.count("🦵"), limits["leg_limit"])
    gained = legs * LEG_POINT

    mek = 0
    if evolution_level >= 1:
        mek = min(text.count("🦿"), limits["mek_limit"])
        gained += mek * MEK_POINT

    paw = min(text.count("🐾"), limits["paw_limit"])
    gained += paw * MEK_POINT * PAW_POINT_MULTIPLIER

    galaxy = min(text.count("🌌"), limits["galaxy_limit"])
    star = min(text.count("⭐️"), limits["star_limit"])

    if gained == 0:
        return

    gained += flat_bonus
    gained = round(gained * farm_yield_multiplier(upgrades))

    mult = get_multiplier(evolution_level, active_items, vip_active, upgrades, ultra_rebirth, chronos_boost_pct)
    event_mult, personal_mult, inv = await asyncio.gather(
        get_event_multiplier(), get_personal_multiplier(user_id), get_inventory(user_id)
    )
    p_yield_mult = 1 + 0.005 * prestige_bonus(prestige_upgrades, "p_farm_yield")
    total = round(gained * mult * event_mult * personal_mult * p_yield_mult)
    if galaxy:
        total = round(total * (1 + 0.20 * galaxy))
    if star:
        total = round(total * (2 ** star))
    potion_text = ""
    if "potion_speed" in potions:
        speed_mult = DRAGON_CLAW_POTION_MULT if "dragon_claw" in set(_normalize_active_items(active_items)) else 2
        total *= speed_mult
        potion_text += f"\n🧪⚡ Зелье ускорения: x{speed_mult} к добыче!"

    chronos_text, _chronos_reset_cd, chronos_farm_mult = await apply_chronos_orb_procs(user_id, active_items)
    if chronos_farm_mult != 1.0:
        total = round(total * chronos_farm_mult)
    new_score = score + total

    await db_exec(
        "UPDATE users SET score = ?, total_farmed = total_farmed + ? WHERE user_id = ?",
        (new_score, total, user_id),
    )

    await maybe_announce_levelup(message, username, score, new_score, evolution_level, bool(levelup_notify), rebirth_count, ultra_rebirth)

    auto_evo_text = ""
    if vip_active and auto_evolve_enabled:
        evolution_level, new_score, auto_evo_text = await try_auto_evolve(user_id, new_score, evolution_level, rebirth_count, active_items)

    auto_rebirth_text = ""
    if vip_active and auto_rebirth_enabled:
        new_score, evolution_level, rebirth_count, rebirth_points, prestige_points, auto_rebirth_text = await try_auto_rebirth(
            user_id, new_score, evolution_level, rebirth_count, rebirth_points, prestige_points, prestige_upgrades, active_items
        )

    inventory_map = {k: q for k, q in inv}
    luck_boost = "luck_x2" in potions
    vase_text = await apply_vase_proc(user_id, inventory_map, luck_boost)
    bonus = await apply_farm_bonuses(user_id, active_items, inventory_map, luck_boost)
    chaos_text = await apply_chaos_orb_proc(user_id, active_items)
    coin_tree_text = (
        await apply_godly_nogost_coin_case_proc(user_id, inventory_map)
        + await apply_bitcoin_proc(user_id, inventory_map)
        + await apply_rebirth_coin_proc(user_id, inventory_map)
        + await apply_craft_coin_proc(user_id, inventory_map)
    )

    now = time.monotonic()
    chat_id = message.chat.id
    if now - _last_leg_reply.get(chat_id, 0) < LEG_REPLY_COOLDOWN:
        return
    _last_leg_reply[chat_id] = now

    equipped_set = set(_normalize_active_items(active_items))

    tide_text = ""
    if "tide_wave" in equipped_set and random.random() < TIDE_WAVE_PROC_CHANCE:
        tide_item = roll_case_item(random.choice([1, 2]))
        await add_item(user_id, tide_item)
        tide_emoji, tide_name, _, _ = ITEMS[tide_item]
        tide_text = f"\n🌊 Прилив принёс: {tide_emoji} {esc(tide_name)}!"

    skull_prefix = "💀 Смерть близко.\n" if "warrior_skull" in equipped_set else ""

    parts = f"+{legs}🦵"
    if mek:
        parts += f" +{mek}🦿"
    if paw:
        parts += f" +{paw}🐾"
    if galaxy:
        parts += f" +{galaxy}🌌"
    if star:
        parts += f" +{star}⭐️"

    coin_text = f" +{bonus['coins']}🪙" if bonus["coins"] else ""
    extra_text = vase_text + auto_evo_text + auto_rebirth_text + potion_text + tide_text + chaos_text + chronos_text + coin_tree_text
    chronos_equipped = "chronos_orb" in set(_normalize_active_items(active_items))

    if bonus["is_god"]:
        flavor = CHRONOS_ORB_FLAVOR if chronos_equipped else (KOSHKO_AMULET_FLAVOR if bonus.get("tier") == "koshko_amulet" else GOD_ESSENCE_FLAVOR)
        god_extra = f" +{bonus['rebirth']}🉑" if bonus["rebirth"] else ""
        await safe_reply(
            message,
            skull_prefix + TEXTS["count_legs_1"].format(v0=flavor, v1=parts, v2=total, v3=coin_text, v4=god_extra, v5=new_score, v6=extra_text)
        )
        return

    if chronos_equipped:
        await safe_reply(
            message,
            skull_prefix + TEXTS["count_legs_1"].format(v0=CHRONOS_ORB_FLAVOR, v1=parts, v2=total, v3=coin_text, v4="", v5=new_score, v6=extra_text)
        )
        return

    await message.reply(
        skull_prefix + TEXTS["count_legs_2"].format(v0=parts, v1=total, v2=coin_text, v3=new_score, v4=extra_text)
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
    nickname = row[19] if len(row) > 19 else None
    ultra_rebirth = bool(row[21])
    vip_active = is_vip_active(vip_until)
    shown_name = display_name(username, nickname)

    level = get_level_index(score, evolution_level, rebirth_count, ultra_rebirth)
    emoji, name, show_level = get_level_visual(level)
    display_level = level
    nxt = next_level_text(score, evolution_level, rebirth_count, ultra_rebirth)
    chronos_boost_pct = row[34] if len(row) > 34 else 100
    mult = get_multiplier(evolution_level, active_items, vip_active, upgrades, ultra_rebirth, chronos_boost_pct)
    flat_bonus = total_flat_bonus(active_items)

    if vip_active:
        left = vip_until - int(time.time())
        d, rem = divmod(left, 86400)
        h = rem // 3600
        vip_line = f"● VIP статус: активен ({d} дн {h} ч) {PREMIUM_VIP_BADGE}\n"
    else:
        vip_line = "● VIP статус: не активен\n"

    lvl_line = f"● Уровень ноги: {display_level} лвл\n" if (show_level or ultra_rebirth) else ""
    name_part = f" {esc(name)}" if name else ""
    guarant_line = f"● Гарант-буст с предмета: +{flat_bonus} к итогу\n" if flat_bonus else ""
    rebirth_line = f"● Перерождений: {rebirth_count} (🉑 {rebirth_points})\n" if rebirth_count else ""
    ultra_line = "🌌 <b>Статус: После Ультра перерождения</b>\n" if ultra_rebirth else ""
    equipped_names = [ITEMS[k][1] for k in (active_items) if k and k in ITEMS]
    equip_line = ("● Экипировано:\n" + "\n".join(f"  {n}" for n in equipped_names) + "\n") if equipped_names else ""

    text = (
        f"👣 <b>ТВОЯ ЛЮТАЯ НОГОСТЬ, {esc(shown_name)}:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{ultra_line}"
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
        await message.reply(TEXTS["info_player_1"])
        return

    username = row[1]
    score, evolution_level, coins, active_item = row[2], row[3], row[5], row[6]
    cases_opened, total_farmed = row[7], row[8]
    vip_until = row[12]
    rebirth_count = row[15] if len(row) > 15 else 0
    hidden = parse_hidden(row[13] if len(row) > 13 else "")
    promo_badges = parse_promo_badges(row[33] if len(row) > 33 else "")
    nickname = row[19] if len(row) > 19 else None
    ultra_rebirth = bool(row[21]) if len(row) > 21 else False
    shown_name = display_name(username, nickname)
    vip_active = is_vip_active(vip_until)
    level = get_level_index(score, evolution_level, rebirth_count, ultra_rebirth)
    emoji, name, show_level = get_level_visual(level)
    lvl_part = f" ({level} лвл)" if show_level else ""
    name_part = f" {esc(name)}" if name else ""
    item_text = ITEMS[active_item][1] if active_item and active_item in ITEMS else "нет"
    vip_text = "активен" if vip_active else "не активен"
    badges = get_badges(username, evolution_level, cases_opened, total_farmed, vip_active, hidden, promo_badges)

    text = (
        f"👣 <b>Инфо об игроке {esc(shown_name)}{badges}:</b>\n"
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
        await message.reply(TEXTS["send_legs_top_1"])
        return

    text = f"🏆 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges, rebirth_points, rebirth_count, nickname, ultra_rebirth, promo_badges_raw) in enumerate(rows, 1):
        level = get_level_index(score, evolution_level, rebirth_count, bool(ultra_rebirth))
        emoji, name, show_level = get_level_visual(level)
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_hidden(hidden_badges), parse_promo_badges(promo_badges_raw))
        lvl_part = f" ({level} лвл)" if show_level else ""
        name_part = f" {esc(name)}" if name else ""
        text += f"{i}. {esc(display_name(username, nickname))}{badges} — <code>{score}</code>\n   └ {emoji}{name_part}{lvl_part} · эво {evolution_level}\n\n"

    await message.reply(text)

async def send_evo_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "evolution_level")

    if not rows:
        await message.reply(TEXTS["send_evo_top_1"])
        return

    text = f"🎆 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges, rebirth_points, rebirth_count, nickname, ultra_rebirth, promo_badges_raw) in enumerate(rows, 1):
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_hidden(hidden_badges), parse_promo_badges(promo_badges_raw))
        text += f"{i}. {esc(display_name(username, nickname))}{badges} — эво {evolution_level} ({score} очков)\n"

    await message.reply(text)

async def send_coin_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "coins")

    if not rows:
        await message.reply(TEXTS["send_coin_top_1"])
        return

    text = f"🪙 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges, rebirth_points, rebirth_count, nickname, ultra_rebirth, promo_badges_raw) in enumerate(rows, 1):
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_hidden(hidden_badges), parse_promo_badges(promo_badges_raw))
        text += f"{i}. {esc(display_name(username, nickname))}{badges} — {coins} 🪙\n"

    await message.reply(text)

async def send_rebirth_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "rebirth_points")

    if not rows:
        await message.reply(TEXTS["send_rebirth_top_1"])
        return

    text = f"🉑 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, hidden_badges, rebirth_points, rebirth_count, nickname, ultra_rebirth, promo_badges_raw) in enumerate(rows, 1):
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_hidden(hidden_badges), parse_promo_badges(promo_badges_raw))
        text += f"{i}. {esc(display_name(username, nickname))}{badges} — {rebirth_points} 🉑 (перерождений: {rebirth_count})\n"

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

