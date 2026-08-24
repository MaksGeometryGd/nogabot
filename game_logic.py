"""
game_logic.py — вспомогательная игровая логика без прямых обращений к БД:
подбор случайного предмета из кейса, поиск предмета по имени, целевого
пользователя команды, VIP-статус, отображение инвентаря в клавиатуре.
"""
import random
import time

from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from game_data import ITEMS, CASES, PASSIVE_ITEMS
from text_utils import plain_emoji

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


def is_vip_active(vip_until: int) -> bool:
    return bool(vip_until) and vip_until > int(time.time())

def _percent_label(item_key: str, percent: int) -> str:
    """Подпись буста для кнопок/списков. chronos_orb — спец-случай: у него рандомный
    буст 10-400% (пересчитывается раз в 5 мин), фикс. число тут вводило бы в заблуждение."""
    if item_key == "chronos_orb":
        return "+10-400%, рандом"
    return f"+{percent}%"

def inventory_keyboard(inventory_rows, active_item: str, user_id: int) -> InlineKeyboardMarkup:
    rows = []
    for item_key, qty in inventory_rows:
        if item_key in PASSIVE_ITEMS:
            continue
        emoji, name, percent, _ = ITEMS[item_key]
        is_equipped = active_item == item_key
        mark = " ✅" if is_equipped else ""
        rows.append([InlineKeyboardButton(
            text=f"{name} {plain_emoji(emoji)} ({_percent_label(item_key, percent)}) x{qty}{mark}",
            callback_data=f"equip:{user_id}:{item_key}",
            style="success" if is_equipped else None,
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def resolve_target(message: Message, to_self: bool):
    if to_self:
        return message.from_user
    if message.reply_to_message:
        return message.reply_to_message.from_user
    return None
