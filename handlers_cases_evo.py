"""
handlers_cases_evo.py — кейсы, эволюция, апгрейды, престиж, перерождение
и ультра-перерождение: осмотр/покупка/открытие кейсов, применение
сохраняющих монет (evolution/rebirth/awakening coin), меню апгрейдов и
престижа, расчёт и выполнение перерождений.
"""
from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
import random
import re

from premium_emoji import (
    PREMIUM_AWAKENING_COIN, PREMIUM_CRAFT_POINT, PREMIUM_EVOLUTION_COIN,
    PREMIUM_REBIRTH_COIN,
)
from config import (
    EVO_FARM_BONUS_LVL10, EVO_FLOW_EXTRA_CHANCE, EVO_FLOW_UNLOCK_LEVEL,
    EVO_HARDNESS_RATE, EVO_LEG_TIERS, EVO_LEG_UNLOCK_BY_LEVEL, EVO_UNLOCK_MEK2_LEVEL,
    EVO_UNLOCK_NECKLACE_CRAFTS_LEVEL, EVO_UNLOCK_REBIRTH_SPARK_LEVEL,
    FARM_EVOLVED, MEK_LIMIT, MEK_POINT, TEXTS,
    ULTRA_LEG_EMOJI, ULTRA_LEG_LEVEL, ULTRA_LEG_NAME, ULTRA_REBIRTH_BOOST,
    ULTRA_REQUIRED_EVO, ULTRA_REQUIRED_LEG_LEVEL, ULTRA_REQUIRED_REBIRTHS,
)
from game_data import (
    AWAKENING_COIN_BADGE_CHANCE, AWAKENING_COIN_PRESTIGE_AMOUNT,
    AWAKENING_COIN_PRESTIGE_CHANCE, AWAKENING_COIN_SAVE_PCT, CASES,
    EVOLUTION_COIN_SAVE_PCT, ICE_SHARD_SAVE_CHANCE, ITEMS, PRESTIGE_ORDER,
    PRESTIGE_PAGE_SIZE, PRESTIGE_PER_REBIRTH, PRESTIGE_PER_ULTRA_REBIRTH,
    PRESTIGE_UPGRADES, REBIRTH_COIN_SAVE_PCT, REBIRTH_EVO_STEP,
    REBIRTH_HARDNESS_STEP, REBIRTH_MIN_EVO, REBIRTH_POINTS_PER_STEP,
    UPGRADES, UPGRADE_CATEGORIES, UPGRADE_ORDER,
    parse_auto_sell_items,
)
from command_patterns import CASE_NUM_RE
from text_utils import esc, plain_emoji, safe_edit_text
from state import dp
from economy import (
    PROMO_BADGES, _invalidate_event_state_cache, _normalize_active_items,
    add_item, add_promo_badge, apply_case_reward, case_price_with_discount,
    db_exec, ensure_user,
    format_prestige_upgrades, format_upgrades, get_inventory, get_level_index,
    get_user, is_event_active, level_threshold, log_admin_action,
    parse_equipped, parse_prestige_upgrades, parse_upgrades, prestige_bonus,
    prestige_level, prestige_next_cost, upgrade_level, upgrade_next_cost,
    upgrade_next_extra_cost,
)
from game_logic import case_drop_table, roll_case_item
from subscription import is_admin, require_subscription

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
        lines.append(f"{emoji} {esc(name)}{boost_part} — {chance}%")
    return "\n".join(lines)

async def send_case_inspect(message: Message, case_num: int):
    """Меню осмотра кейса: список дропа с процентами + кнопка открытия."""
    case = CASES.get(case_num)
    if not case:
        await message.reply(TEXTS["send_case_inspect_1"])
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
        await message.reply(TEXTS["open_case_instant_1"])
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    coins = row[5]
    upgrades = parse_upgrades(row[16])
    auto_sell_enabled = bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])
    price = case_price_with_discount(case["price"], upgrades)

    if coins < price:
        await message.reply(TEXTS["open_case_instant_2"].format(v0=price, v1=coins))
        return

    item_key = roll_case_item(case_num)
    emoji, name, percent, _ = ITEMS[item_key]

    await db_exec(
        "UPDATE users SET coins = coins - ?, cases_opened = cases_opened + 1 WHERE user_id = ?",
        (price, user_id),
    )
    _sold_for, sold_text = await apply_case_reward(user_id, item_key, upgrades, auto_sell_enabled, auto_sell_items)
    new_coins = coins - price + _sold_for

    await message.reply(TEXTS["open_case_instant_3"].format(v0=emoji, v1=esc(name), v2=percent, v3=new_coins) + sold_text)

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
    await message.reply(TEXTS["case_list_1"], reply_markup=kb)

