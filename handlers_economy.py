"""
handlers_economy.py — фарм ног, ежедневный бонус, все виды обмена валют
(ноги/монеты/очки крафта/очки перерождения), перевод валюты и предметов
между игроками, продажа и уничтожение предметов/бустеров.
"""
from aiogram import F
from aiogram.types import Message
import random
import time

from premium_emoji import PREMIUM_DAILY_CHARM
from config import (
    CRAFT_POINTS_EXCHANGE_RATE, DAILY_MIN_GAP, DAILY_STREAK_LIMIT,
    DAILY_TABLE, EXCHANGE_RATE, REVERSE_EXCHANGE_RATE, TEXTS,
)
from game_data import (
    CHRONOS_ORB_FLAVOR, DRAGON_CLAW_POTION_MULT, GOD_ESSENCE_FLAVOR, ITEMS,
    NON_TRADABLE_ITEMS, NO_CD_CHARGES_KEY, SELL_PRICE,
)
from command_patterns import (
    CRAFT_EXCHANGE_RE, CRAFT_EXCHANGE_TO_RE, EXCHANGE_RE, REVERSE_EXCHANGE_RE,
    _AMOUNT_TOKEN_RE,
)
from text_utils import esc, parse_amount, safe_reply
from state import dp
from economy import (
    _normalize_active_items, active_potions_now, add_item, apply_bitcoin_proc,
    apply_chaos_orb_proc, apply_chronos_orb_procs, apply_coin_tree_farm_roll,
    apply_farm_bonuses, apply_godly_nogost_coin_case_proc, apply_rebirth_coin_proc,
    apply_vase_proc, claim_offline_auto_farm, consume_no_cd_charge, db_exec,
    db_query_one, ensure_user, farm_cd_seconds, farm_range, farm_yield_multiplier,
    format_equipped, get_event_multiplier, get_inventory, get_level_index,
    get_multiplier, get_personal_multiplier, get_user, parse_equipped,
    parse_prestige_upgrades, parse_upgrades, prestige_bonus, remove_item,
    sell_bonus_coins, unequip_item, upgrade_level,
)
from game_logic import find_item_by_name, is_vip_active
from subscription import require_subscription
from handlers_cases_evo import try_auto_evolve, try_auto_rebirth
from handlers_profile import maybe_announce_levelup

