"""
handlers_admin.py — административные команды: выдача/списание игровых
ресурсов, управление событиями и множителями, промокоды, рассылка новостей,
списки игроков/чатов/VIP, логи и их очистка, служебные команды (пинг,
рестарт, отладка).
"""
from aiogram import F
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Message
import asyncio
import os
import time
from datetime import datetime

from config import TEXTS, ULTRA_LEVEL_CAP, ULTRA_REQUIRED_LEG_LEVEL, VIP_FOREVER_SECONDS
from game_data import CASES, ITEMS, POTIONS, UPGRADES
from command_patterns import (
    ADMIN_CLEAR_INVENTORY_RE, ADMIN_DEBUG_RE, ADMIN_EVENT_CUSTOM_RE,
    ADMIN_FIND_RE, ADMIN_GIVE_ALL_RE, ADMIN_GIVE_BOOST_RE, ADMIN_GIVE_CASE_RE,
    ADMIN_GIVE_COIN_RE, ADMIN_GIVE_CRAFT_RE, ADMIN_GIVE_EVO_RE,
    ADMIN_GIVE_ITEM_RE, ADMIN_GIVE_KEY_RE, ADMIN_GIVE_LEGS_LVL_RE,
    ADMIN_GIVE_LEGS_RE, ADMIN_GIVE_REBIRTH_RE, ADMIN_GIVE_VIP_RE,
    ADMIN_PERSONAL_BOOST_RE, ADMIN_RESET_BONUS_RE, ADMIN_RESET_CD_RE,
    ADMIN_RESET_NICK_RE, ADMIN_RESET_RE, ADMIN_SET_EVO_RE, ADMIN_SET_LEGS_RE,
    ADMIN_SET_REBIRTH_RE, ADMIN_SET_UPGRADE_RE, ADMIN_SHOW_TEXT_RE,
    ADMIN_SIMULATE_EVO_RE, ADMIN_TAKE_BOOST_RE, ADMIN_TAKE_COIN_RE,
    ADMIN_TAKE_CRAFT_RE, ADMIN_TAKE_EVO_RE, ADMIN_TAKE_ITEM_RE,
    ADMIN_TAKE_LEGS_RE, ADMIN_TAKE_REBIRTH_RE, ADMIN_TAKE_VIP_RE,
    ADMIN_ULTRA_REBIRTH_RE, ADMIN_VIP_FOREVER_RE, ADMIN_WIPE_ECONOMY_RE,
    NEWS_PREFIX, PROMO_CREATE_BADGE_RE, PROMO_CREATE_RE, PROMO_DELETE_RE,
    PROMO_LIST_RE, PROMO_REDEEM_RE,
)
from text_utils import esc, parse_amount, safe_reply
from state import bot, dp
from economy import (
    PLAYER_LOG_MIN_INTERVAL, PROMO_BADGES, PROMO_TYPE_LABEL, USER_COLUMNS,
    _invalidate_event_state_cache, add_item, apply_promo_reward, db_exec,
    db_query, db_query_one, display_name, ensure_user, find_promo_badge_key,
    format_potion_stock, format_upgrades, get_all_chat_ids, get_event_state,
    get_level_index, get_level_visual, get_user_by_username, is_event_active,
    level_threshold, log_admin_action, parse_potion_stock, parse_promo_type,
    parse_upgrades, remove_item,
)
from game_logic import find_item_by_name, is_vip_active, resolve_target, roll_case_item
from subscription import is_admin
from handlers_profile import maybe_announce_levelup