@dp.callback_query(F.data.startswith("inspect_case:"))
async def inspect_case_callback(callback: CallbackQuery):
    _, case_num_str, owner_str = callback.data.split(":")
    case_num = int(case_num_str)
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inspect_case_callback_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    case = CASES[case_num]
    price = case_price_with_discount(case["price"], upgrades)

    await safe_edit_text(callback, 
        format_case_inspect_text(case_num, price, case["price"]),
        reply_markup=case_offer_keyboard(case_num, owner_id, price),
    )

@dp.callback_query(F.data.startswith("buy_case:"))
async def buy_case(callback: CallbackQuery):
    _, case_num_str, owner_str = callback.data.split(":")
    case_num = int(case_num_str)
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["buy_case_1"], show_alert=True)
        return

    case = CASES[case_num]

    row = await get_user(owner_id)
    coins = row[5]
    upgrades = parse_upgrades(row[16])
    auto_sell_enabled = bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])
    price = case_price_with_discount(case["price"], upgrades)

    if coins < price:
        await callback.answer(TEXTS["buy_case_2"].format(v0=price), show_alert=True)
        return

    item_key = roll_case_item(case_num)
    emoji, name, percent, _ = ITEMS[item_key]

    await db_exec(
        "UPDATE users SET coins = coins - ?, cases_opened = cases_opened + 1 WHERE user_id = ?",
        (price, owner_id),
    )
    sold_for, sold_text = await apply_case_reward(owner_id, item_key, upgrades, auto_sell_enabled, auto_sell_items)
    new_coins = coins - price + sold_for

    await safe_edit_text(callback, 
        f"🎉 Выпало: {emoji} {esc(name)} (+{percent}%)!{sold_text}\nОстаток монет: {new_coins} 🪙",
        reply_markup=case_offer_keyboard(case_num, owner_id, price),
    )
    await callback.answer(TEXTS["buy_case_3"])

async def apply_coin_tree_save(user_id: int, inventory_map: dict, event: str, score: int, evolution_level: int) -> dict:
    """Гарантированный сейв % очков/эво при эволюции или перерождении от 🟢/🟣/⚪️ монет дерева.
    event: "evolution" или "rebirth". Работает пассивно (монеты лежат в инвентаре, экипировать
    не нужно). Если у игрока есть несколько подходящих монет — действует только САМАЯ СИЛЬНАЯ:
    ⚪️ Монета Пробуждения (работает и на эво, и на перерождение) > специфичная монета события
    (🟢 только эво, 🟣 только перерождение). При срабатывании 1% шанс +3 очка престижа и
    0.01% шанс на бейдж "Инвестировал в #####" — только у ⚪️ Монеты Пробуждения.
    Возвращает {"kept_score": int, "kept_evolution": int, "extra_text": str}."""
    kept_score = 0
    kept_evolution = 0
    extra_text = ""
    pct = 0.0
    coin_label = ""

    if inventory_map.get("awakening_coin", 0) > 0:
        pct = AWAKENING_COIN_SAVE_PCT
        coin_label = f"{PREMIUM_AWAKENING_COIN} Монета Пробуждения"
    elif event == "evolution" and inventory_map.get("evolution_coin", 0) > 0:
        pct = EVOLUTION_COIN_SAVE_PCT
        coin_label = f"{PREMIUM_EVOLUTION_COIN} Монета Эволюции"
    elif event == "rebirth" and inventory_map.get("rebirth_coin", 0) > 0:
        pct = REBIRTH_COIN_SAVE_PCT
        coin_label = f"{PREMIUM_REBIRTH_COIN} Монета Перерождения"

    if pct > 0:
        kept_score = round(score * pct)
        if event == "rebirth" or inventory_map.get("awakening_coin", 0) > 0:
            kept_evolution = round(evolution_level * pct)
        extra_text += f"\n{coin_label}: сохранено {round(pct * 100)}% ({kept_score} очков ноги{f' и {kept_evolution} ур. эво' if kept_evolution else ''})!"

        if inventory_map.get("awakening_coin", 0) > 0:
            if random.random() < AWAKENING_COIN_PRESTIGE_CHANCE:
                await db_exec(
                    "UPDATE users SET prestige_points = prestige_points + ? WHERE user_id = ?",
                    (AWAKENING_COIN_PRESTIGE_AMOUNT, user_id),
                )
                extra_text += f"\n{PREMIUM_AWAKENING_COIN} Монета Пробуждения: +{AWAKENING_COIN_PRESTIGE_AMOUNT}🔮 очка престижа!"
            if random.random() < AWAKENING_COIN_BADGE_CHANCE:
                await add_promo_badge(user_id, "investor")
                badge_emoji, badge_name = PROMO_BADGES["investor"]
                extra_text += f"\n{PREMIUM_AWAKENING_COIN} Монета Пробуждения: выпал бейдж {badge_emoji} «{badge_name}»!"

    return {"kept_score": kept_score, "kept_evolution": kept_evolution, "extra_text": extra_text}

