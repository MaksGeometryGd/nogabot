import asyncio
import os
import random
import re
import time

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

TOKEN = os.environ.get("8383839196:AAEJAbGIB1gqtQ85M4ZRZ98Z9m4MeCvlank")
ADMIN_USERNAME = "MaksGeometryGd"
DB_PATH = "nogost.db"

PREMIUM_MIKU = '<tg-emoji emoji-id="5199793038410391513">🤩</tg-emoji>'
PREMIUM_MGG = '<tg-emoji emoji-id="6327920744789444368">🥰</tg-emoji>'

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

REGULAR_THRESHOLDS = [10, 50, 150, 300, 500, 800, 1200, 1600, 2000, 2400,
                       3000, 3600, 4200, 4800, 5400, 6000, 6600, 7200, 7800, 8400]

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
    (16200, "🦵", "нога Panther"),
    (16800, PREMIUM_MIKU, "нога Мику"),
    (17400, "🦵🏇", "нога героя"),
    (18000, "🦵👁", "нога полу-бога"),
    (18600, "🦵🌌", "космическая нога"),
    (19200, "🦵🧿", "нога бога"),
    (19800, PREMIUM_MGG, "нога MGG"),
]

ALL_THRESHOLDS = REGULAR_THRESHOLDS + [t for t, _, _ in CUSTOM_LEVELS]
MAX_LEVEL_SCORE = ALL_THRESHOLDS[-1]

LEG_POINT = 1
LEG_LIMIT = 5
MEK_POINT = 25
MEK_LIMIT = 10

FARM_COOLDOWN = 3600
FARM_BASE = (100, 250)
FARM_EVOLVED = (700, 1250)

EXCHANGE_RATE = 200
CASE_PRICE = 20

ITEMS = {
    "amulet": ("🪬", "Амулет галактики", 25, 10),
    "orb":    ("🔮", "Шар парадокса", 20, 20),
    "pill":   ("💊", "Таблетка силы", 8, 30),
    "candle": ("🪔", "Свеча солнцестояния", 6, 35),
    "gift":   ("💮", "Подарок кошко-девочки", 70, 5),
    "star":   ("⭐️", "Звезда перерождения", 50, 0),
}
CASE_POOL = [k for k in ITEMS if k != "star"]

ADMIN_GIVE_RE = re.compile(r"^дать ног (\d+)(\s+себе)?$", re.IGNORECASE)
EXCHANGE_RE = re.compile(r"^обменять (\d+)$", re.IGNORECASE)


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


def farm_range(evolution_level: int):
    return FARM_EVOLVED if evolution_level >= 1 else FARM_BASE


def is_admin(message: Message) -> bool:
    return (message.from_user.username or "").lower() == ADMIN_USERNAME.lower()