@dp.message(F.text.lower().in_({"ферма", "фарма"}))
async def farm(message: Message):
    if not await require_subscription(message):
        return
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    now = int(time.time())

    row = await ensure_user(user_id, username)
    score, evolution_level, active_item = row[2], row[3], row[6]
    last_farm, levelup_notify, vip_until = row[4], row[11], row[12]
    rebirth_points, rebirth_count = row[14], row[15]
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    ultra_rebirth = bool(row[21])
    auto_evolve_enabled = bool(row[22])
    auto_rebirth_enabled = bool(row[29])
    prestige_points = row[27]
    vip_active = is_vip_active(vip_until)
    potions = active_potions_now(row[23], now, active_items)
    prestige_upgrades = parse_prestige_upgrades(row[28])
    chronos_boost_pct = row[34] if len(row) > 34 else 100

    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}
    has_time_particle = inventory_map.get("time_particle", 0) > 0

    cooldown = farm_cd_seconds(upgrades, active_items, has_time_particle, prestige_upgrades)
    has_no_cd = NO_CD_CHARGES_KEY in potions
    if not has_no_cd and now - last_farm < cooldown:
        left = cooldown - (now - last_farm)
        m, s = divmod(left, 60)
        await message.reply(TEXTS["farm_1"].format(v0=m, v1=s))
        return

    auto_legs, auto_coins, score, _coins_after = await claim_offline_auto_farm(user_id, row)

    low, high = farm_range(evolution_level)
    mult = get_multiplier(evolution_level, active_items, vip_active, upgrades, ultra_rebirth, chronos_boost_pct)
    event_mult = await get_event_multiplier()
    personal_mult = await get_personal_multiplier(user_id)
    p_yield_mult = 1 + 0.005 * prestige_bonus(prestige_upgrades, "p_farm_yield")
    gained = round(random.randint(low, high) * farm_yield_multiplier(upgrades) * mult * event_mult * personal_mult * p_yield_mult)
    potion_text = ""
    if "potion_speed" in potions:
        speed_mult = DRAGON_CLAW_POTION_MULT if "dragon_claw" in set(_normalize_active_items(active_items)) else 2
        gained *= speed_mult
        potion_text += f"\n🧪⚡ Зелье ускорения: x{speed_mult} к добыче!"

    chronos_text, chronos_reset_cd, chronos_farm_mult = await apply_chronos_orb_procs(user_id, active_items)
    if chronos_farm_mult != 1.0:
        gained = round(gained * chronos_farm_mult)

    gained, nogost_coin_text = apply_coin_tree_farm_roll(gained, active_items)
    new_score = score + gained

    new_last_farm = 0 if chronos_reset_cd else now
    await db_exec(
        "UPDATE users SET score = ?, last_farm = ?, total_farmed = total_farmed + ? WHERE user_id = ?",
        (new_score, new_last_farm, gained, user_id),
    )

    if has_no_cd:
        potions = await consume_no_cd_charge(user_id, potions)
        charges_left = potions.get(NO_CD_CHARGES_KEY, 0)
        potion_text += f"\n🧪🌀 Зелье без КД: заряд использован ({charges_left} ост.)"

    luck_boost = "luck_x2" in potions
    vase_text = await apply_vase_proc(user_id, inventory_map, luck_boost)
    bonus = await apply_farm_bonuses(user_id, active_items, inventory_map, luck_boost)
    chaos_text = await apply_chaos_orb_proc(user_id, active_items)
    coin_tree_text = (
        nogost_coin_text
        + await apply_godly_nogost_coin_case_proc(user_id, inventory_map)
        + await apply_bitcoin_proc(user_id, inventory_map)
        + await apply_rebirth_coin_proc(user_id, inventory_map)
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

    auto_text = ""
    if auto_legs or auto_coins:
        bits = []
        if auto_legs:
            bits.append(f"+{auto_legs} очков")
        if auto_coins:
            bits.append(f"+{auto_coins} 🪙")
        auto_text = f"\n⚙️ Авто-Ферма накопила: {', '.join(bits)}"

    coin_text = f" +{bonus['coins']}🪙" if bonus["coins"] else ""
    extra_text = vase_text + auto_evo_text + auto_rebirth_text + potion_text + chaos_text + chronos_text + coin_tree_text
    chronos_equipped = "chronos_orb" in set(_normalize_active_items(active_items))

    if bonus["is_god"]:
        flavor = CHRONOS_ORB_FLAVOR if chronos_equipped else GOD_ESSENCE_FLAVOR
        god_extra = f" +{bonus['rebirth']}🉑" if bonus["rebirth"] else ""
        await safe_reply(
            message,
            TEXTS["farm_2"].format(v0=flavor, v1=gained, v2=new_score, v3=coin_text, v4=god_extra, v5=auto_text, v6=extra_text)
        )
        return

    if chronos_equipped:
        await safe_reply(
            message,
            TEXTS["farm_2"].format(v0=CHRONOS_ORB_FLAVOR, v1=gained, v2=new_score, v3=coin_text, v4="", v5=auto_text, v6=extra_text)
        )
        return

    await message.reply(
        TEXTS["farm_3"].format(v0=gained, v1=new_score, v2=coin_text, v3=auto_text, v4=extra_text)
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
        await message.reply(TEXTS["daily_bonus_1"].format(v0=h, v1=m))
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
    await message.reply(TEXTS["daily_bonus_2"].format(v0=streak, v1=reward, v2=new_score, v3=item_text))

@dp.message(F.text.regexp(REVERSE_EXCHANGE_RE))
async def reverse_exchange(message: Message):
    """обменять <кол-во> коин -> списывает коины, начисляет очки ног (1 коин = 150 очков)."""
    match = REVERSE_EXCHANGE_RE.match(message.text.strip())
    coins_wanted = parse_amount(match.group(1))
    if not coins_wanted or coins_wanted <= 0:
        await message.reply(TEXTS["reverse_exchange_1"])
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, coins, evolution_level = row[2], row[5], row[3]
    rebirth_count = row[15]
    levelup_notify = row[11]

    if coins_wanted > coins:
        await message.reply(TEXTS["reverse_exchange_2"].format(v0=coins))
        return

    gained = coins_wanted * REVERSE_EXCHANGE_RATE
    new_coins = coins - coins_wanted
    new_score = score + gained

    await db_exec("UPDATE users SET score = ?, coins = ? WHERE user_id = ?", (new_score, new_coins, user_id))

    await maybe_announce_levelup(message, username, score, new_score, evolution_level, bool(levelup_notify), rebirth_count)
    await message.reply(TEXTS["reverse_exchange_3"].format(v0=coins_wanted, v1=gained, v2=new_score))

@dp.message(F.text.regexp(CRAFT_EXCHANGE_RE))
async def craft_exchange(message: Message):
    """обменять <кол-во> крафт/очкк -> списывает очки перерождения, начисляет очки крафта
    (курс: CRAFT_POINTS_EXCHANGE_RATE 🉑 = 1 💠). <кол-во> здесь — это 🉑, которые отдаёшь."""
    match = CRAFT_EXCHANGE_RE.match(message.text.strip())
    rebirth_wanted = parse_amount(match.group(1))
    if not rebirth_wanted or rebirth_wanted <= 0:
        await message.reply("Количество очков перерождения должно быть больше нуля.")
        return
    if rebirth_wanted % CRAFT_POINTS_EXCHANGE_RATE != 0:
        await message.reply(
            f"Обменивать можно только кратно {CRAFT_POINTS_EXCHANGE_RATE} 🉑 "
            f"(например: обменять {CRAFT_POINTS_EXCHANGE_RATE} крафт).\n"
            f"Хочешь сразу задать нужное число очков крафта — пиши «обменять очкк <число>» "
            f"(например: обменять очкк 3 → спишет {3 * CRAFT_POINTS_EXCHANGE_RATE} 🉑)."
        )
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    rebirth_points = row[14]
    craft_points = row[32]

    if rebirth_wanted > rebirth_points:
        await message.reply(
            f"Недостаточно очков перерождения. У тебя {rebirth_points} 🉑, "
            f"нужно {rebirth_wanted} 🉑 (= {rebirth_wanted // CRAFT_POINTS_EXCHANGE_RATE} 💠)."
        )
        return

    gained = rebirth_wanted // CRAFT_POINTS_EXCHANGE_RATE
    new_rebirth_points = rebirth_points - rebirth_wanted
    new_craft_points = craft_points + gained

    await db_exec(
        "UPDATE users SET rebirth_points = ?, craft_points = ? WHERE user_id = ?",
        (new_rebirth_points, new_craft_points, user_id),
    )

    await message.reply(
        f"Обменял {rebirth_wanted} 🉑 → +{gained} 💠 очков крафта (Всего: {new_craft_points})"
    )

@dp.message(F.text.regexp(CRAFT_EXCHANGE_TO_RE))
async def craft_exchange_to(message: Message):
    """обменять крафт/очкк <кол-во> -> удобный обратный формат: <кол-во> это то, сколько
    очков крафта 💠 хочешь ПОЛУЧИТЬ. Бот сам считает нужные 🉑 (по курсу) и списывает их."""
    match = CRAFT_EXCHANGE_TO_RE.match(message.text.strip())
    craft_wanted = parse_amount(match.group(1))
    if not craft_wanted or craft_wanted <= 0:
        await message.reply("Количество очков крафта должно быть больше нуля.")
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    rebirth_points = row[14]
    craft_points = row[32]

    rebirth_cost = craft_wanted * CRAFT_POINTS_EXCHANGE_RATE

    if rebirth_cost > rebirth_points:
        max_affordable = rebirth_points // CRAFT_POINTS_EXCHANGE_RATE
        await message.reply(
            f"Недостаточно очков перерождения. У тебя {rebirth_points} 🉑, "
            f"нужно {rebirth_cost} 🉑 на {craft_wanted} 💠.\n"
            f"Сейчас можешь обменять максимум {max_affordable} 💠 "
            f"(обменять очкк {max_affordable})." if max_affordable > 0 else
            f"Недостаточно очков перерождения. У тебя {rebirth_points} 🉑, "
            f"нужно {rebirth_cost} 🉑 на {craft_wanted} 💠."
        )
        return

    new_rebirth_points = rebirth_points - rebirth_cost
    new_craft_points = craft_points + craft_wanted

    await db_exec(
        "UPDATE users SET rebirth_points = ?, craft_points = ? WHERE user_id = ?",
        (new_rebirth_points, new_craft_points, user_id),
    )

    await message.reply(
        f"Обменял {rebirth_cost} 🉑 → +{craft_wanted} 💠 очков крафта (Всего: {new_craft_points})"
    )

@dp.message(F.text.lower().startswith("обменять "))
async def exchange(message: Message):
    match = EXCHANGE_RE.match(message.text.strip().lower())
    if not match:
        await message.reply(TEXTS["exchange_1"].format(v0=EXCHANGE_RATE))
        return

    coins_wanted = parse_amount(match.group(1))
    if not coins_wanted or coins_wanted <= 0:
        await message.reply(TEXTS["exchange_2"])
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, coins, evolution_level = row[2], row[5], row[3]
    rebirth_count = row[15]
    ultra_rebirth = bool(row[21])

    spent = coins_wanted * EXCHANGE_RATE
    if spent > score:
        max_coins = score // EXCHANGE_RATE
        await message.reply(TEXTS["exchange_3"].format(v0=score, v1=max_coins))
        return

    old_level = get_level_index(score, evolution_level, rebirth_count, ultra_rebirth)
    new_score = score - spent
    new_level = get_level_index(new_score, evolution_level, rebirth_count, ultra_rebirth)
    new_coins = coins + coins_wanted

    await db_exec("UPDATE users SET score = ?, coins = ? WHERE user_id = ?", (new_score, new_coins, user_id))

    warn = f"\n⚠️ Уровень упал с {old_level} до {new_level}!" if new_level < old_level else ""
    await message.reply(TEXTS["exchange_4"].format(v0=spent, v1=coins_wanted, v2=new_coins, v3=warn))

async def transfer_currency(message: Message, currency: str, amount: int):
    """currency: 'ног' или 'коин'. Общая логика для дать/передать <число> <валюта>."""
    if not message.reply_to_message:
        await message.reply(TEXTS["transfer_currency_1"])
        return

    receiver = message.reply_to_message.from_user
    sender = message.from_user
    if receiver.id == sender.id:
        await message.reply(TEXTS["transfer_currency_2"])
        return

    sender_username = sender.username or sender.first_name or "Без имени"
    receiver_username = receiver.username or receiver.first_name or "Без имени"

    sender_row = await ensure_user(sender.id, sender_username)
    if sender_row[3] < 1:
        await message.reply(TEXTS["transfer_currency_3"])
        return

    if currency == "ног":
        if sender_row[2] < amount:
            await message.reply(TEXTS["transfer_currency_4"].format(v0=sender_row[2]))
            return
        receiver_row = await ensure_user(receiver.id, receiver_username)
        new_sender = sender_row[2] - amount
        new_receiver = receiver_row[2] + amount
        await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_sender, sender.id))
        await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_receiver, receiver.id))
        await message.reply(TEXTS["transfer_currency_5"].format(v0=esc(sender_username), v1=amount, v2=esc(receiver_username)))
        await maybe_announce_levelup(message, receiver_username, receiver_row[2], new_receiver,
                                      receiver_row[3], bool(receiver_row[11]), receiver_row[15])
    else:
        if sender_row[5] < amount:
            await message.reply(TEXTS["transfer_currency_6"].format(v0=sender_row[5]))
            return
        await ensure_user(receiver.id, receiver_username)
        await db_exec("UPDATE users SET coins = coins - ? WHERE user_id = ?", (amount, sender.id))
        await db_exec("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, receiver.id))
        await message.reply(TEXTS["transfer_currency_7"].format(v0=esc(sender_username), v1=amount, v2=esc(receiver_username)))

async def transfer_item_direct(message: Message, item_query: str):
    """Прямой поиск предмета по вхождению строки, без разделения на бустеры/пассивки (п.2 ТЗ)."""
    if not message.reply_to_message:
        await message.reply(TEXTS["transfer_item_direct_1"])
        return

    item_key = find_item_by_name(item_query)
    if not item_key:
        await message.reply(TEXTS["transfer_item_direct_2"].format(v0=esc(item_query)))
        return

    if item_key in NON_TRADABLE_ITEMS:
        emoji, name, _, _ = ITEMS[item_key]
        await message.reply(TEXTS["transfer_item_direct_3"].format(v0=emoji, v1=esc(name)))
        return

    sender_id = message.from_user.id
    sender_username = message.from_user.username or message.from_user.first_name or "Без имени"
    receiver = message.reply_to_message.from_user
    receiver_username = receiver.username or receiver.first_name or "Без имени"

    if receiver.id == sender_id:
        await message.reply(TEXTS["transfer_item_direct_4"])
        return

    emoji, name, _, _ = ITEMS[item_key]

    await ensure_user(sender_id, sender_username)
    await ensure_user(receiver.id, receiver_username)

    removed = await remove_item(sender_id, item_key, 1)
    if not removed:
        await message.reply(TEXTS["transfer_item_direct_5"].format(v0=esc(name)))
        return

    sender_row = await get_user(sender_id)
    remaining = await get_inventory(sender_id)
    has_more = any(k == item_key and q > 0 for k, q in remaining)
    if not has_more:
        new_equipped = unequip_item(sender_row[18], item_key)
        await db_exec("UPDATE users SET equipped_items = ? WHERE user_id = ?", (format_equipped(new_equipped), sender_id))

    await add_item(receiver.id, item_key)

    await safe_reply(message, TEXTS["transfer_item_direct_6"].format(v0=emoji, v1=esc(name), v2=esc(receiver_username)))

_TRANSFER_CURRENCY_TOKENS = {"ног": "ног", "коин": "коин"}

@dp.message(F.text.regexp(r"(?i)^(дать|передать)\s+(.+)$"))
async def give_or_transfer(message: Message):
    """Умный хендлер: 'дать 888 коин' -> валюта, 'дать свеча' / 'передать свеча' -> предмет.
    Синтаксис определяется автоматически по структуре аргументов."""
    text = message.text.strip()
    verb, _, args = text.partition(" ")
    args = args.strip()
    if not args:
        await message.reply(TEXTS["give_or_transfer_1"])
        return

    parts = args.split(" ", 1)
    first_word = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""

    if _AMOUNT_TOKEN_RE.match(first_word) and rest:
        currency_word = rest.split(" ", 1)[0].lower()
        if currency_word in _TRANSFER_CURRENCY_TOKENS:
            amount = parse_amount(first_word)
            if not amount or amount <= 0:
                await message.reply(TEXTS["give_or_transfer_2"])
                return
            await transfer_currency(message, _TRANSFER_CURRENCY_TOKENS[currency_word], amount)
            return
        else:
            await message.reply(TEXTS["give_or_transfer_3"].format(v0=esc(currency_word)))
            return

    if first_word.lower() in _TRANSFER_CURRENCY_TOKENS and rest and _AMOUNT_TOKEN_RE.match(rest.split(" ", 1)[0]):
        amount_word = rest.split(" ", 1)[0]
        amount = parse_amount(amount_word)
        if not amount or amount <= 0:
            await message.reply(TEXTS["give_or_transfer_4"])
            return
        await transfer_currency(message, _TRANSFER_CURRENCY_TOKENS[first_word.lower()], amount)
        return

    await transfer_item_direct(message, args)

async def sell_item(message: Message, prefix: str, only_passive: bool):
    raw = message.text[len(prefix):].strip()
    sell_all = False
    if raw.lower().endswith(" все"):
        sell_all = True
        raw = raw[:-len(" все")].strip()
    item_query = raw
    item_key = find_item_by_name(item_query, only_passive=only_passive)
    if not item_key:
        wrong_cmd = "продать п" if only_passive is False else "продать б"
        await message.reply(TEXTS["sell_item_1"].format(v0='предметов' if only_passive else 'бустеров', v1=wrong_cmd))
        return

    if item_key in NON_TRADABLE_ITEMS:
        emoji, name, _, _ = ITEMS[item_key]
        await message.reply(TEXTS["sell_item_2"].format(v0=emoji, v1=esc(name)))
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    emoji, name, _, _ = ITEMS[item_key]

    if sell_all:
        owned_row = await db_query_one("SELECT qty FROM inventory WHERE user_id = ? AND item_key = ?", (user_id, item_key))
        qty = owned_row[0] if owned_row else 0
        if qty <= 0:
            await message.reply(TEXTS["sell_item_3"].format(v0=esc(name)))
            return
    else:
        qty = 1

    removed = await remove_item(user_id, item_key, qty)
    if not removed:
        await message.reply(TEXTS["sell_item_3"].format(v0=esc(name)))
        return

    row = await get_user(user_id)
    remaining = await get_inventory(user_id)
    has_more = any(k == item_key and q > 0 for k, q in remaining)
    if not has_more:
        new_equipped = unequip_item(row[18], item_key)
        await db_exec("UPDATE users SET equipped_items = ? WHERE user_id = ?", (format_equipped(new_equipped), user_id))

    upgrades = parse_upgrades(row[16])
    sell_lvl = upgrade_level(upgrades, "sell_boost")
    unit_price = SELL_PRICE.get(item_key, 1) + sell_bonus_coins(upgrades)
    price = unit_price * qty

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
    if sell_all and qty > 1:
        await safe_reply(message, TEXTS["sell_item_4_all"].format(v0=emoji, v1=esc(name), v2=qty, v3=price, v4=bonus_text))
    else:
        await safe_reply(message, TEXTS["sell_item_4"].format(v0=emoji, v1=esc(name), v2=price, v3=bonus_text))

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
        return
    await message.reply(
        TEXTS["sell_wrong_format_1"]
    )

async def destroy_item(message: Message, prefix: str, only_passive: bool):
    item_query = message.text[len(prefix):].strip()
    item_key = find_item_by_name(item_query, only_passive=only_passive)
    if not item_key:
        wrong_cmd = "уничтожение п" if only_passive is False else "уничтожение б"
        await message.reply(TEXTS["destroy_item_1"].format(v0='предметов' if only_passive else 'бустеров', v1=wrong_cmd))
        return

    if item_key in NON_TRADABLE_ITEMS:
        emoji, name, _, _ = ITEMS[item_key]
        await message.reply(TEXTS["destroy_item_2"].format(v0=emoji, v1=esc(name)))
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    removed = await remove_item(user_id, item_key, 1)
    emoji, name, _, _ = ITEMS[item_key]
    if not removed:
        await message.reply(TEXTS["destroy_item_3"].format(v0=esc(name)))
        return

    row = await get_user(user_id)
    remaining = await get_inventory(user_id)
    has_more = any(k == item_key and q > 0 for k, q in remaining)
    if not has_more:
        new_equipped = unequip_item(row[18], item_key)
        await db_exec("UPDATE users SET equipped_items = ? WHERE user_id = ?", (format_equipped(new_equipped), user_id))

    await safe_reply(message, TEXTS["destroy_item_4"].format(v0=emoji, v1=esc(name)))

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
        TEXTS["destroy_wrong_format_1"]
    )