async def evo_level_unlock_text(user_id: int, evolution_level: int) -> str:
    """Общая точка разблокировок за уровень эволюции — вызывается и из авто-эво (каскадно,
    на каждом промежуточном уровне), и из ручной «эволюция» (один уровень за раз), чтобы
    список разблокировок не расходился между ними."""
    if evolution_level == 1:
        return f"\nОткрыта фарма {FARM_EVOLVED[0]}-{FARM_EVOLVED[1]} очков и эмодзи 🦿 ({MEK_POINT} очков, до {MEK_LIMIT} раз в соо)!"
    if evolution_level == 2:
        await add_item(user_id, "star")
        return "\nПолучена ⭐️ Звезда перерождения — экипируй в инвентарь!"

    text = ""
    if evolution_level == EVO_UNLOCK_REBIRTH_SPARK_LEVEL:
        await add_item(user_id, "rebirth_spark")
        text += f"\nПолучена {ITEMS['rebirth_spark'][0]} Искра перерождения — сырьё для новых крафтов!"
    if evolution_level in EVO_LEG_UNLOCK_BY_LEVEL:
        emoji = EVO_LEG_UNLOCK_BY_LEVEL[evolution_level]
        tier = EVO_LEG_TIERS[emoji]
        text += f"\nОткрыты новые ноги {emoji} (+{tier['bonus_pct']}% к добыче робоног, лимит {tier['limit']} за сообщение)!"
    if evolution_level == EVO_UNLOCK_MEK2_LEVEL:
        text += f"\nДобыча команды «ферма» увеличена на +{EVO_FARM_BONUS_LVL10} очков!"
    if evolution_level == EVO_UNLOCK_NECKLACE_CRAFTS_LEVEL:
        text += "\nОткрыты новые крафты: Ожерелье из звёзд, Ожерелье пылающей звезды, Карманная звезда!"
    if evolution_level == EVO_FLOW_UNLOCK_LEVEL:
        text += f"\nОткрыт пассивный буст «Поток эволюции» — {round(EVO_FLOW_EXTRA_CHANCE * 100)}% шанс на доп. эволюцию сверху при каждой эволюции!"
    return text

