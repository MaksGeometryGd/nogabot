"""
handlers_inventory.py — инвентарь, зелья и крафт: просмотр инвентаря по
категориям (предметы/бустеры/зелья), варка и использование зелий,
экипировка предметов, список и выполнение рецептов крафта.
"""
from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
import re
import time
from urllib.parse import quote, unquote

from config import CRAFT_MAX_LEVEL, TEXTS
from game_data import (
    ALL_PLAYER_AMULETS, AUTOSELL_PAGE_SIZE, CASE_SELLABLE_ITEMS, ITEMS,
    PASSIVE_ITEMS, POTIONS, POTION_ORDER, RECIPES,
    format_recipe_requirements, recipe_missing_ingredients,
)
from text_utils import esc, plain_emoji, safe_edit_text, safe_reply
from state import dp
from economy import (
    _normalize_active_items, active_potions_now, add_item, brew_seconds_for,
    coin_tree_slot_bonus, craft_coin_cost_with_discount, db_exec, ensure_user,
    equip_item, equipped_slots_max, format_equipped, format_potion_stock,
    format_potions, get_inventory, get_user, parse_equipped, parse_potion_stock,
    parse_prestige_upgrades, parse_upgrades, potion_duration_seconds,
    remove_item, upgrade_level,
)
from game_logic import _percent_label

def _format_equipped_item_line(item_key: str) -> str:
    emoji, name, boost_percent, _ = ITEMS[item_key]
    if item_key == "chronos_orb":
        return f"{emoji} {esc(name)} (+10-400%, рандом)"
    return f"{emoji} {esc(name)} (+{boost_percent}%)"

def format_inventory_menu_text(active_items, upgrades: dict = None, prestige_upgrades: dict = None, bonus_slots: int = 0):
    items = _normalize_active_items(active_items)
    max_slots = equipped_slots_max(upgrades or {}, prestige_upgrades or {}, bonus_slots)
    equipped = [_format_equipped_item_line(k) for k in items if k in ITEMS]
    equipped_header = f"Экипировано ({len(equipped)}/{max_slots}):"
    equipped_text = equipped_header + ("\n" + "\n".join(equipped) if equipped else " ничего")
    return f"🎒 <b>Твой инвентарь</b>\n{equipped_text}\n\nВыбери раздел:"

INV_PAGE_SIZE = 5
POTION_PAGE_SIZE = 6

def inventory_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧪 Бустеры", callback_data=f"inv_cat:{user_id}:boosters:0")],
        [InlineKeyboardButton(text="📦 Предметы", callback_data=f"inv_cat:{user_id}:items:0")],
        [InlineKeyboardButton(text="⚗️ Зелья", callback_data=f"inv_cat:{user_id}:potions:0")],
    ])

def _paginate(items: list, page: int, page_size: int = INV_PAGE_SIZE):
    """Возвращает (нарезка_страницы, страница_в_границах, всего_страниц)."""
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    return items[start:start + page_size], page, total_pages

def _pagination_row(callback_prefix: str, user_id: int, page: int, total_pages: int, extra: str = "") -> list:
    """Строка навигации ◀️ n/N ▶️. extra — доп. часть callback_data (например поисковый запрос)."""
    if total_pages <= 1:
        return []
    suffix = f":{extra}" if extra else ""
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{callback_prefix}:{user_id}:{page - 1}{suffix}", style="primary"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{callback_prefix}:{user_id}:{page + 1}{suffix}", style="primary"))
    return nav

def boosters_keyboard(rows, active_items, user_id: int, page: int = 0, query: str = None) -> InlineKeyboardMarkup:
    equipped = set(_normalize_active_items(active_items))
    boosters = [(k, q) for k, q in rows if k not in PASSIVE_ITEMS]
    if query:
        ql = query.lower()
        boosters = [(k, q) for k, q in boosters if ql in ITEMS[k][1].lower()]
    page_items, page, total_pages = _paginate(boosters, page)

    kb_rows = []
    for item_key, qty in page_items:
        emoji, name, percent, _ = ITEMS[item_key]
        is_equipped = item_key in equipped
        mark = " ✅" if is_equipped else ""
        cb = f"equip:{user_id}:{item_key}:{page}"
        if query:
            cb += f":{quote(query)}"
        kb_rows.append([InlineKeyboardButton(
            text=f"{name} {plain_emoji(emoji)} ({_percent_label(item_key, percent)}) x{qty}{mark}",
            callback_data=cb,
            style="success" if is_equipped else None,
        )])

    if query:
        nav_row = _pagination_row("inv_boost_search_page", user_id, page, total_pages, extra=quote(query))
    else:
        nav_row = _pagination_row("inv_boost_page", user_id, page, total_pages)
    if nav_row:
        kb_rows.append(nav_row)
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"inv_menu:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)