@dp.message(F.text.lower().startswith("!дать очкп"))
async def admin_give_rebirth(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_REBIRTH_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_rebirth_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_rebirth_2"])
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_give_rebirth_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_points = row[14] + amount
    await db_exec("UPDATE users SET rebirth_points = ? WHERE user_id = ?", (new_points, target.id))
    await message.reply(TEXTS["admin_give_rebirth_4"].format(v0=amount, v1=esc(target_username), v2=new_points))

@dp.message(F.text.regexp(r"(?i)^!дать (?:крафт|очкк)\b"))
async def admin_give_craft(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_CRAFT_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !дать крафт <количество> [себе] (в ответ на сообщение игрока). Алиас: !дать очкк")
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
    new_points = row[32] + amount
    await db_exec("UPDATE users SET craft_points = ? WHERE user_id = ?", (new_points, target.id))
    await message.reply(f"Выдано {amount} 💠 очков крафта игроку {esc(target_username)} (Всего: {new_points})")

@dp.message(F.text.regexp(r"(?i)^!снять (?:крафт|очкк)\b"))
async def admin_take_craft(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_CRAFT_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !снять крафт <количество|все> [себе] (в ответ на сообщение игрока). Алиас: !снять очкк")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return
    target_username = target.username or target.first_name or "Без имени"

    if match.group(1) is None:
        await db_exec("UPDATE users SET craft_points = 0 WHERE user_id = ?", (target.id,))
        await message.reply(f"Снято все 💠 очки крафта у игрока {esc(target_username)} (Осталось: 0)")
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply("Некорректное количество.")
        return

    row = await ensure_user(target.id, target_username)
    new_points = max(0, row[32] - amount)
    await db_exec("UPDATE users SET craft_points = ? WHERE user_id = ?", (new_points, target.id))
    await message.reply(f"Снято {amount} 💠 очков крафта у игрока {esc(target_username)} (Осталось: {new_points})")

@dp.message(F.text.lower().startswith("!снять очкп"))
async def admin_take_rebirth(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_REBIRTH_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_rebirth_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_take_rebirth_2"])
        return
    target_username = target.username or target.first_name or "Без имени"

    if match.group(1) is None:
        await db_exec("UPDATE users SET rebirth_points = 0 WHERE user_id = ?", (target.id,))
        await message.reply(TEXTS["admin_take_rebirth_4"].format(v0="все", v1=esc(target_username), v2=0))
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_take_rebirth_3"])
        return

    row = await ensure_user(target.id, target_username)
    new_points = max(0, row[14] - amount)
    await db_exec("UPDATE users SET rebirth_points = ? WHERE user_id = ?", (new_points, target.id))
    await message.reply(TEXTS["admin_take_rebirth_4"].format(v0=amount, v1=esc(target_username), v2=new_points))

@dp.message(F.text.lower().startswith(NEWS_PREFIX))
async def broadcast_news(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    if message.chat.type != "private":
        return

    text = message.text[len(NEWS_PREFIX):].strip()
    if not text:
        await message.reply(TEXTS["broadcast_news_1"])
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

    await message.reply(TEXTS["broadcast_news_2"].format(v0=sent, v1=failed))

@dp.message(F.text.regexp(r"(?i)^!дать ног(?!и лвл)"))
async def admin_give_legs(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_LEGS_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_legs_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_legs_2"])
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_give_legs_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_score = row[2] + amount
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_score, target.id))
    await maybe_announce_levelup(message, target_username, row[2], new_score, row[3], bool(row[11]))

    await message.reply(TEXTS["admin_give_legs_4"].format(v0=amount, v1=esc(target_username), v2=new_score))

@dp.message(F.text.lower().startswith("!снять ноги"))
async def admin_take_legs(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_LEGS_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_legs_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_take_legs_2"])
        return
    target_username = target.username or target.first_name or "Без имени"

    if match.group(1) is None:
        await db_exec("UPDATE users SET score = 0 WHERE user_id = ?", (target.id,))
        await message.reply(TEXTS["admin_take_legs_4"].format(v0=esc(target_username), v1=0))
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_take_legs_3"])
        return

    row = await ensure_user(target.id, target_username)
    new_score = max(0, row[2] - amount)
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_score, target.id))

    await message.reply(TEXTS["admin_take_legs_4"].format(v0=esc(target_username), v1=new_score))

@dp.message(F.text.lower().startswith("!дать эво"))
async def admin_give_evo(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_EVO_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_evo_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_evo_2"])
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_give_evo_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_evo = row[3] + amount
    await db_exec("UPDATE users SET evolution_level = ? WHERE user_id = ?", (new_evo, target.id))

    await message.reply(TEXTS["admin_give_evo_4"].format(v0=amount, v1=esc(target_username), v2=new_evo))

@dp.message(F.text.lower().startswith("!снять эво"))
async def admin_take_evo(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_EVO_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_evo_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_take_evo_2"])
        return
    target_username = target.username or target.first_name or "Без имени"

    if match.group(1) is None:
        await db_exec("UPDATE users SET evolution_level = 0 WHERE user_id = ?", (target.id,))
        await message.reply(TEXTS["admin_take_evo_4"].format(v0="все", v1=esc(target_username), v2=0))
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_take_evo_3"])
        return

    row = await ensure_user(target.id, target_username)
    new_evo = max(0, row[3] - amount)
    await db_exec("UPDATE users SET evolution_level = ? WHERE user_id = ?", (new_evo, target.id))

    await message.reply(TEXTS["admin_take_evo_4"].format(v0=amount, v1=esc(target_username), v2=new_evo))

@dp.message(F.text.lower().startswith("!дать коин"))
async def admin_give_coin(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_COIN_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_coin_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_coin_2"])
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_give_coin_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_coins = row[5] + amount
    await db_exec("UPDATE users SET coins = ? WHERE user_id = ?", (new_coins, target.id))

    await message.reply(TEXTS["admin_give_coin_4"].format(v0=amount, v1=esc(target_username), v2=new_coins))

@dp.message(F.text.lower().startswith("!снять коин"))
async def admin_take_coin(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_COIN_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_coin_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_take_coin_2"])
        return
    target_username = target.username or target.first_name or "Без имени"

    if match.group(1) is None:
        await db_exec("UPDATE users SET coins = 0 WHERE user_id = ?", (target.id,))
        await message.reply(TEXTS["admin_take_coin_4"].format(v0="все", v1=esc(target_username), v2=0))
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_take_coin_3"])
        return

    row = await ensure_user(target.id, target_username)
    new_coins = max(0, row[5] - amount)
    await db_exec("UPDATE users SET coins = ? WHERE user_id = ?", (new_coins, target.id))

    await message.reply(TEXTS["admin_take_coin_4"].format(v0=amount, v1=esc(target_username), v2=new_coins))

@dp.message(F.text.lower().startswith("!дать б "))
async def admin_give_boost(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_BOOST_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_boost_1"])
        return

    item_key = find_item_by_name(match.group(1), only_passive=False)
    if not item_key:
        await message.reply(TEXTS["admin_give_boost_2"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_boost_3"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await add_item(target.id, item_key)

    emoji, name, _, _ = ITEMS[item_key]
    await safe_reply(message, TEXTS["admin_give_boost_4"].format(v0=emoji, v1=esc(name), v2=esc(target_username)))

@dp.message(F.text.lower().startswith("!снять б "))
async def admin_take_boost(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_BOOST_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_boost_1"])
        return

    item_key = find_item_by_name(match.group(1), only_passive=False)
    if not item_key:
        await message.reply(TEXTS["admin_take_boost_2"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_take_boost_3"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    removed = await remove_item(target.id, item_key)

    emoji, name, _, _ = ITEMS[item_key]
    if removed:
        await safe_reply(message, TEXTS["admin_take_boost_4"].format(v0=emoji, v1=esc(name), v2=esc(target_username)))
    else:
        await message.reply(TEXTS["admin_take_boost_5"].format(v0=esc(target_username), v1=esc(name)))

@dp.message(F.text.lower().startswith("!дать п "))
async def admin_give_passive(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_ITEM_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_passive_1"])
        return

    item_key = find_item_by_name(match.group(1), only_passive=True)
    if not item_key:
        await message.reply(TEXTS["admin_give_passive_2"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_passive_3"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await add_item(target.id, item_key)

    emoji, name, _, _ = ITEMS[item_key]
    await safe_reply(message, TEXTS["admin_give_passive_4"].format(v0=emoji, v1=esc(name), v2=esc(target_username)))

@dp.message(F.text.lower().startswith("!снять п "))
async def admin_take_passive(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_ITEM_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_passive_1"])
        return

    item_key = find_item_by_name(match.group(1), only_passive=True)
    if not item_key:
        await message.reply(TEXTS["admin_take_passive_2"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_take_passive_3"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    removed = await remove_item(target.id, item_key)

    emoji, name, _, _ = ITEMS[item_key]
    if removed:
        await safe_reply(message, TEXTS["admin_take_passive_4"].format(v0=emoji, v1=esc(name), v2=esc(target_username)))
    else:
        await message.reply(TEXTS["admin_take_passive_5"].format(v0=esc(target_username), v1=esc(name)))

@dp.message(F.text.lower().startswith("!дать вип"))
async def admin_give_vip(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_VIP_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_vip_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_vip_2"])
        return

    days = parse_amount(match.group(1))
    if not days or days <= 0:
        await message.reply(TEXTS["admin_give_vip_3"])
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

    await message.reply(TEXTS["admin_give_vip_4"].format(v0=days, v1=esc(target_username)))

@dp.message(F.text.lower().startswith("!снять вип"))
async def admin_take_vip(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_VIP_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_vip_1"])
        return

    target = await resolve_target(message, bool(match.group(1)))
    if not target:
        await message.reply(TEXTS["admin_take_vip_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await db_exec("UPDATE users SET vip_until = 0 WHERE user_id = ?", (target.id,))

    await message.reply(TEXTS["admin_take_vip_3"].format(v0=esc(target_username)))

@dp.message(F.text.lower().startswith("!сбросить"))
async def admin_reset(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_RESET_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_reset_1"])
        return

    target = await resolve_target(message, bool(match.group(1)))
    if not target:
        await message.reply(TEXTS["admin_reset_2"])
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

    await message.reply(TEXTS["admin_reset_3"].format(v0=esc(target_username)))

@dp.message(F.text.lower().startswith("!установить ног"))
async def admin_set_legs(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_SET_LEGS_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_set_legs_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_set_legs_2"])
        return

    amount = parse_amount(match.group(1))
    if amount is None or amount < 0:
        await message.reply(TEXTS["admin_set_legs_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    old_score = row[2]
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (amount, target.id))
    await maybe_announce_levelup(message, target_username, old_score, amount, row[3], bool(row[11]))

@dp.message(F.text.lower().startswith("!дать ноги лвл"))
async def admin_give_legs_level(message: Message):
    """Ставит игроку РОВНО указанный уровень ноги (не сырое число очков) — пересчитывает
    нужный score через level_threshold с учётом его эволюции/перерождений/ultra_rebirth."""
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_LEGS_LVL_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_legs_lvl_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_legs_lvl_2"])
        return

    level = int(match.group(1))
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    evolution_level, rebirth_count = row[3], row[15]
    ultra_rebirth = bool(row[21])
    cap = ULTRA_LEVEL_CAP if ultra_rebirth else ULTRA_REQUIRED_LEG_LEVEL

    if level < 0 or level > cap:
        await message.reply(TEXTS["admin_give_legs_lvl_3"].format(v0=cap))
        return

    old_score = row[2]
    new_score = level_threshold(level, evolution_level, rebirth_count)
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_score, target.id))
    await maybe_announce_levelup(message, target_username, old_score, new_score, evolution_level, bool(row[11]), rebirth_count, ultra_rebirth)

    await message.reply(TEXTS["admin_give_legs_lvl_4"].format(v0=level, v1=esc(target_username), v2=new_score))

    await message.reply(TEXTS["admin_set_legs_4"].format(v0=esc(target_username), v1=amount, v2=old_score))

@dp.message(F.text.lower().startswith("!установить эво"))
async def admin_set_evo(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_SET_EVO_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_set_evo_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_set_evo_2"])
        return

    amount = parse_amount(match.group(1))
    if amount is None or amount < 0:
        await message.reply(TEXTS["admin_set_evo_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    old_evo = row[3]
    await db_exec("UPDATE users SET evolution_level = ? WHERE user_id = ?", (amount, target.id))

    await message.reply(TEXTS["admin_set_evo_4"].format(v0=esc(target_username), v1=amount, v2=old_evo))

@dp.message(F.text.lower().startswith("!сброс кд"))
async def admin_reset_cd(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_RESET_CD_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_reset_cd_1"])
        return

    target = await resolve_target(message, bool(match.group(1)))
    if not target:
        await message.reply(TEXTS["admin_reset_cd_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await db_exec("UPDATE users SET last_farm = 0 WHERE user_id = ?", (target.id,))

    await message.reply(TEXTS["admin_reset_cd_3"].format(v0=esc(target_username)))

@dp.message(F.text.lower().startswith("!сброс бонус"))
async def admin_reset_bonus(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_RESET_BONUS_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_reset_bonus_1"])
        return

    target = await resolve_target(message, bool(match.group(1)))
    if not target:
        await message.reply(TEXTS["admin_reset_bonus_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await db_exec("UPDATE users SET last_bonus = 0 WHERE user_id = ?", (target.id,))

    await message.reply(TEXTS["admin_reset_bonus_3"].format(v0=esc(target_username)))

@dp.message(F.text.lower().startswith("!дать кейс"))
async def admin_give_case(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_CASE_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_case_1"])
        return

    case_num = int(match.group(1))
    count = int(match.group(2))
    case = CASES.get(case_num)
    if not case:
        await message.reply(TEXTS["admin_give_case_3"])
        return
    if count < 1 or count > 100:
        await message.reply(TEXTS["admin_give_case_4"])
        return

    target = await resolve_target(message, bool(match.group(3)))
    if not target:
        await message.reply(TEXTS["admin_give_case_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)

    won = {}
    for _ in range(count):
        item_key = roll_case_item(case_num)
        await add_item(target.id, item_key)
        won[item_key] = won.get(item_key, 0) + 1
    await db_exec("UPDATE users SET cases_opened = cases_opened + ? WHERE user_id = ?", (count, target.id))

    loot_lines = "\n".join(f"● {ITEMS[k][0]} {esc(ITEMS[k][1])} × {qty}" for k, qty in won.items())
    await safe_reply(
        message,
        TEXTS["admin_give_case_5"].format(v0=esc(target_username), v1=esc(case["name"]), v2=count, v3=loot_lines),
    )

@dp.message(F.text.regexp(r"(?i)^!дебаг\s+"))
async def admin_debug(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_DEBUG_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_debug_1"])
        return

    row = await get_user_by_username(match.group(1))
    if not row:
        await message.reply(TEXTS["admin_debug_2"])
        return

    fields = USER_COLUMNS.split(", ")
    dump = "\n".join(f"{name} = {value}" for name, value in zip(fields, row))
    await message.reply(TEXTS["admin_debug_3"].format(v0=esc(row[1]), v1=esc(dump)))

@dp.message(F.text.regexp(r"(?i)^!текст\s+"))
async def admin_show_text(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_SHOW_TEXT_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_show_text_1"])
        return

    key = match.group(1)
    if key not in TEXTS:
        await message.reply(TEXTS["admin_show_text_2"])
        return

    await message.reply(TEXTS["admin_show_text_3"].format(v0=esc(key), v1=esc(TEXTS[key])))

@dp.message(F.text.regexp(r"(?i)^!симулировать эволюция\s+"))
async def admin_simulate_evolution(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_SIMULATE_EVO_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_simulate_evo_1"])
        return

    row = await get_user_by_username(match.group(1))
    if not row:
        await message.reply(TEXTS["admin_simulate_evo_2"])
        return

    username, score, evolution_level = row[1], row[2], row[3]
    rebirth_count = row[15] if len(row) > 15 else 0
    required = level_threshold(39, evolution_level, rebirth_count)
    verdict = TEXTS["admin_simulate_evo_ok"] if score >= required else TEXTS["admin_simulate_evo_fail"].format(v0=required - score)

    await message.reply(
        TEXTS["admin_simulate_evo_3"].format(v0=esc(username), v1=score, v2=required, v3=evolution_level, v4=verdict)
    )

@dp.message(F.text.lower() == "!стата")
async def admin_stats(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)

    row = await db_query_one(
        "SELECT COUNT(*), COALESCE(SUM(score),0), COALESCE(SUM(coins),0), COALESCE(SUM(rebirth_points),0), "
        "COALESCE(SUM(cases_opened),0), SUM(CASE WHEN vip_until > ? THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN top_banned = 1 THEN 1 ELSE 0 END) FROM users",
        (int(time.time()),),
    )
    players, total_score, total_coins, total_rebirth, total_cases, vip_count, banned_count = row

    await message.reply(
        TEXTS["admin_stats_1"].format(
            v0=players, v1=total_score, v2=total_coins, v3=total_rebirth,
            v4=total_cases, v5=vip_count or 0, v6=banned_count or 0,
        )
    )

@dp.message(F.text.lower() == "!рестарт")
async def admin_restart(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    await message.reply(TEXTS["admin_restart_1"])
    await bot.session.close()
    os._exit(0)

@dp.message(F.text.regexp(r"(?i)^!ивент\s+х\d"))
async def admin_event_custom(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_EVENT_CUSTOM_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_event_custom_1"])
        return

    mult = float(match.group(1))
    minutes = int(match.group(2))
    if mult <= 0 or minutes <= 0:
        await message.reply(TEXTS["admin_event_custom_2"])
        return

    until = int(time.time()) + minutes * 60
    for key, value in (("event_active", "1"), ("event_multiplier", str(mult)), ("event_until", str(until))):
        await db_exec(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    _invalidate_event_state_cache()

    await message.reply(TEXTS["admin_event_custom_3"].format(v0=mult, v1=minutes))

@dp.message(F.text.lower().startswith("!установить очкп"))
async def admin_set_rebirth(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_SET_REBIRTH_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_set_rebirth_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_set_rebirth_2"])
        return

    amount = parse_amount(match.group(1))
    if amount is None or amount < 0:
        await message.reply(TEXTS["admin_set_rebirth_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    old_rp = row[14]
    await db_exec("UPDATE users SET rebirth_points = ? WHERE user_id = ?", (amount, target.id))

    await message.reply(TEXTS["admin_set_rebirth_4"].format(v0=esc(target_username), v1=amount, v2=old_rp))

@dp.message(F.text.regexp(r"(?i)^!обнулить экономику\s+"))
async def admin_wipe_economy(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_WIPE_ECONOMY_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_wipe_economy_1"])
        return

    row = await get_user_by_username(match.group(1))
    if not row:
        await message.reply(TEXTS["admin_wipe_economy_2"])
        return

    await db_exec(
        "UPDATE users SET score = 0, coins = 0, rebirth_points = 0 WHERE user_id = ?",
        (row[0],),
    )
    await message.reply(TEXTS["admin_wipe_economy_3"].format(v0=esc(row[1])))

@dp.message(F.text.regexp(r"(?i)^!мультипликатор ферма\s+"))
async def admin_personal_boost(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_PERSONAL_BOOST_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_personal_boost_1"])
        return

    target = await resolve_target(message, bool(match.group(3)))
    if not target:
        await message.reply(TEXTS["admin_personal_boost_2"])
        return

    mult = float(match.group(1))
    minutes = int(match.group(2))
    if mult <= 0 or minutes <= 0:
        await message.reply(TEXTS["admin_personal_boost_3"])
        return
    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)

    until = int(time.time()) + minutes * 60
    await db_exec(
        "INSERT INTO personal_boosts (user_id, multiplier, until) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET multiplier = excluded.multiplier, until = excluded.until",
        (target.id, mult, until),
    )

    await message.reply(TEXTS["admin_personal_boost_4"].format(v0=esc(target_username), v1=mult, v2=minutes))

@dp.message(F.text.regexp(r"(?i)^!дать предмет\s+"))
async def admin_give_item(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_ITEM_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_item_1"])
        return

    item_key = match.group(1)
    count = int(match.group(2))
    if item_key not in ITEMS:
        await message.reply(TEXTS["admin_give_item_3"])
        return
    if count < 1 or count > 1000:
        await message.reply(TEXTS["admin_give_item_4"])
        return

    target = await resolve_target(message, bool(match.group(3)))
    if not target:
        await message.reply(TEXTS["admin_give_item_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await add_item(target.id, item_key, count)

    emoji, name, _, _ = ITEMS[item_key]
    await message.reply(TEXTS["admin_give_item_5"].format(v0=esc(target_username), v1=emoji, v2=esc(name), v3=count))

@dp.message(F.text.regexp(r"(?i)^!дать ключ\s+"))
async def admin_give_key(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_KEY_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_key_1"])
        return

    item_key = match.group(1)
    count = int(match.group(2))
    if item_key not in ITEMS:
        await message.reply(TEXTS["admin_give_key_3"])
        return
    if count < 1 or count > 1000:
        await message.reply(TEXTS["admin_give_key_4"])
        return

    target = await resolve_target(message, bool(match.group(3)))
    if not target:
        await message.reply(TEXTS["admin_give_key_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await add_item(target.id, item_key, count)

    emoji, name, _, _ = ITEMS[item_key]
    await message.reply(TEXTS["admin_give_key_5"].format(v0=esc(target_username), v1=emoji, v2=esc(name), v3=count))

@dp.message(F.text.regexp(r"(?i)^!очистить инвентарь\s+"))
async def admin_clear_inventory(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_CLEAR_INVENTORY_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_clear_inventory_1"])
        return

    row = await get_user_by_username(match.group(1))
    if not row:
        await message.reply(TEXTS["admin_clear_inventory_2"])
        return

    await db_exec("DELETE FROM inventory WHERE user_id = ?", (row[0],))
    await db_exec("UPDATE users SET equipped_items = '' WHERE user_id = ?", (row[0],))
    await message.reply(TEXTS["admin_clear_inventory_3"].format(v0=esc(row[1])))

@dp.message(F.text.regexp(r"(?i)^!дать апгрейд\s+"))
async def admin_set_upgrade(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_SET_UPGRADE_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_set_upgrade_1"])
        return

    upgrade_key = match.group(1)
    level = int(match.group(2))
    if upgrade_key not in UPGRADES:
        await message.reply(TEXTS["admin_set_upgrade_3"])
        return
    max_level = UPGRADES[upgrade_key]["max_level"]
    if level < 0 or level > max_level:
        await message.reply(TEXTS["admin_set_upgrade_4"].format(v0=max_level))
        return

    target = await resolve_target(message, bool(match.group(3)))
    if not target:
        await message.reply(TEXTS["admin_set_upgrade_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    row = await ensure_user(target.id, target_username)
    upgrades = parse_upgrades(row[16])
    if level > 0:
        upgrades[upgrade_key] = level
    else:
        upgrades.pop(upgrade_key, None)
    await db_exec("UPDATE users SET upgrades = ? WHERE user_id = ?", (format_upgrades(upgrades), target.id))

    await message.reply(
        TEXTS["admin_set_upgrade_5"].format(v0=esc(target_username), v1=esc(UPGRADES[upgrade_key]["name"]), v2=level)
    )

@dp.message(F.text.lower().startswith("!вип навсегда"))
async def admin_vip_forever(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_VIP_FOREVER_RE.match(message.text.strip())
    target = await resolve_target(message, bool(match.group(1))) if match else None
    if not target:
        await message.reply(TEXTS["admin_vip_forever_1"])
        return

    target_username = target.username or target.first_name or "Без имени"
    row = await ensure_user(target.id, target_username)
    new_vip_until = int(time.time()) + VIP_FOREVER_SECONDS
    await db_exec("UPDATE users SET vip_until = ? WHERE user_id = ?", (new_vip_until, target.id))
    if not is_vip_active(row[12]):
        await add_item(target.id, "vip_charm")

    await message.reply(TEXTS["admin_vip_forever_2"].format(v0=esc(target_username)))

@dp.message(F.text.lower().startswith("!ультра навсегда"))
async def admin_ultra_rebirth_forever(message: Message):
    """Owner-инструмент для тестирования: выдаёт статус Ультра перерождения напрямую,
    БЕЗ сброса прогресса игрока (в отличие от реальной активации через игровую команду).
    Полезно для проверки пост-ультра контента ("тест ноги", буста) без реального гринда."""
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_ULTRA_REBIRTH_RE.match(message.text.strip())
    target = await resolve_target(message, bool(match.group(1))) if match else None
    if not target:
        await message.reply(TEXTS["admin_ultra_rebirth_1"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await db_exec("UPDATE users SET ultra_rebirth = 1 WHERE user_id = ?", (target.id,))

    await message.reply(TEXTS["admin_ultra_rebirth_2"].format(v0=esc(target_username)))

@dp.message(F.text.regexp(r"(?i)^!сброс ник\s+"))
async def admin_reset_nick(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_RESET_NICK_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_reset_nick_1"])
        return

    row = await get_user_by_username(match.group(1))
    if not row:
        await message.reply(TEXTS["admin_reset_nick_2"])
        return

    old_nick = row[19] if len(row) > 19 else None
    if not old_nick:
        await message.reply(TEXTS["admin_reset_nick_3"])
        return

    await db_exec("UPDATE users SET nickname = NULL WHERE user_id = ?", (row[0],))
    await message.reply(TEXTS["admin_reset_nick_4"].format(v0=esc(row[1]), v1=esc(old_nick)))

@dp.message(F.text.lower() == "!список вип")
async def admin_list_vip(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    now = int(time.time())
    rows = await db_query(
        "SELECT username, nickname, vip_until FROM users WHERE vip_until > ? ORDER BY vip_until DESC LIMIT 30",
        (now,),
    )
    if not rows:
        await message.reply(TEXTS["admin_list_vip_1"])
        return

    lines = []
    for username, nickname, vip_until in rows:
        left = vip_until - now
        if left > 50 * 365 * 86400:
            left_text = "навсегда"
        else:
            days = left // 86400
            left_text = f"{days} дн."
        lines.append(f"● {esc(display_name(username, nickname))} — {left_text}")

    await message.reply(TEXTS["admin_list_vip_2"].format(v0=len(rows), v1="\n".join(lines)))

@dp.message(F.text.lower() == "!список ников")
async def admin_list_nicknames(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    rows = await db_query(
        "SELECT username, nickname FROM users WHERE nickname IS NOT NULL AND nickname != '' LIMIT 50"
    )
    if not rows:
        await message.reply(TEXTS["admin_list_nicknames_1"])
        return

    lines = [f"● {esc(nickname)} (@{esc(username)})" for username, nickname in rows]
    await message.reply(TEXTS["admin_list_nicknames_2"].format(v0=len(rows), v1="\n".join(lines)))

@dp.message(F.text.regexp(r"(?i)^!найти\s+"))
async def admin_find(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_FIND_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_find_1"])
        return

    row = await get_user_by_username(match.group(1))
    if not row:
        await message.reply(TEXTS["admin_find_2"])
        return

    chat_rows = await db_query("SELECT chat_id FROM chat_members WHERE user_id = ? LIMIT 20", (row[0],))
    if not chat_rows:
        await message.reply(TEXTS["admin_find_4"])
        return

    lines = []
    for (chat_id,) in chat_rows:
        try:
            chat = await bot.get_chat(chat_id)
            title = chat.title or chat.full_name or str(chat_id)
        except Exception:
            title = f"chat_id {chat_id} (недоступен)"
        lines.append(f"● {esc(title)}")

    await message.reply(TEXTS["admin_find_3"].format(v0=esc(row[1]), v1=len(chat_rows), v2="\n".join(lines)))

@dp.message(F.text.lower().startswith("!дать всё"))
async def admin_give_all(message: Message):
    """!дать всё [себе] — выдаёт целевому игроку все существующие предметы, бустеры
    (все ключи ITEMS, без исключений) и все зелья (все ключи POTIONS) по 1 штуке каждого.
    Полезно для тестирования — например прогона «помощь бустер/предмет/зелье» по реальному
    инвентарю."""
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_ALL_RE.match(message.text.strip())
    target = await resolve_target(message, bool(match.group(1))) if match else None
    if not target:
        await message.reply(TEXTS["admin_give_all_1"])
        return

    target_username = target.username or target.first_name or "Без имени"
    row = await ensure_user(target.id, target_username)

    for item_key in ITEMS:
        await add_item(target.id, item_key, 1)

    stock = parse_potion_stock(row[26])
    for potion_key in POTIONS:
        stock[potion_key] = stock.get(potion_key, 0) + 1
    await db_exec("UPDATE users SET potion_stock = ? WHERE user_id = ?", (format_potion_stock(stock), target.id))

    await safe_reply(message, TEXTS["admin_give_all_2"].format(v0=esc(target_username), v1=len(ITEMS), v2=len(POTIONS)))

@dp.message(F.text.lower() == "!смс выкл всем")
async def admin_levelup_notify_off_all(message: Message):
    """!смс выкл всем — массово отключает показ уведомления о новом уровне (levelup_notify)
    у ВСЕХ игроков разом, одним UPDATE без WHERE (тот же паттерн, что chronos_orb_boost_loop)."""
    if not is_admin(message):
        return
    await log_admin_action(message)

    count_row = await db_query_one("SELECT COUNT(*) FROM users")
    total = count_row[0] if count_row else 0

    await db_exec("UPDATE users SET levelup_notify = 0")

    await message.reply(TEXTS["admin_levelup_notify_off_all_1"].format(v0=total))

@dp.message(F.text.lower() == "!игроки")
async def admin_list_players(message: Message):
    """!игроки — показ всех игроков (username/ник + основные показатели)."""
    if not is_admin(message):
        return
    await log_admin_action(message)
    rows = await db_query(
        "SELECT username, nickname, score, evolution_level FROM users "
        "ORDER BY evolution_level DESC, score DESC LIMIT 100"
    )
    if not rows:
        await message.reply(TEXTS["admin_players_1"])
        return

    lines = [
        f"● {esc(display_name(username, nickname))} — нога {score}, эво {evolution_level}"
        for username, nickname, score, evolution_level in rows
    ]
    await message.reply(TEXTS["admin_players_2"].format(v0=len(rows), v1="\n".join(lines)))

@dp.message(F.text.lower() == "!список чат")
async def admin_list_chats(message: Message):
    """Список всех чатов, где бот отметился (из chat_members — Telegram Bot API не даёт
    метода 'дай все чаты бота' напрямую). Титул подтягивается свежим через bot.get_chat();
    если чат недоступен (бота уже выгнали), запись пропускается, а не показывается мёртвой
    строкой — так список честно отражает чаты, где бот РЕАЛЬНО сейчас состоит."""
    if not is_admin(message):
        return
    await log_admin_action(message)

    chat_ids = await db_query("SELECT DISTINCT chat_id FROM chat_members")

    lines = []
    for (chat_id,) in chat_ids:
        try:
            chat = await bot.get_chat(chat_id)
            title = chat.title or chat.full_name or str(chat_id)
        except Exception:
            continue
        lines.append(f"● {esc(title)}")

    if not lines:
        await message.reply(TEXTS["admin_list_chats_1"])
        return

    await message.reply(TEXTS["admin_list_chats_2"].format(v0=len(lines), v1="\n".join(lines)))

@dp.message(F.text.regexp(r'(?i)^!промокод создать бейдж\s+'))
async def admin_promo_create_badge(message: Message):
    """Короткий синтаксис для выдачи бейджа промокодом (см. PROMO_BADGES):
    !промокод создать бейдж "название_бейджа" "название_промокода".
    Зарегистрирован раньше admin_promo_create и матчится первым — aiogram
    останавливается на первом сработавшем хендлере для одного сообщения."""
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = PROMO_CREATE_BADGE_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["promo_create_badge_1"])
        return

    badge_name_raw, code_raw = match.groups()
    code = code_raw.strip()

    badge_key = find_promo_badge_key(badge_name_raw)
    if not badge_key:
        await message.reply(TEXTS["promo_create_badge_2"].format(v0=esc(badge_name_raw)))
        return

    existing = await db_query_one("SELECT code FROM promocodes WHERE code = ?", (code,))
    if existing:
        await message.reply(TEXTS["promo_create_badge_3"].format(v0=esc(code)))
        return

    admin_username = message.from_user.username or message.from_user.first_name or "admin"
    await db_exec(
        "INSERT INTO promocodes (code, reward_type, reward_key, amount, activations_left, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (code, "badge", badge_key, 1, 1, admin_username, int(time.time())),
    )

    emoji, name = PROMO_BADGES[badge_key]
    await message.reply(TEXTS["promo_create_badge_4"].format(v0=esc(code), v1=emoji, v2=esc(name)))

@dp.message(F.text.regexp(r'(?i)^!промокод создать\s+(?!бейдж\s)'))
async def admin_promo_create(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = PROMO_CREATE_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["promo_create_1"])
        return

    type_raw, amount_raw, activations_raw, code_raw = match.groups()
    code = code_raw.strip()

    parsed_type = parse_promo_type(type_raw)
    if not parsed_type:
        await message.reply(TEXTS["promo_create_2"].format(v0=esc(type_raw)))
        return
    reward_type, reward_key = parsed_type

    amount = parse_amount(amount_raw)
    if not amount or amount <= 0:
        await message.reply(TEXTS["promo_create_3"])
        return

    activations = parse_amount(activations_raw)
    if not activations or activations <= 0:
        await message.reply(TEXTS["promo_create_4"])
        return

    existing = await db_query_one("SELECT code FROM promocodes WHERE code = ?", (code,))
    if existing:
        await message.reply(TEXTS["promo_create_5"].format(v0=esc(code)))
        return

    admin_username = message.from_user.username or message.from_user.first_name or "admin"
    await db_exec(
        "INSERT INTO promocodes (code, reward_type, reward_key, amount, activations_left, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (code, reward_type, reward_key, amount, activations, admin_username, int(time.time())),
    )

    if reward_type == "item":
        emoji, name, _, _ = ITEMS[reward_key]
        reward_label = f"{emoji} {esc(name)}"
    else:
        reward_label = PROMO_TYPE_LABEL[reward_type]

    await message.reply(TEXTS["promo_create_6"].format(v0=esc(code), v1=reward_label, v2=amount, v3=activations))

@dp.message(F.text.regexp(r'(?i)^!промокод удалить\s+'))
async def admin_promo_delete(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = PROMO_DELETE_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["promo_delete_1"])
        return

    code = match.group(1).strip()
    existing = await db_query_one("SELECT code FROM promocodes WHERE code = ?", (code,))
    if not existing:
        await message.reply(TEXTS["promo_delete_2"].format(v0=esc(code)))
        return

    await db_exec("DELETE FROM promocodes WHERE code = ?", (code,))
    await db_exec("DELETE FROM promocode_uses WHERE code = ?", (code,))
    await message.reply(TEXTS["promo_delete_3"].format(v0=esc(code)))

@dp.message(F.text.lower() == "!промокод список")
async def admin_promo_list(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    rows = await db_query(
        "SELECT code, reward_type, reward_key, amount, activations_left FROM promocodes ORDER BY created_at DESC LIMIT 50"
    )
    if not rows:
        await message.reply(TEXTS["promo_list_1"])
        return

    lines = []
    for code, reward_type, reward_key, amount, activations_left in rows:
        if reward_type == "item" and reward_key in ITEMS:
            emoji, name, _, _ = ITEMS[reward_key]
            reward_label = f"{emoji} {esc(name)}"
        elif reward_type == "badge" and reward_key in PROMO_BADGES:
            emoji, name = PROMO_BADGES[reward_key]
            reward_label = f"{emoji} бейдж «{esc(name)}»"
        else:
            reward_label = PROMO_TYPE_LABEL.get(reward_type, esc(reward_type))
        lines.append(f"● «{esc(code)}» — {reward_label} × {amount} (осталось активаций: {activations_left})")

    await message.reply(TEXTS["promo_list_2"].format(v0=len(rows), v1="\n".join(lines)))

@dp.message(F.text.regexp(r'(?i)^(?:промокод|промо)\s+\S+$'))
async def redeem_promo(message: Message):
    match = PROMO_REDEEM_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["promo_redeem_1"])
        return

    code = match.group(1).strip()
    promo = await db_query_one(
        "SELECT reward_type, reward_key, amount, activations_left FROM promocodes WHERE code = ?", (code,)
    )
    if not promo:
        await message.reply(TEXTS["promo_redeem_2"])
        return

    reward_type, reward_key, amount, activations_left = promo
    if activations_left <= 0:
        await message.reply(TEXTS["promo_redeem_3"].format(v0=esc(code)))
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    already_used = await db_query_one(
        "SELECT 1 FROM promocode_uses WHERE user_id = ? AND code = ?", (user_id, code)
    )
    if already_used:
        await message.reply(TEXTS["promo_redeem_4"])
        return

    await ensure_user(user_id, username)

    await db_exec(
        "UPDATE promocodes SET activations_left = activations_left - 1 "
        "WHERE code = ? AND activations_left > 0",
        (code,),
    )
    check = await db_query_one("SELECT activations_left FROM promocodes WHERE code = ?", (code,))
    if check is None:
        await message.reply(TEXTS["promo_redeem_2"])
        return
    if check[0] < activations_left:
        pass
    else:
        await message.reply(TEXTS["promo_redeem_3"].format(v0=esc(code)))
        return

    await db_exec(
        "INSERT INTO promocode_uses (user_id, code, used_at) VALUES (?, ?, ?)",
        (user_id, code, int(time.time())),
    )
    reward_label = await apply_promo_reward(user_id, reward_type, reward_key, amount)
    await message.reply(TEXTS["promo_redeem_5"].format(v0=esc(code), v1=reward_label))

@dp.message(F.text.lower() == "!логи")
async def admin_logs(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    rows = await db_query("SELECT ts, admin_username, command FROM audit_log ORDER BY id DESC LIMIT 20")
    if not rows:
        await message.reply(TEXTS["admin_logs_1"])
        return

    lines = []
    for ts, admin_username, command in rows:
        dt = datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")
        lines.append(f"● [{dt}] @{esc(admin_username)}: {esc(command)}")

    await message.reply(TEXTS["admin_logs_2"].format(v0=len(rows), v1="\n".join(lines)))

@dp.message(F.text.lower().startswith("!топ спам"))
async def admin_top_spam(message: Message):
    """!топ спам        -> топ-20 игроков по числу команд за последний час
    !топ спам 30        -> тот же топ, но за последние 30 минут

    Источник — player_action_log (пишется в ThrottleMiddleware ДО rate-limit,
    см. _log_player_action), так что здесь видно и то, что троттлинг заглушил.
    Для каждого игрока также берём минимальный интервал между двумя ЕГО
    последовательными командами за то же окно — человек физически не может
    слать команды каждые доли секунды подолгу, поэтому маленький минимальный
    интервал при большом числе команд — сигнал на бота/скрипт, а не флуд руками.
    """
    if not is_admin(message):
        return
    await log_admin_action(message)

    parts = message.text.strip().split(maxsplit=2)
    minutes = 60
    if len(parts) > 2:
        try:
            minutes = max(1, int(parts[2]))
        except ValueError:
            minutes = 60

    since = int(time.time()) - minutes * 60
    rows = await db_query(
        "SELECT user_id, username, ts FROM player_action_log WHERE ts >= ? ORDER BY user_id, ts",
        (since,),
    )
    if not rows:
        await message.reply(TEXTS["admin_top_spam_1"])
        return

    per_user = {}
    for user_id, username, ts in rows:
        entry = per_user.setdefault(user_id, {"username": username, "count": 0, "min_gap": None, "last_ts": None})
        entry["username"] = username
        entry["count"] += 1
        if entry["last_ts"] is not None:
            gap = ts - entry["last_ts"]
            if entry["min_gap"] is None or gap < entry["min_gap"]:
                entry["min_gap"] = gap
        entry["last_ts"] = ts

    ranked = sorted(per_user.items(), key=lambda kv: kv[1]["count"], reverse=True)[:20]

    leg_by_user = {}
    if ranked:
        ids = [user_id for user_id, _ in ranked]
        placeholders = ",".join("?" for _ in ids)
        leg_rows = await db_query(
            f"SELECT user_id, score, evolution_level, rebirth_count, ultra_rebirth "
            f"FROM users WHERE user_id IN ({placeholders})",
            tuple(ids),
        )
        for uid, score, evo, rebirth_count, ultra in leg_rows:
            level = get_level_index(score or 0, evo or 0, rebirth_count or 0, bool(ultra))
            emoji, name, _ = get_level_visual(level)
            leg_by_user[uid] = f"{emoji} ур.{level}" + (f" ({name})" if name else "")

    lines = []
    for user_id, info in ranked:
        gap = info["min_gap"]
        suspicious = gap is not None and gap <= PLAYER_LOG_MIN_INTERVAL + 1
        marker = " ⚠️ подозрение на бота" if suspicious else ""
        gap_text = f"{gap}с" if gap is not None else "—"
        leg_text = leg_by_user.get(user_id, "—")
        lines.append(
            f"● @{esc(info['username'])} (id {user_id}), {leg_text}: "
            f"{info['count']} команд, мин. интервал {gap_text}{marker}"
        )

    await message.reply(TEXTS["admin_top_spam_2"].format(v0=minutes, v1=len(ranked), v2="\n".join(lines)))

@dp.message(F.text.lower() == "!логи вся")
async def admin_logs_all(message: Message):
    """!логи вся — вся история audit_log без ограничения в 20 записей.
    Telegram-сообщение ограничено ~4096 символами, поэтому шлём частями."""
    if not is_admin(message):
        return
    await log_admin_action(message)
    rows = await db_query("SELECT ts, admin_username, command FROM audit_log ORDER BY id DESC")
    if not rows:
        await message.reply(TEXTS["admin_logs_all_1"])
        return

    lines = []
    for ts, admin_username, command in rows:
        dt = datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")
        lines.append(f"● [{dt}] @{esc(admin_username)}: {esc(command)}")

    total = len(rows)
    header = TEXTS["admin_logs_all_2"].format(v0=total, v1="")
    chunk_limit = 3800
    chunk_lines = []
    chunk_len = len(header)
    chunks = []
    for line in lines:
        if chunk_len + len(line) + 1 > chunk_limit and chunk_lines:
            chunks.append(chunk_lines)
            chunk_lines = []
            chunk_len = 0
        chunk_lines.append(line)
        chunk_len += len(line) + 1
    if chunk_lines:
        chunks.append(chunk_lines)

    for i, chunk in enumerate(chunks):
        if i == 0:
            await message.reply(TEXTS["admin_logs_all_2"].format(v0=total, v1="\n".join(chunk)))
        else:
            await message.answer("\n".join(chunk))

@dp.message(F.text.lower().startswith("!чистлоги"))
async def admin_clear_logs(message: Message):
    if not is_admin(message):
        return

    parts = message.text.strip().split(maxsplit=2)
    if len(parts) > 1 and parts[1].strip().lower() == "игроки":
        await _admin_clear_player_logs_impl(message, parts[2].strip().lower() if len(parts) > 2 else "")
        return

    parts = message.text.strip().split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""

    if arg in ("все", "всё", "all"):
        before_row = await db_query_one("SELECT COUNT(*) FROM audit_log")
        before = before_row[0] if before_row else 0
        await db_exec("DELETE FROM audit_log")
        await log_admin_action(message)
        await message.reply(TEXTS["admin_logs_clear_1"].format(v0=before, v1=0))
        return

    days = 7
    if arg:
        try:
            days = max(0, int(arg))
        except ValueError:
            days = 7

    cutoff = int(time.time()) - days * 86400
    before_row = await db_query_one("SELECT COUNT(*) FROM audit_log WHERE ts < ?", (cutoff,))
    before = before_row[0] if before_row else 0
    await db_exec("DELETE FROM audit_log WHERE ts < ?", (cutoff,))
    await log_admin_action(message)
    after_row = await db_query_one("SELECT COUNT(*) FROM audit_log")
    after = after_row[0] if after_row else 0
    await message.reply(TEXTS["admin_logs_clear_1"].format(v0=before, v1=after))

async def _admin_clear_player_logs_impl(message: Message, arg: str):
    if arg in ("все", "всё", "all"):
        before_row = await db_query_one("SELECT COUNT(*) FROM player_action_log")
        before = before_row[0] if before_row else 0
        await db_exec("DELETE FROM player_action_log")
        await log_admin_action(message)
        await message.reply(TEXTS["admin_logs_clear_1"].format(v0=before, v1=0))
        return

    days = 2
    if arg:
        try:
            days = max(0, int(arg))
        except ValueError:
            days = 2

    cutoff = int(time.time()) - days * 86400
    before_row = await db_query_one("SELECT COUNT(*) FROM player_action_log WHERE ts < ?", (cutoff,))
    before = before_row[0] if before_row else 0
    await db_exec("DELETE FROM player_action_log WHERE ts < ?", (cutoff,))
    await log_admin_action(message)
    after_row = await db_query_one("SELECT COUNT(*) FROM player_action_log")
    after = after_row[0] if after_row else 0
    await message.reply(TEXTS["admin_logs_clear_1"].format(v0=before, v1=after))

@dp.message(F.text.lower() == "!пинг")
async def admin_ping(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    start = time.monotonic()
    await db_query_one("SELECT 1")
    elapsed_ms = round((time.monotonic() - start) * 1000)
    await message.reply(TEXTS["admin_ping_1"].format(v0=elapsed_ms))

@dp.message(F.text.lower() == "!пинг5")
async def admin_ping5(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    samples = []
    for _ in range(5):
        start = time.monotonic()
        await db_query_one("SELECT 1")
        samples.append(round((time.monotonic() - start) * 1000))
    samples_text = ", ".join(str(s) for s in samples)
    await message.reply(
        TEXTS["admin_ping_2"].format(
            v0=samples_text, v1=min(samples), v2=round(sum(samples) / len(samples)), v3=max(samples)
        )
    )

@dp.message(F.text.lower() == "!ивент стоп")
async def admin_event_stop(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    active = await is_event_active()
    await db_exec(
        "INSERT INTO settings (key, value) VALUES ('event_active', '0') "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    )
    _invalidate_event_state_cache()
    await message.reply(TEXTS["admin_event_stop_1"] if active else TEXTS["admin_event_stop_2"])

@dp.message(F.text.lower() == "!ивент статус")
async def admin_event_status(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    active, mult = await get_event_state()
    if not active:
        await message.reply(TEXTS["admin_event_status_2"])
        return

    row = await db_query_one("SELECT value FROM settings WHERE key = 'event_until'")
    until = int(row[0]) if row and row[0] else 0
    if until:
        left = max(0, until - int(time.time()))
        m, s = divmod(left, 60)
        left_text = f"{m} мин. {s} сек."
    else:
        left_text = TEXTS["admin_event_status_forever"]

    await message.reply(TEXTS["admin_event_status_1"].format(v0=mult, v1=left_text))