async def try_auto_evolve(user_id: int, score: int, evolution_level: int, rebirth_count: int, active_items=None) -> tuple[int, int, str]:
    """VIP авто-эво: каскадно эволюционирует, пока очков хватает на след. эволюцию —
    например, если фарм разом принёс очков на 2 эволюции вперёд, сработают обе.
    Возвращает (итоговый evolution_level, итоговый score, текст для добавления к ответу)."""
    evolutions_done = 0
    unlock_text = ""
    score_before_last_reset = score
    while True:
        required = level_threshold(39, evolution_level, rebirth_count, active_items)
        if score < required:
            break
        score_before_last_reset = score
        score = 0
        evolution_level += 1
        evolutions_done += 1
        unlock_text += await evo_level_unlock_text(user_id, evolution_level)
        if evolution_level >= EVO_FLOW_UNLOCK_LEVEL and random.random() < EVO_FLOW_EXTRA_CHANCE:
            evolution_level += 1
            evolutions_done += 1
            unlock_text += "\n🌊 Поток эволюции: доп. эволюция сверху!"
            unlock_text += await evo_level_unlock_text(user_id, evolution_level)

    if evolutions_done == 0:
        return evolution_level, score, ""

    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}
    coin_save_text = ""
    if inventory_map.get("evolution_coin", 0) > 0 or inventory_map.get("awakening_coin", 0) > 0:
        evolution_level += 1
        coin_save_text += "\n🟢 Дерево монет: доп. эволюция сверху!"
    save_result = await apply_coin_tree_save(user_id, inventory_map, "evolution", score_before_last_reset, evolution_level)
    score = save_result["kept_score"]
    coin_save_text += save_result["extra_text"]

    await db_exec("UPDATE users SET score = ?, evolution_level = ? WHERE user_id = ?", (score, evolution_level, user_id))
    times = f" ×{evolutions_done}" if evolutions_done > 1 else ""
    text = f"\n\n⚙️💎 Авто-эволюция{times}! Теперь {evolution_level} уровень эволюции.{unlock_text}{coin_save_text}"
    return evolution_level, score, text

@dp.message(F.text.lower() == "эволюция")
async def evolve(message: Message):
    if not await require_subscription(message):
        return
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level = row[2], row[3]
    rebirth_count = row[15]
    active_items = parse_equipped(row[18])

    required = level_threshold(39, evolution_level, rebirth_count, active_items)
    if score < required:
        await message.reply(TEXTS["evolve_1"].format(v0=required))
        return

    new_evolution = evolution_level + 1

    ice_text = ""
    kept_score = 0
    if "ice_shard" in set(_normalize_active_items(active_items)) and random.random() < ICE_SHARD_SAVE_CHANCE:
        kept_score = score
        ice_text = "\n🧊 Ледяной осколок: очки ноги сохранены!"

    coin_save_text = ""
    if not kept_score:
        inv_rows = await get_inventory(user_id)
        inventory_map = {k: q for k, q in inv_rows}
        save_result = await apply_coin_tree_save(user_id, inventory_map, "evolution", score, evolution_level)
        kept_score = save_result["kept_score"]
        coin_save_text = save_result["extra_text"]
        if inventory_map.get("evolution_coin", 0) > 0 or inventory_map.get("awakening_coin", 0) > 0:
            new_evolution += 1
            coin_save_text += "\n🟢 Дерево монет: доп. эволюция сверху!"

    await db_exec("UPDATE users SET score = ?, evolution_level = ? WHERE user_id = ?", (kept_score, new_evolution, user_id))

    unlock_text = await evo_level_unlock_text(user_id, new_evolution)

    await message.reply(
        TEXTS["evolve_2"].format(v0=new_evolution, v1=round(EVO_HARDNESS_RATE * new_evolution * 100), v2=unlock_text + ice_text + coin_save_text)
    )