def items_keyboard(user_id: int, rows=None, page: int = 0) -> InlineKeyboardMarkup:
    rows = rows or []
    passive = [(k, q) for k, q in rows if k in PASSIVE_ITEMS]
    _, page, total_pages = _paginate(passive, page)
    kb_rows = []
    nav_row = _pagination_row("inv_items_page", user_id, page, total_pages)
    if nav_row:
        kb_rows.append(nav_row)
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"inv_menu:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)

def format_autosell_text(auto_sell_enabled: bool, auto_sell_items: set, page: int = 0) -> str:
    _, page, total_pages = _paginate(CASE_SELLABLE_ITEMS, page, AUTOSELL_PAGE_SIZE)
    page_suffix = f" (стр. {page + 1}/{total_pages})" if total_pages > 1 else ""
    status = "включена ✅" if auto_sell_enabled else "выключена ❌"
    return (
        f"💰 <b>Авто-продажа дропа из кейсов 1/2/3</b>{page_suffix}\n"
        f"Статус: {status}\n"
        f"Отмечено предметов: {len(auto_sell_items)}\n\n"
        f"Жми на предмет, чтобы включить/выключить его авто-продажу:"
    )

def autosell_keyboard(auto_sell_enabled: bool, auto_sell_items: set, user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    page_items, page, total_pages = _paginate(CASE_SELLABLE_ITEMS, page, AUTOSELL_PAGE_SIZE)
    kb_rows = []
    for item_key in page_items:
        emoji, name, _, _ = ITEMS[item_key]
        is_on = item_key in auto_sell_items
        mark = "✅" if is_on else "❌"
        kb_rows.append([InlineKeyboardButton(
            text=f"{name} {plain_emoji(emoji)} {mark}",
            callback_data=f"autosell_toggle:{user_id}:{item_key}:{page}",
            style="success" if is_on else "danger",
        )])

    nav_row = _pagination_row("autosell_page", user_id, page, total_pages)
    if nav_row:
        kb_rows.append(nav_row)

    switch_text = "🔴 Выключить авто-продажу" if auto_sell_enabled else "🟢 Включить авто-продажу"
    kb_rows.append([InlineKeyboardButton(
        text=switch_text, callback_data=f"autosell_switch:{user_id}:{page}",
        style="danger" if auto_sell_enabled else "success",
    )])
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"inv_menu:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)

def format_boosters_text(rows, max_slots: int = 1, page: int = 0, query: str = None):
    boosters = [(k, q) for k, q in rows if k not in PASSIVE_ITEMS]
    if query:
        ql = query.lower()
        boosters = [(k, q) for k, q in boosters if ql in ITEMS[k][1].lower()]
        if not boosters:
            return f"🔍 По запросу «{esc(query)}» бустеров не найдено."
        _, page, total_pages = _paginate(boosters, page)
        page_suffix = f" (стр. {page + 1}/{total_pages})" if total_pages > 1 else ""
        return f"🔍 Поиск «{esc(query)}»{page_suffix}:"
    if not boosters:
        return f"🧪 У тебя нет бустеров. Можно носить одновременно {max_slots}."
    _, page, total_pages = _paginate(boosters, page)
    page_suffix = f" (стр. {page + 1}/{total_pages})" if total_pages > 1 else ""
    return f"🧪 Твои бустеры (можно носить одновременно {max_slots}){page_suffix}:"

def format_items_text(rows, page: int = 0):
    passive = [(k, q) for k, q in rows if k in PASSIVE_ITEMS]
    if not passive:
        return "📦 У тебя нет предметов."
    page_items, page, total_pages = _paginate(passive, page)
    page_suffix = f" (стр. {page + 1}/{total_pages})" if total_pages > 1 else ""
    lines = [f"📦 Твои предметы (нельзя экипировать, действуют пассивно){page_suffix}:\n"]
    for item_key, qty in page_items:
        emoji, name, _, _ = ITEMS[item_key]
        lines.append(f"{emoji} {esc(name)} x{qty}")
    return "\n".join(lines)

def format_time_left(seconds: int) -> str:
    seconds = max(0, seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}ч {m}м"
    if m:
        return f"{m}м {s}с"
    return f"{s}с"

# ---- Справочные тексты для «помощь зелье <название>» ----
def find_potion_key_by_name(query: str):
    """Ищет ключ POTIONS по русскому названию. Сначала точное совпадение, иначе — по
    вхождению подстроки (как find_item_by_name). Возвращает (key, None) при однозначном
    совпадении, (None, [варианты]) при неоднозначности, (None, []) если не найдено."""
    q = (query or "").strip().lower()
    if not q:
        return None, []
    for key, cfg in POTIONS.items():
        if cfg["name"].strip().lower() == q:
            return key, None
    matches = [key for key, cfg in POTIONS.items() if q in cfg["name"].lower()]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        matches.sort(key=lambda k: POTIONS[k]["name"])
        return None, matches
    return None, []

def format_help_potion_text(key: str) -> str:
    cfg = POTIONS[key]
    lines = [cfg["desc"] + "."]

    if cfg["effect"] == "no_cd":
        lines.append(f"Действует: {cfg['charges']} следующих использования фермы.")
    else:
        lines.append(f"Длительность эффекта: {format_time_left(cfg['duration_seconds'])} после выпития.")

    lines.append(
        f"Варка: {cfg['brew_cost']} 🪙, занимает {format_time_left(cfg['brew_seconds'])} "
        "— открой «мои зелья» и жми «⚗️ Варить»."
    )
    lines.append("Забрать готовое и выпить — тоже кнопками там же («✅ Забрать» / «▶️ Использовать»).")
    lines.append("Скорость и длительность варки можно улучшить в апгрейдах: «Скорость готовки зелья», «Длительность зелья».")
    return "\n".join(lines)

def format_potions_text(inventory_potions: dict, active_potions: dict, brewing_potion: str, brewing_until: int,
                         upgrades: dict, now: int = None, page: int = 0) -> str:
    now = now or int(time.time())
    _, page, total_pages = _paginate(POTION_ORDER, page, POTION_PAGE_SIZE)
    page_suffix = f" (стр. {page + 1}/{total_pages})" if total_pages > 1 else ""
    lines = [f"⚗️ <b>Зелья</b>{page_suffix}"]

    if brewing_potion and brewing_potion in POTIONS:
        cfg = POTIONS[brewing_potion]
        left = brewing_until - now
        if left > 0:
            lines.append(f"🔥 {cfg['emoji']} {esc(cfg['name'])} — готово через {format_time_left(left)}")
        else:
            lines.append(f"✅ {cfg['emoji']} {esc(cfg['name'])} готово — забери ниже")
    else:
        lines.append("🔥 Котёл свободен")

    for key, val in active_potions.items():
        cfg = POTIONS[key]
        if cfg["effect"] == "no_cd":
            lines.append(f"● {cfg['emoji']} {val} исп.")
        else:
            lines.append(f"● {cfg['emoji']} {format_time_left(val - now)}")

    owned = [f"{POTIONS[k]['emoji']}x{q}" for k, q in inventory_potions.items() if q > 0]
    if owned:
        lines.append("В запасе:")
        lines.extend(f"  {o}" for o in owned)
    else:
        lines.append("В запасе: пусто")

    return "\n".join(lines)

def potions_keyboard(inventory_potions: dict, brewing_potion: str, brewing_until: int, user_id: int,
                      upgrades: dict, now: int = None, prestige_upgrades: dict = None, page: int = 0,
                      active_items=None) -> InlineKeyboardMarkup:
    now = now or int(time.time())
    kb_rows = []

    brewing_active = bool(brewing_potion) and brewing_until > now
    brewing_ready = bool(brewing_potion) and brewing_until <= now

    page_order, page, total_pages = _paginate(POTION_ORDER, page, POTION_PAGE_SIZE)

    if brewing_ready:
        cfg = POTIONS[brewing_potion]
        kb_rows.append([InlineKeyboardButton(
            text=f"✅ Забрать {cfg['emoji']} {cfg['name']}",
            callback_data=f"potion_collect:{user_id}",
        )])
    elif not brewing_active:
        for key in page_order:
            cfg = POTIONS[key]
            seconds = brew_seconds_for(key, upgrades, prestige_upgrades, active_items)
            kb_rows.append([InlineKeyboardButton(
                text=f"⚗️ Варить {cfg['emoji']} {cfg['name']} ({cfg['brew_cost']}🪙, {format_time_left(seconds)})",
                callback_data=f"potion_brew:{user_id}:{key}",
            )])

    for key in page_order:
        qty = inventory_potions.get(key, 0)
        if qty > 0:
            cfg = POTIONS[key]
            kb_rows.append([InlineKeyboardButton(
                text=f"▶️ Использовать {cfg['emoji']} {cfg['name']} (x{qty})",
                callback_data=f"potion_use:{user_id}:{key}",
            )])

    nav_row = _pagination_row("inv_potion_page", user_id, page, total_pages)
    if nav_row:
        kb_rows.append(nav_row)
    kb_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"inv_cat:{user_id}:potions:{page}")])
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"inv_menu:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)