def roll_case_item() -> str:
    weights = [ITEMS[k][3] for k in CASE_POOL]
    return random.choices(CASE_POOL, weights=weights, k=1)[0]


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            score INTEGER DEFAULT 0,
            evolution_level INTEGER DEFAULT 0,
            last_farm INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            active_item TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            user_id INTEGER,
            item_key TEXT,
            qty INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, item_key)
        )
        """)
        await db.commit()


async def get_user(db, user_id: int):
    cur = await db.execute(
        "SELECT user_id, username, score, evolution_level, last_farm, coins, active_item FROM users WHERE user_id = ?",
        (user_id,),
    )
    return await cur.fetchone()


async def ensure_user(db, user_id: int, username: str):
    row = await get_user(db, user_id)
    if row is None:
        await db.execute("INSERT INTO users (user_id, username, score) VALUES (?, ?, 0)", (user_id, username))
        await db.commit()
        return (user_id, username, 0, 0, 0, 0, None)
    if row[1] != username:
        await db.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        await db.commit()
    return row


async def get_inventory(db, user_id: int):
    cur = await db.execute("SELECT item_key, qty FROM inventory WHERE user_id = ? AND qty > 0", (user_id,))
    return await cur.fetchall()


async def add_item(db, user_id: int, item_key: str, qty: int = 1):
    await db.execute(
        "INSERT INTO inventory (user_id, item_key, qty) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, item_key) DO UPDATE SET qty = qty + excluded.qty",
        (user_id, item_key, qty),
    )
    await db.commit()


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


@dp.message(F.text.regexp(r"[🦵🦿]"))
async def count_legs(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    text = message.text

    async with aiosqlite.connect(DB_PATH) as db:
        _, _, score, evolution_level, last_farm, coins, active_item = await ensure_user(db, user_id, username)

        legs = min(text.count("🦵"), LEG_LIMIT)
        gained = legs * LEG_POINT

        mek = 0
        if evolution_level >= 1:
            mek = min(text.count("🦿"), MEK_LIMIT)
            gained += mek * MEK_POINT

        if gained == 0:
            return

        mult = get_multiplier(evolution_level, active_item)
        total = round(gained * mult)
        new_score = score + total

        await db.execute("UPDATE users SET score = ? WHERE user_id = ?", (new_score, user_id))
        await db.commit()

    parts = f"+{legs}🦵"
    if mek:
        parts += f" +{mek}🦿"
    await message.reply(f"Лютый рофл засчитан! {parts} → +{total} очков (Всего: {new_score})")


@dp.message(F.text.lower() == "моя нога")
async def my_profile(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    async with aiosqlite.connect(DB_PATH) as db:
        _, _, score, evolution_level, last_farm, coins, active_item = await ensure_user(db, user_id, username)

    emoji, name = get_level_visual(score)
    level = get_level_index(score)
    nxt = next_level_text(score)
    mult = get_multiplier(evolution_level, active_item)

    text = (
        f"👣 <b>ТВОЯ ЛЮТАЯ НОГОСТЬ:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"● Очки: <code>{score}</code>\n"
        f"● Монеты: <code>{coins}</code> 🪙\n"
        f"● Вид ног: {emoji} {esc(name)} ({level} ур)\n"
        f"🎆 УРОВЕНЬ ЭВОЛЮЦИИ: {evolution_level}\n"
        f"● Процентовый буст: {round(mult * 100)}%\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"● {nxt}"
    )
    await message.reply(text)


@dp.message(F.text.lower() == "топ ног")
async def top_players(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT username, score, evolution_level FROM users ORDER BY score DESC LIMIT 10")
        rows = await cur.fetchall()

    if not rows:
        await message.reply("В топе пока пусто, никто еще не кинул ногу... 🧍")
        return

    text = "🏆 <b>ТОП-10 САМЫХ НОГАСТЫХ КИБОРГОВ:</b>\n\n"
    for i, (username, score, evolution_level) in enumerate(rows, 1):
        emoji, name = get_level_visual(score)
        evo = f" (эво {evolution_level})" if evolution_level else ""
        text += f"{i}. {esc(username)} — <code>{score}</code>{evo}\n   └ {emoji} {esc(name)}\n\n"

    await message.reply(text)


@dp.message(F.text.lower() == "ферма")
async def farm(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    now = int(time.time())

    async with aiosqlite.connect(DB_PATH) as db:
        _, _, score, evolution_level, last_farm, coins, active_item = await ensure_user(db, user_id, username)

        if now - last_farm < FARM_COOLDOWN:
            left = FARM_COOLDOWN - (now - last_farm)
            m, s = divmod(left, 60)
            await message.reply(f"Ферма на кулдауне ⏳ Осталось {m} мин {s} сек")
            return

        low, high = farm_range(evolution_level)
        mult = get_multiplier(evolution_level, active_item)
        gained = round(random.randint(low, high) * mult)
        new_score = score + gained

        await db.execute("UPDATE users SET score = ?, last_farm = ? WHERE user_id = ?", (new_score, now, user_id))
        await db.commit()

    await message.reply(f"Наферметил ногу! 🦵 +{gained} очков (Всего: {new_score})")


@dp.message(F.text.lower().startswith("обменять "))
async def exchange(message: Message):
    match = EXCHANGE_RE.match(message.text.strip().lower())
    if not match:
        await message.reply("Формат: обменять <количество очков>")
        return

    amount = int(match.group(1))
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    async with aiosqlite.connect(DB_PATH) as db:
        _, _, score, evolution_level, last_farm, coins, active_item = await ensure_user(db, user_id, username)

        coins_gained = amount // EXCHANGE_RATE
        if coins_gained == 0:
            await message.reply(f"Мало очков. Курс {EXCHANGE_RATE} очков ноги = 1 монета.")
            return

        spent = coins_gained * EXCHANGE_RATE
        if spent > score:
            await message.reply(f"Недостаточно очков. У тебя {score}.")
            return

        old_level = get_level_index(score)
        new_score = score - spent
        new_level = get_level_index(new_score)
        new_coins = coins + coins_gained

        await db.execute("UPDATE users SET score = ?, coins = ? WHERE user_id = ?", (new_score, new_coins, user_id))
        await db.commit()

    warn = f"\n⚠️ Уровень упал с {old_level} до {new_level}!" if new_level < old_level else ""
    await message.reply(f"Обменял {spent} очков → +{coins_gained} 🪙 монет (Всего монет: {new_coins}){warn}")


@dp.message(F.text.lower() == "инвентарь")
async def inventory(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    async with aiosqlite.connect(DB_PATH) as db:
        _, _, score, evolution_level, last_farm, coins, active_item = await ensure_user(db, user_id, username)
        rows = await get_inventory(db, user_id)

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

    async with aiosqlite.connect(DB_PATH) as db:
        row = await get_user(db, owner_id)
        active_item = row[6]
        new_active = None if active_item == item_key else item_key
        await db.execute("UPDATE users SET active_item = ? WHERE user_id = ?", (new_active, owner_id))
        await db.commit()
        rows = await get_inventory(db, owner_id)

    kb = inventory_keyboard(rows, new_active, owner_id)
    await callback.message.edit_text("🎒 Твой инвентарь (можно носить максимум 1 предмет):", reply_markup=kb)
    await callback.answer("Готово!")


@dp.message(F.text.lower() == "кейс")
async def case_menu(message: Message):
    user_id = message.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"🎁 Купить кейс ({CASE_PRICE} 🪙)", callback_data=f"case:{user_id}")
    ]])
    await message.reply("Кейс с бустерами ноги. Что выпадет — решает удача!", reply_markup=kb)


@dp.callback_query(F.data.startswith("case:"))
async def buy_case(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer("Это не твой кейс!", show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        row = await get_user(db, owner_id)
        coins = row[5]
        if coins < CASE_PRICE:
            await callback.answer(f"Не хватает монет. Нужно {CASE_PRICE} 🪙", show_alert=True)
            return

        item_key = roll_case_item()
        emoji, name, percent, _ = ITEMS[item_key]

        await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (CASE_PRICE, owner_id))
        await add_item(db, owner_id, item_key)
        new_coins = coins - CASE_PRICE

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"🎁 Купить кейс ({CASE_PRICE} 🪙)", callback_data=f"case:{owner_id}")
    ]])
    await callback.message.edit_text(
        f"🎉 Выпало: {emoji} {esc(name)} (+{percent}%)!\nОстаток монет: {new_coins} 🪙",
        reply_markup=kb,
    )
    await callback.answer("Кейс открыт!")


@dp.message(F.text.lower() == "эволюция")
async def evolve(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    async with aiosqlite.connect(DB_PATH) as db:
        _, _, score, evolution_level, last_farm, coins, active_item = await ensure_user(db, user_id, username)

        if score < MAX_LEVEL_SCORE:
            await message.reply(f"Нужно достичь «ногу мгг» (39 ур, {MAX_LEVEL_SCORE} очков), чтобы эволюционировать.")
            return

        new_evolution = evolution_level + 1
        await db.execute("UPDATE users SET score = 0, evolution_level = ? WHERE user_id = ?", (new_evolution, user_id))

        unlock_text = ""
        if new_evolution == 1:
            unlock_text = "\nОткрыта фарма 700-1250 очков и эмодзи 🦿 (25 очков, до 10 раз в соо)!"
        elif new_evolution == 2:
            await add_item(db, user_id, "star")
            unlock_text = "\nПолучена ⭐️ Звезда перерождения (+50%) — экипируй в инвентарь!"

        await db.commit()

    await message.reply(f"🎆 ЭВОЛЮЦИЯ! Прогресс сброшен, теперь у тебя {new_evolution} уровень эволюции навсегда.{unlock_text}")


@dp.message(F.text.lower().startswith("дать ног"))
async def admin_give(message: Message):
    if not is_admin(message):
        return

    match = ADMIN_GIVE_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: дать ног <количество> [себе] (в ответ на сообщение игрока)")
        return

    amount = int(match.group(1))
    to_self = bool(match.group(2))

    if to_self:
        target = message.from_user
    elif message.reply_to_message:
        target = message.reply_to_message.from_user
    else:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    target_username = target.username or target.first_name or "Без имени"

    async with aiosqlite.connect(DB_PATH) as db:
        row = await ensure_user(db, target.id, target_username)
        new_score = row[2] + amount
        await db.execute("UPDATE users SET score = ? WHERE user_id = ?", (new_score, target.id))
        await db.commit()

    await message.reply(f"Выдано {amount} очков ноги игроку {esc(target_username)}. Теперь у него: {new_score}")


async def handle(request):
    return web.Response(text="Бот Нога Работает!")


async def main():
    await init_db()

    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    print("Бот НОГА запущен!")
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        await bot.session.close()
        await runner.cleanup()


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Установи переменную окружения BOT_TOKEN")
    asyncio.run(main())