@dp.message(F.text.lower() == "!ивент ноги")
async def toggle_event(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)

    active = await is_event_active()
    new_value = "0" if active else "1"
    await db_exec(
        "INSERT INTO settings (key, value) VALUES ('event_active', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (new_value,),
    )
    if new_value == "1":
        for key, value in (("event_multiplier", "2"), ("event_until", "0")):
            await db_exec(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
    _invalidate_event_state_cache()

    if new_value == "1":
        await message.reply(TEXTS["toggle_event_1"])
    else:
        await message.reply(TEXTS["toggle_event_2"])

def format_upgrade_page_text(upgrades: dict, rebirth_points: int, category: int, craft_points: int = 0) -> str:
    craft_line = f"💠 Очки крафта: <code>{craft_points}</code>\n" if category == 3 else ""
    header = (
        f"⚙️ <b>МЕНЮ ПРОКАЧКИ</b> — {UPGRADE_CATEGORIES[category]}\n"
        f"🉑 Очки перерождения: <code>{rebirth_points}</code>\n"
        f"{craft_line}"
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
            extra = upgrade_next_extra_cost(key, upgrades)
            extra_part = f" + {extra[1]} {plain_emoji(PREMIUM_CRAFT_POINT)}" if extra else ""
            label = f"{cfg['name']} — {level}/{cfg['max_level']} ({cost} 🉑{extra_part})"
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
    craft_points = row[32]

    await message.reply(
        format_upgrade_page_text(upgrades, rebirth_points, 1, craft_points),
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
        await callback.answer(TEXTS["upgrade_change_page_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    rebirth_points = row[14]
    craft_points = row[32]
    await safe_edit_text(callback, 
        format_upgrade_page_text(upgrades, rebirth_points, category, craft_points),
        reply_markup=upgrade_page_keyboard(upgrades, owner_id, category),
    )

@dp.callback_query(F.data.startswith("upg_buy:"))
async def upgrade_buy(callback: CallbackQuery):
    _, owner_str, category_str, key = callback.data.split(":")
    owner_id = int(owner_str)
    category = int(category_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["upgrade_buy_1"], show_alert=True)
        return
    if key not in UPGRADES or UPGRADES[key].get("wip"):
        await callback.answer(TEXTS["upgrade_buy_2"], show_alert=True)
        return

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    rebirth_points = row[14]
    craft_points = row[32]
    cost = upgrade_next_cost(key, upgrades)

    if cost is None:
        await callback.answer(TEXTS["upgrade_buy_3"], show_alert=True)
        return
    if rebirth_points < cost:
        await callback.answer(TEXTS["upgrade_buy_4"].format(v0=cost, v1=rebirth_points), show_alert=True)
        return

    extra = upgrade_next_extra_cost(key, upgrades)
    extra_field, extra_amount = (extra if extra else (None, 0))
    if extra_field == "craft_points" and craft_points < extra_amount:
        await callback.answer(
            f"Нужно {extra_amount} 💠 очков крафта, у тебя {craft_points}.", show_alert=True
        )
        return

    upgrades[key] = upgrade_level(upgrades, key) + 1
    new_points = rebirth_points - cost
    new_craft_points = craft_points - extra_amount if extra_field == "craft_points" else craft_points
    await db_exec(
        "UPDATE users SET rebirth_points = ?, upgrades = ?, craft_points = ? WHERE user_id = ?",
        (new_points, format_upgrades(upgrades), new_craft_points, owner_id),
    )

    await safe_edit_text(callback, 
        format_upgrade_page_text(upgrades, new_points, category, new_craft_points),
        reply_markup=upgrade_page_keyboard(upgrades, owner_id, category),
    )
    await callback.answer(TEXTS["upgrade_buy_5"].format(v0=UPGRADES[key]['name'], v1=upgrades[key]))

def format_prestige_page_text(prestige_upgrades: dict, prestige_points: int, page: int) -> str:
    total_pages = (len(PRESTIGE_ORDER) - 1) // PRESTIGE_PAGE_SIZE + 1
    header = (
        f"🔮 <b>ДЕРЕВО ПРЕСТИЖА</b> — стр. {page + 1}/{total_pages}\n"
        f"🔮 Очки престижа: <code>{prestige_points}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Ветки бесконечны — чем выше уровень, тем реже растёт эффект, а цена растёт всегда.\n"
    )
    start = page * PRESTIGE_PAGE_SIZE
    lines = [header]
    for key in PRESTIGE_ORDER[start:start + PRESTIGE_PAGE_SIZE]:
        cfg = PRESTIGE_UPGRADES[key]
        level = prestige_level(prestige_upgrades, key)
        bonus = prestige_bonus(prestige_upgrades, key)
        cost = prestige_next_cost(key, prestige_upgrades)
        lines.append(
            f"{cfg['emoji']} <b>{cfg['name']}</b> — ур. {level} (эффект: {bonus})\n"
            f"   {cfg['desc']}\n"
            f"   Следующий уровень: {cost} 🔮"
        )
    return "\n".join(lines)

def prestige_page_keyboard(prestige_upgrades: dict, user_id: int, page: int) -> InlineKeyboardMarkup:
    total_pages = (len(PRESTIGE_ORDER) - 1) // PRESTIGE_PAGE_SIZE + 1
    start = page * PRESTIGE_PAGE_SIZE
    rows = []
    for key in PRESTIGE_ORDER[start:start + PRESTIGE_PAGE_SIZE]:
        cfg = PRESTIGE_UPGRADES[key]
        level = prestige_level(prestige_upgrades, key)
        cost = prestige_next_cost(key, prestige_upgrades)
        label = f"⬆️ {cfg['emoji']} {cfg['name']} ({cost} 🔮)"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"pr_buy:{user_id}:{page}:{key}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"pr_page:{user_id}:{page - 1}", style="primary"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="pr_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"pr_page:{user_id}:{page + 1}", style="primary"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.message(F.text.lower() == "престиж")
async def prestige_menu(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    prestige_upgrades = parse_prestige_upgrades(row[28])
    prestige_points = row[27]

    await message.reply(
        format_prestige_page_text(prestige_upgrades, prestige_points, 0),
        reply_markup=prestige_page_keyboard(prestige_upgrades, user_id, 0),
    )

@dp.callback_query(F.data == "pr_noop")
async def prestige_noop(callback: CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data.startswith("pr_page:"))
async def prestige_change_page(callback: CallbackQuery):
    _, owner_str, page_str = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["upgrade_change_page_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    prestige_upgrades = parse_prestige_upgrades(row[28])
    prestige_points = row[27]
    await safe_edit_text(callback, 
        format_prestige_page_text(prestige_upgrades, prestige_points, page),
        reply_markup=prestige_page_keyboard(prestige_upgrades, owner_id, page),
    )

@dp.callback_query(F.data.startswith("pr_buy:"))
async def prestige_buy(callback: CallbackQuery):
    _, owner_str, page_str, key = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["upgrade_buy_1"], show_alert=True)
        return
    if key not in PRESTIGE_UPGRADES:
        await callback.answer(TEXTS["upgrade_buy_2"], show_alert=True)
        return

    row = await get_user(owner_id)
    prestige_upgrades = parse_prestige_upgrades(row[28])
    prestige_points = row[27]
    cost = prestige_next_cost(key, prestige_upgrades)

    if prestige_points < cost:
        await callback.answer(TEXTS["prestige_buy_4"].format(v0=cost, v1=prestige_points), show_alert=True)
        return

    prestige_upgrades[key] = prestige_level(prestige_upgrades, key) + 1
    new_points = prestige_points - cost
    await db_exec(
        "UPDATE users SET prestige_points = ?, prestige_upgrades = ? WHERE user_id = ?",
        (new_points, format_prestige_upgrades(prestige_upgrades), owner_id),
    )

    await safe_edit_text(callback, 
        format_prestige_page_text(prestige_upgrades, new_points, page),
        reply_markup=prestige_page_keyboard(prestige_upgrades, owner_id, page),
    )
    await callback.answer(TEXTS["upgrade_buy_5"].format(v0=PRESTIGE_UPGRADES[key]['name'], v1=prestige_upgrades[key]))

async def compute_rebirth_result(user_id: int, score: int, evolution_level: int, rebirth_points: int, rebirth_count: int,
                                  prestige_points: int, prestige_upgrades: dict, active_items, inventory_map: dict) -> dict:
    """Считает результат перерождения (в т.ч. проки дерева монет, требующие БД) — общая логика
    для ручной команды «перерождение» и авто-перерождения (см. try_auto_rebirth)."""
    points_gained = (evolution_level // REBIRTH_EVO_STEP) * REBIRTH_POINTS_PER_STEP
    new_rebirth_points = rebirth_points + points_gained
    new_rebirth_count = rebirth_count + 1

    extra_text = ""
    echo_chance = 0.01 * prestige_bonus(prestige_upgrades, "p_echo")
    if echo_chance > 0 and random.random() < echo_chance:
        new_rebirth_points += 1
        extra_text += "\n🔮 Эхо сработало: +1 доп. Очко Перерождения!"

    new_prestige_points = prestige_points + PRESTIGE_PER_REBIRTH

    kept_evolution = 0
    kept_score = 0
    if "ice_shard" in set(_normalize_active_items(active_items)) and random.random() < ICE_SHARD_SAVE_CHANCE:
        kept_evolution = evolution_level
        extra_text += "\n🧊 Ледяной осколок: уровень эволюции сохранён!"
    else:
        save_result = await apply_coin_tree_save(user_id, inventory_map, "rebirth", score, evolution_level)
        kept_score = save_result["kept_score"]
        kept_evolution = save_result["kept_evolution"]
        extra_text += save_result["extra_text"]

    return {
        "points_gained": points_gained,
        "kept_evolution": kept_evolution,
        "kept_score": kept_score,
        "rebirth_points": new_rebirth_points,
        "rebirth_count": new_rebirth_count,
        "prestige_points": new_prestige_points,
        "extra_text": extra_text,
    }

async def try_auto_rebirth(user_id: int, score: int, evolution_level: int, rebirth_count: int,
                            rebirth_points: int, prestige_points: int, prestige_upgrades: dict,
                            active_items=None) -> tuple[int, int, int, int, int, str]:
    """VIP авто-перерождение: срабатывает само, как только эволюция достигает REBIRTH_MIN_EVO
    (см. auto_rebirth_on/off). Возвращает (score, evolution_level, rebirth_count, rebirth_points,
    prestige_points, текст для добавления к ответу)."""
    if evolution_level < REBIRTH_MIN_EVO:
        return score, evolution_level, rebirth_count, rebirth_points, prestige_points, ""

    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}
    result = await compute_rebirth_result(user_id, score, evolution_level, rebirth_points, rebirth_count, prestige_points, prestige_upgrades, active_items, inventory_map)
    await db_exec(
        "UPDATE users SET score = ?, evolution_level = ?, rebirth_points = ?, rebirth_count = ?, "
        "prestige_points = ? WHERE user_id = ?",
        (result["kept_score"], result["kept_evolution"], result["rebirth_points"], result["rebirth_count"], result["prestige_points"], user_id),
    )
    text = f"\n♻️ Авто-перерождение: +{result['points_gained']}🉑 (всего {result['rebirth_points']}🉑)" + result["extra_text"]
    return result["kept_score"], result["kept_evolution"], result["rebirth_count"], result["rebirth_points"], result["prestige_points"], text

@dp.message(F.text.lower() == "перерождение")
async def rebirth(message: Message):
    if not await require_subscription(message):
        return
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level = row[2], row[3]
    rebirth_points, rebirth_count = row[14], row[15]
    prestige_points = row[27]
    prestige_upgrades = parse_prestige_upgrades(row[28])
    active_items = parse_equipped(row[18])

    if evolution_level < REBIRTH_MIN_EVO:
        await message.reply(
            TEXTS["rebirth_1"].format(v0=REBIRTH_MIN_EVO, v1=evolution_level, v2=REBIRTH_MIN_EVO)
        )
        return

    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}
    result = await compute_rebirth_result(user_id, score, evolution_level, rebirth_points, rebirth_count, prestige_points, prestige_upgrades, active_items, inventory_map)

    await db_exec(
        "UPDATE users SET score = ?, evolution_level = ?, rebirth_points = ?, rebirth_count = ?, "
        "prestige_points = ? WHERE user_id = ?",
        (result["kept_score"], result["kept_evolution"], result["rebirth_points"], result["rebirth_count"], result["prestige_points"], user_id),
    )

    new_hardness = round(REBIRTH_HARDNESS_STEP * result["rebirth_count"] * 100)
    await message.reply(
        TEXTS["rebirth_2"].format(v0=result["points_gained"], v1=result["rebirth_points"], v2=new_hardness, v3=PRESTIGE_PER_REBIRTH) + result["extra_text"]
    )

def ultra_rebirth_eligible(evolution_level: int, leg_level: int, rebirth_count: int,
                            has_awakening_coin: bool, has_chronos_orb: bool) -> bool:
    """Все пять условий обязательны одновременно (см. константы ULTRA_REQUIRED_*):
    эволюция, уровень ноги, число перерождений, а также владение Монетой Пробуждения
    и Хвостом Джевила (просто лежат в инвентаре — экипировать не нужно, не расходуются)."""
    return (
        evolution_level >= ULTRA_REQUIRED_EVO
        and leg_level >= ULTRA_REQUIRED_LEG_LEVEL
        and rebirth_count >= ULTRA_REQUIRED_REBIRTHS
        and has_awakening_coin
        and has_chronos_orb
    )

def ultra_rebirth_confirm_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌌 Подтвердить", callback_data=f"ultra_ok:{user_id}", style="success"),
        InlineKeyboardButton(text="Отмена", callback_data=f"ultra_no:{user_id}", style="danger"),
    ]])

@dp.message(F.text.lower() == "ультра перерождение")
async def ultra_rebirth_info(message: Message):
    """Показывает статус условий и, если всё готово, просит подтверждение кнопкой —
    Ультра перерождение необратимо и выполняется только один раз за игру."""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level = row[2], row[3]
    rebirth_count = row[15]
    ultra_rebirth = bool(row[21])

    if ultra_rebirth:
        await message.reply(TEXTS["ultra_rebirth_already_1"])
        return

    leg_level = get_level_index(score, evolution_level, rebirth_count)

    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}
    has_awakening_coin = inventory_map.get("awakening_coin", 0) > 0
    has_chronos_orb = inventory_map.get("chronos_orb", 0) > 0

    if not ultra_rebirth_eligible(evolution_level, leg_level, rebirth_count, has_awakening_coin, has_chronos_orb):
        await message.reply(
            TEXTS["ultra_rebirth_locked_1"].format(
                v0=evolution_level, v1=ULTRA_REQUIRED_EVO,
                v2=leg_level, v3=ULTRA_REQUIRED_LEG_LEVEL,
                v4=rebirth_count, v5=ULTRA_REQUIRED_REBIRTHS,
                v6="✅" if has_awakening_coin else "❌",
                v7="✅" if has_chronos_orb else "❌",
            )
        )
        return

    await message.reply(
        TEXTS["ultra_rebirth_confirm_1"].format(
            v0=ULTRA_LEG_EMOJI, v1=esc(ULTRA_LEG_NAME), v2=ULTRA_LEG_LEVEL,
            v3=round(ULTRA_REBIRTH_BOOST * 100),
        ),
        reply_markup=ultra_rebirth_confirm_keyboard(user_id),
    )

@dp.callback_query(F.data.startswith("ultra_no:"))
async def ultra_rebirth_cancel(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["ultra_rebirth_not_owner_1"], show_alert=True)
        return
    await callback.answer()
    await safe_edit_text(callback, TEXTS["ultra_rebirth_cancelled_1"])

@dp.callback_query(F.data.startswith("ultra_ok:"))
async def ultra_rebirth_confirm(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["ultra_rebirth_not_owner_1"], show_alert=True)
        return

    user_id = callback.from_user.id
    username = callback.from_user.username or callback.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level = row[2], row[3]
    rebirth_count = row[15]
    ultra_rebirth = bool(row[21])

    if ultra_rebirth:
        await safe_edit_text(callback, TEXTS["ultra_rebirth_already_1"])
        await callback.answer()
        return

    leg_level = get_level_index(score, evolution_level, rebirth_count)

    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}
    has_awakening_coin = inventory_map.get("awakening_coin", 0) > 0
    has_chronos_orb = inventory_map.get("chronos_orb", 0) > 0

    if not ultra_rebirth_eligible(evolution_level, leg_level, rebirth_count, has_awakening_coin, has_chronos_orb):
        await safe_edit_text(
            callback,
            TEXTS["ultra_rebirth_locked_1"].format(
                v0=evolution_level, v1=ULTRA_REQUIRED_EVO,
                v2=leg_level, v3=ULTRA_REQUIRED_LEG_LEVEL,
                v4=rebirth_count, v5=ULTRA_REQUIRED_REBIRTHS,
                v6="✅" if has_awakening_coin else "❌",
                v7="✅" if has_chronos_orb else "❌",
            ),
        )
        await callback.answer()
        return

    prestige_points = row[27]
    new_prestige_points = prestige_points + PRESTIGE_PER_ULTRA_REBIRTH
    await db_exec(
        "UPDATE users SET score = 0, evolution_level = 0, rebirth_points = 0, rebirth_count = 0, "
        "ultra_rebirth = 1, prestige_points = ? WHERE user_id = ?",
        (new_prestige_points, user_id),
    )

    await safe_edit_text(
        callback,
        TEXTS["ultra_rebirth_success_1"].format(
            v0=ULTRA_LEG_EMOJI, v1=esc(ULTRA_LEG_NAME), v2=ULTRA_LEG_LEVEL,
            v3=round(ULTRA_REBIRTH_BOOST * 100), v4=PRESTIGE_PER_ULTRA_REBIRTH,
        ),
    )
    await callback.answer()