@dp.message(F.text.lower().in_({"инвентарь", "мой инвентарь"}))
async def inventory(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    prestige_upgrades = parse_prestige_upgrades(row[28])
    rows = await get_inventory(user_id)

    if not rows:
        await message.reply(TEXTS["inventory_1"])
        return

    await safe_reply(message, format_inventory_menu_text(active_items, upgrades, prestige_upgrades), reply_markup=inventory_menu_keyboard(user_id))

@dp.message(F.text.lower().in_({"мои предметы", "предметы"}))
async def my_items_tab(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)
    rows = await get_inventory(user_id)
    await safe_reply(message, format_items_text(rows), reply_markup=items_keyboard(user_id, rows))

@dp.message(F.text.lower().in_({"мои бустеры", "бустеры"}))
async def my_boosters_tab(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    prestige_upgrades = parse_prestige_upgrades(row[28])
    rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in rows}
    max_slots = equipped_slots_max(upgrades, prestige_upgrades, coin_tree_slot_bonus(inventory_map))
    await message.reply(format_boosters_text(rows, max_slots), reply_markup=boosters_keyboard(rows, active_items, user_id, 0))

@dp.message(F.text.lower().regexp(r"^бустеры поиск\s+.+$"))
async def my_boosters_search(message: Message):
    query = message.text.strip()[len("бустеры поиск"):].strip()
    if not query:
        return
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    active_items = parse_equipped(row[18])
    rows = await get_inventory(user_id)
    await message.reply(
        format_boosters_text(rows, page=0, query=query),
        reply_markup=boosters_keyboard(rows, active_items, user_id, 0, query=query),
    )

@dp.message(F.text.lower().in_({"мои зелья", "зелья"}))
async def my_potions_tab(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    upgrades = parse_upgrades(row[16])
    stock = parse_potion_stock(row[26])
    active_items = parse_equipped(row[18])
    active = active_potions_now(row[23], active_items=active_items)
    brewing_potion, brewing_until = row[24], row[25]
    prestige_upgrades = parse_prestige_upgrades(row[28])
    await message.reply(
        format_potions_text(stock, active, brewing_potion, brewing_until, upgrades),
        reply_markup=potions_keyboard(stock, brewing_potion, brewing_until, user_id, upgrades, prestige_upgrades=prestige_upgrades, active_items=active_items),
    )

@dp.callback_query(F.data.startswith("inv_menu:"))
async def inventory_back_to_menu(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_back_to_menu_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    prestige_upgrades = parse_prestige_upgrades(row[28])
    rows = await get_inventory(owner_id)
    inventory_map = {k: q for k, q in rows}
    await safe_edit_text(callback, format_inventory_menu_text(active_items, upgrades, prestige_upgrades, coin_tree_slot_bonus(inventory_map)), reply_markup=inventory_menu_keyboard(owner_id))

@dp.callback_query(F.data.startswith("inv_cat:"))
async def inventory_open_category(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    category = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    await callback.answer()

    if category == "boosters":
        rows = await get_inventory(owner_id)
        row = await get_user(owner_id)
        upgrades = parse_upgrades(row[16])
        active_items = parse_equipped(row[18])
        prestige_upgrades = parse_prestige_upgrades(row[28])
        inventory_map = {k: q for k, q in rows}
        max_slots = equipped_slots_max(upgrades, prestige_upgrades, coin_tree_slot_bonus(inventory_map))
        await safe_edit_text(callback, format_boosters_text(rows, max_slots, page), reply_markup=boosters_keyboard(rows, active_items, owner_id, page))
    elif category == "potions":
        row = await get_user(owner_id)
        upgrades = parse_upgrades(row[16])
        stock = parse_potion_stock(row[26])
        active_items = parse_equipped(row[18])
        active = active_potions_now(row[23], active_items=active_items)
        brewing_potion, brewing_until = row[24], row[25]
        prestige_upgrades = parse_prestige_upgrades(row[28])
        await safe_edit_text(
            callback,
            format_potions_text(stock, active, brewing_potion, brewing_until, upgrades, page=page),
            reply_markup=potions_keyboard(stock, brewing_potion, brewing_until, owner_id, upgrades, prestige_upgrades=prestige_upgrades, page=page, active_items=active_items),
        )
    else:
        rows = await get_inventory(owner_id)
        await safe_edit_text(callback, format_items_text(rows, page), reply_markup=items_keyboard(owner_id, rows, page))

@dp.callback_query(F.data.startswith("potion_brew:"))
async def potion_brew_start(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    potion_key = parts[2]
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    if potion_key not in POTIONS:
        await callback.answer()
        return

    now = int(time.time())
    row = await get_user(owner_id)
    coins = row[5]
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    brewing_potion, brewing_until = row[24], row[25]
    prestige_upgrades = parse_prestige_upgrades(row[28])

    if brewing_potion and brewing_until > now:
        await callback.answer(TEXTS["potion_brew_busy_1"], show_alert=True)
        return

    cfg = POTIONS[potion_key]
    if coins < cfg["brew_cost"]:
        await callback.answer(TEXTS["potion_brew_no_coins_1"].format(v0=cfg["brew_cost"], v1=coins), show_alert=True)
        return

    seconds = brew_seconds_for(potion_key, upgrades, prestige_upgrades, active_items)
    new_until = now + seconds
    await db_exec(
        "UPDATE users SET coins = coins - ?, brewing_potion = ?, brewing_until = ? WHERE user_id = ?",
        (cfg["brew_cost"], potion_key, new_until, owner_id),
    )

    stock = parse_potion_stock(row[26])
    await safe_edit_text(
        callback,
        format_potions_text(stock, active_potions_now(row[23], now, active_items), potion_key, new_until, upgrades, now),
        reply_markup=potions_keyboard(stock, potion_key, new_until, owner_id, upgrades, now, prestige_upgrades, active_items=active_items),
    )
    await callback.answer(TEXTS["potion_brew_started_1"].format(v0=cfg["emoji"], v1=cfg["name"], v2=format_time_left(seconds)))

@dp.callback_query(F.data.startswith("potion_collect:"))
async def potion_collect(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return

    now = int(time.time())
    row = await get_user(owner_id)
    brewing_potion, brewing_until = row[24], row[25]
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    prestige_upgrades = parse_prestige_upgrades(row[28])

    if not brewing_potion:
        await callback.answer(TEXTS["potion_collect_none_1"], show_alert=True)
        return
    if brewing_until > now:
        await callback.answer(TEXTS["potion_collect_not_ready_1"].format(v0=format_time_left(brewing_until - now)), show_alert=True)
        return

    stock = parse_potion_stock(row[26])
    stock[brewing_potion] = stock.get(brewing_potion, 0) + 1
    await db_exec(
        "UPDATE users SET brewing_potion = NULL, brewing_until = 0, potion_stock = ? WHERE user_id = ?",
        (format_potion_stock(stock), owner_id),
    )

    cfg = POTIONS[brewing_potion]
    await safe_edit_text(
        callback,
        format_potions_text(stock, active_potions_now(row[23], now, active_items), None, 0, upgrades, now),
        reply_markup=potions_keyboard(stock, None, 0, owner_id, upgrades, now, prestige_upgrades, active_items=active_items),
    )
    await callback.answer(TEXTS["potion_collect_ok_1"].format(v0=cfg["emoji"], v1=cfg["name"]))

@dp.callback_query(F.data.startswith("potion_use:"))
async def potion_use(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    potion_key = parts[2]
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    if potion_key not in POTIONS:
        await callback.answer()
        return

    now = int(time.time())
    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    stock = parse_potion_stock(row[26])
    prestige_upgrades = parse_prestige_upgrades(row[28])

    if stock.get(potion_key, 0) <= 0:
        await callback.answer(TEXTS["potion_use_none_1"], show_alert=True)
        return

    stock[potion_key] -= 1
    if stock[potion_key] <= 0:
        del stock[potion_key]

    active = active_potions_now(row[23], now, active_items)
    cfg = POTIONS[potion_key]
    if cfg["effect"] == "no_cd":
        active[potion_key] = cfg["charges"]
    else:
        duration = potion_duration_seconds(potion_key, upgrades)
        active[potion_key] = now + duration

    await db_exec(
        "UPDATE users SET potion_stock = ?, active_potions = ? WHERE user_id = ?",
        (format_potion_stock(stock), format_potions(active), owner_id),
    )

    brewing_potion, brewing_until = row[24], row[25]
    await safe_edit_text(
        callback,
        format_potions_text(stock, active, brewing_potion, brewing_until, upgrades, now),
        reply_markup=potions_keyboard(stock, brewing_potion, brewing_until, owner_id, upgrades, now, prestige_upgrades, active_items=active_items),
    )
    if cfg["effect"] == "no_cd":
        await callback.answer(TEXTS["potion_use_ok_charges_1"].format(v0=cfg["emoji"], v1=cfg["name"], v2=cfg["charges"]))
    else:
        await callback.answer(TEXTS["potion_use_ok_1"].format(v0=cfg["emoji"], v1=cfg["name"], v2=format_time_left(potion_duration_seconds(potion_key, upgrades))))

@dp.callback_query(F.data.startswith("inv_boost_page:"))
async def inventory_boosters_page(callback: CallbackQuery):
    _, owner_str, page_str = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    prestige_upgrades = parse_prestige_upgrades(row[28])
    rows = await get_inventory(owner_id)
    inventory_map = {k: q for k, q in rows}
    max_slots = equipped_slots_max(upgrades, prestige_upgrades, coin_tree_slot_bonus(inventory_map))
    await safe_edit_text(callback, format_boosters_text(rows, max_slots, page), reply_markup=boosters_keyboard(rows, active_items, owner_id, page))

@dp.callback_query(F.data.startswith("inv_boost_search_page:"))
async def inventory_boosters_search_page(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    page = int(parts[2])
    query = unquote(parts[3]) if len(parts) > 3 else ""
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    active_items = parse_equipped(row[18])
    rows = await get_inventory(owner_id)
    await safe_edit_text(callback, 
        format_boosters_text(rows, page=page, query=query),
        reply_markup=boosters_keyboard(rows, active_items, owner_id, page, query=query),
    )

@dp.callback_query(F.data.startswith("inv_items_page:"))
async def inventory_items_page(callback: CallbackQuery):
    _, owner_str, page_str = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    await callback.answer()

    rows = await get_inventory(owner_id)
    await safe_edit_text(callback, format_items_text(rows, page), reply_markup=items_keyboard(owner_id, rows, page))

@dp.callback_query(F.data.startswith("inv_potion_page:"))
async def inventory_potions_page(callback: CallbackQuery):
    _, owner_str, page_str = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    stock = parse_potion_stock(row[26])
    active = active_potions_now(row[23], active_items=active_items)
    brewing_potion, brewing_until = row[24], row[25]
    prestige_upgrades = parse_prestige_upgrades(row[28])
    await safe_edit_text(
        callback,
        format_potions_text(stock, active, brewing_potion, brewing_until, upgrades, page=page),
        reply_markup=potions_keyboard(stock, brewing_potion, brewing_until, owner_id, upgrades, prestige_upgrades=prestige_upgrades, page=page, active_items=active_items),
    )

@dp.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data.startswith("equip:"))
async def toggle_equip(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    item_key = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    query = unquote(parts[4]) if len(parts) > 4 else None
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["toggle_equip_1"], show_alert=True)
        return
    if item_key in PASSIVE_ITEMS:
        await callback.answer(TEXTS["toggle_equip_2"], show_alert=True)
        return

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    prestige_upgrades = parse_prestige_upgrades(row[28])
    rows = await get_inventory(owner_id)
    inventory_map = {k: q for k, q in rows}
    max_slots = equipped_slots_max(upgrades, prestige_upgrades, coin_tree_slot_bonus(inventory_map))

    before = parse_equipped(row[18])
    kicked = before[0] if item_key not in before and len(before) >= max_slots else None
    new_equipped = equip_item(row[18], item_key, max_slots)

    await db_exec("UPDATE users SET equipped_items = ? WHERE user_id = ?", (format_equipped(new_equipped), owner_id))

    await safe_edit_text(callback, 
        format_boosters_text(rows, max_slots, page, query=query),
        reply_markup=boosters_keyboard(rows, new_equipped, owner_id, page, query=query),
    )
    if kicked and kicked in ITEMS:
        await callback.answer(TEXTS["toggle_equip_3"].format(v0=ITEMS[item_key][1], v1=ITEMS[kicked][1]))
    else:
        await callback.answer(TEXTS["toggle_equip_4"])

CRAFT_RE = re.compile(r"^крафт(?:ы)?(?:\s+(.+))?$", re.IGNORECASE)

def craft_level_of(upgrades: dict) -> int:
    return upgrade_level(upgrades, "crafts")

def recipe_is_discovered(recipe: dict, inventory_map: dict) -> bool:
    """Как в Minecraft: рецепт «открыт» (виден в списке), если у игрока есть хотя бы
    1 шт. любого предметного ингредиента. Валюта (монеты/очки/💠/🉑) на открытие не влияет —
    только на возможность реально скрафтить (см. recipe_missing_ingredients)."""
    ingredients = recipe.get("ingredients", {})
    if not ingredients and not recipe.get("needs_all_amulets"):
        return True
    for ing_key in ingredients:
        if inventory_map.get(ing_key, 0) > 0:
            return True
    if recipe.get("needs_all_amulets"):
        if any(inventory_map.get(ing_key, 0) > 0 for ing_key in ALL_PLAYER_AMULETS):
            return True
    return False

def available_recipes(craft_level: int, inventory_map: dict, query: str = None) -> list:
    """Рецепты, доступные по уровню крафта игрока И уже «открытые» (есть хотя бы 1 нужный
    предмет в инвентаре — валюта не считается), отфильтрованные по подстроке в названии результата."""
    result = []
    for key, recipe in RECIPES.items():
        if recipe["level"] > craft_level:
            continue
        if not recipe_is_discovered(recipe, inventory_map):
            continue
        if query and query.lower() not in ITEMS[key][1].lower():
            continue
        result.append(key)
    return result

def crafts_keyboard(recipe_keys: list, user_id: int, page: int = 0, query: str = "") -> InlineKeyboardMarkup:
    page_items, page, total_pages = _paginate(recipe_keys, page)

    rows = []
    for key in page_items:
        emoji, name, _, _ = ITEMS[key]
        rows.append([InlineKeyboardButton(
            text=f"{plain_emoji(emoji)} Скрафтить {name}",
            callback_data=f"craft:{user_id}:{key}",
        )])

    nav_row = _pagination_row("craft_page", user_id, page, total_pages, extra=query)
    if nav_row:
        rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def format_crafts_text(recipe_keys: list, craft_level: int, query: str, page: int = 0) -> str:
    if not recipe_keys:
        if query:
            return f"🔨 Нет доступных рецептов по запросу «{esc(query)}» (либо не хватает уровня крафта, либо нет ни одного нужного ингредиента в инвентаре)."
        return (
            f"🔨 Нет открытых рецептов ({craft_level}/{CRAFT_MAX_LEVEL} ур. крафта).\n"
            f"Рецепт появляется в списке, когда у тебя есть хотя бы 1 нужный предмет — "
            f"добывай ингредиенты в кейсах и качай апгрейд «Крафты» в прокачке!"
        )

    page_keys, page, total_pages = _paginate(recipe_keys, page)
    page_suffix = f" — стр. {page + 1}/{total_pages}" if total_pages > 1 else ""
    lines = [f"🔨 <b>Доступные рецепты</b> (уровень крафта {craft_level}/{CRAFT_MAX_LEVEL}){page_suffix}:\n"]
    for key in page_keys:
        emoji, name, _, _ = ITEMS[key]
        lines.append(f"{emoji} <b>{esc(name)}</b> = {esc(format_recipe_requirements(RECIPES[key]))}")
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
    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}

    recipe_keys = available_recipes(craft_level, inventory_map, query)
    await message.reply(
        format_crafts_text(recipe_keys, craft_level, query or "", 0),
        reply_markup=crafts_keyboard(recipe_keys, user_id, 0, query or "") if recipe_keys else None,
    )

@dp.callback_query(F.data.startswith("craft_page:"))
async def crafts_page_nav(callback: CallbackQuery):
    parts = callback.data.split(":", 3)
    owner_id = int(parts[1])
    page = int(parts[2])
    query = parts[3] if len(parts) > 3 and parts[3] else None
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["craft_do_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    craft_level = craft_level_of(upgrades)
    inv_rows = await get_inventory(owner_id)
    inventory_map = {k: q for k, q in inv_rows}
    recipe_keys = available_recipes(craft_level, inventory_map, query)

    await safe_edit_text(callback, 
        format_crafts_text(recipe_keys, craft_level, query or "", page),
        reply_markup=crafts_keyboard(recipe_keys, owner_id, page, query or "") if recipe_keys else None,
    )

@dp.callback_query(F.data.startswith("craft:"))
async def craft_do(callback: CallbackQuery):
    _, owner_str, recipe_key = callback.data.split(":")
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["craft_do_1"], show_alert=True)
        return
    if recipe_key not in RECIPES:
        await callback.answer(TEXTS["craft_do_2"], show_alert=True)
        return

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    prestige_upgrades = parse_prestige_upgrades(row[28])
    craft_level = craft_level_of(upgrades)
    recipe = RECIPES[recipe_key]

    if recipe["level"] > craft_level:
        await callback.answer(TEXTS["craft_do_3"].format(v0=recipe['level'], v1=craft_level), show_alert=True)
        return

    coins, score = row[5], row[2]
    craft_points = row[32]
    rebirth_points = row[14]
    inv_rows = await get_inventory(owner_id)
    inventory_map = {k: q for k, q in inv_rows}

    missing = recipe_missing_ingredients(inventory_map, coins, score, recipe, prestige_upgrades, craft_points, rebirth_points)
    if missing:
        await callback.answer("Не хватает: " + "; ".join(missing), show_alert=True)
        return

    for ing_key, qty in recipe.get("ingredients", {}).items():
        await remove_item(owner_id, ing_key, qty)
    if recipe.get("needs_all_amulets"):
        for ing_key in ALL_PLAYER_AMULETS:
            await remove_item(owner_id, ing_key, 1)
    if recipe.get("coin_cost"):
        discounted_cost = craft_coin_cost_with_discount(recipe["coin_cost"], prestige_upgrades)
        await db_exec("UPDATE users SET coins = coins - ? WHERE user_id = ?", (discounted_cost, owner_id))
    if recipe.get("score_cost"):
        await db_exec("UPDATE users SET score = score - ? WHERE user_id = ?", (recipe["score_cost"], owner_id))
    if recipe.get("craft_points_cost"):
        await db_exec(
            "UPDATE users SET craft_points = craft_points - ? WHERE user_id = ?",
            (recipe["craft_points_cost"], owner_id),
        )
    if recipe.get("rebirth_cost"):
        await db_exec(
            "UPDATE users SET rebirth_points = rebirth_points - ? WHERE user_id = ?",
            (recipe["rebirth_cost"], owner_id),
        )

    await add_item(owner_id, recipe_key, 1)

    emoji, name, _, _ = ITEMS[recipe_key]
    result_text = f"✅ Скрафтил {emoji} {name}!"

    await callback.message.reply(result_text)
    await callback.answer(TEXTS["craft_do_4"])

