"""
handlers_help.py — команды помощи: баланс игрока и справка по бейджам,
бустерам, предметам, зельям и списку команд бота.
"""
from aiogram import F
from aiogram.types import Message
import re

from premium_emoji import PREMIUM_VIP_BADGE
from config import TEXTS
from game_data import (
    HELP_BOOSTER_KEYS, HELP_ITEM_KEYS, ITEMS, POTIONS,
    find_item_key_by_name, format_help_booster_text, format_help_item_text,
)
from text_utils import esc
from state import dp
from economy import HELP_BADGES, ensure_user, find_help_badge_key
from game_logic import is_vip_active
from handlers_inventory import find_potion_key_by_name, format_help_potion_text

@dp.message(F.text.lower() == "баланс")
async def show_balance(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, coins = row[2], row[5]
    vip_until = row[12]
    rebirth_points, rebirth_count = row[14], row[15]
    craft_points = row[32]
    vip_active = is_vip_active(vip_until)

    vip_line = f"{PREMIUM_VIP_BADGE} VIP активен" if vip_active else "VIP не активен"

    await message.reply(
        TEXTS["show_balance_1"].format(
            v0=score, v1=coins, v2=rebirth_points, v3=rebirth_count, v4=vip_line, v5=craft_points
        )
    )

HELP_SECTION_ALIASES = {
    "бейдж": "бейдж", "бейджи": "бейдж", "значок": "бейдж", "значки": "бейдж",
    "бустер": "бустер", "бустеры": "бустер",
    "предмет": "предмет", "предметы": "предмет",
    "зелье": "зелье", "зелья": "зелье", "зелий": "зелье",
    "команда": "команда", "команды": "команда",
}

# Справочник для «помощь команда <название>»: ключ -> (эмодзи, алиасы команды, описание).
# Первый алиас — «каноничное» отображаемое имя команды.
HELP_COMMANDS = {
    "farm": ("🦵", ["ферма", "фарма"],
             "Основная команда добычи очков ноги — жми регулярно (или отправляй 🦵/🦿), копится опыт для эволюций и перерождений."),
    "bonus": ("🎁", ["бонус"],
              "Ежедневная награда очками ноги — стрик за подряд идущие дни. На 5-й день серии дополнительно даёт Дневной амулет."),
    "upgrade": ("⬆️", ["апгрейд", "прокачка", "апг"],
                "Прокачка постоянных улучшений за очки перерождения/крафта: лимиты, скорость варки зелий, слоты бустеров и т.д."),
    "craft": ("🛠", ["крафт", "крафты"],
              "Меню крафта — соединяй предметы/бустеры по рецептам и получай более сильные вещи (вплоть до Эссенции Бога)."),
    "case": ("🎰", ["кейс", "кейсы"],
             "Открытие кейсов за монеты — выпадают случайные предметы и бустеры из пула конкретного кейса."),
    "evolution": ("🧬", ["эволюция"],
                  "Переход на новый уровень эволюции при достижении нужного количества очков ноги — открывает новые возможности."),
    "prestige": ("🌟", ["престиж"],
                 "Система престижа — сброс части прогресса ради постоянных бонусов более высокого порядка."),
    "rebirth": ("🉑", ["перерождение"],
                "Сбрасывает ногу и эволюцию, взамен даёт очки перерождения — их тратят на апгрейды и крафт уникальных бустеров."),
    "ultra_rebirth": ("💫", ["ультра перерождение"],
                       "Разовый необратимый прыжок за грань обычного мира: обнуляет ногу, эволюцию и перерождения, "
                       "но взамен открывает второй, ULTRA-мир уровней (потолок улетает с 20001 в астрономические дали), "
                       "даёт постоянный буст добычи и очки престижа (отдельная валюта для престиж-апгрейдов). "
                       "Условия: эволюция 50+, уровень ноги 20001+, 5+ перерождений, а также Монета Пробуждения и Хвост Джевила в инвентаре."),
    "exchange": ("💱", ["обменять"],
                 "Обменивает очки ноги на монеты по фиксированному курсу: «обменять <число>»."),
    "inventory": ("🎒", ["инвентарь", "мой инвентарь"],
                  "Общее меню инвентаря — оттуда переходишь в разделы Бустеры/Предметы/Зелья."),
    "boosters": ("🧪", ["бустеры", "мои бустеры"],
                 "Список твоих бустеров с возможностью экипировать/снять прямо из меню."),
    "items": ("📦", ["предметы", "мои предметы"],
              "Список твоих обычных предметов (сырьё для крафта, коллекционные вещи)."),
    "potions": ("⚗️", ["зелья", "мои зелья"],
                "Меню зелий — варка в котле, забор готового и использование, все кнопками."),
    "give": ("🤝", ["дать", "передать"],
             "Передать другому игроку (ответом на его сообщение) монеты, очки ноги или предмет из своего инвентаря: «дать 100 коин», «дать эссенция дружбы»."),
    "sell": ("💰", ["продать"],
             "Продажа бустеров/предметов из инвентаря за монеты по фиксированной цене: «продать б <название>» / «продать п <название>»."),
    "destroy": ("🗑", ["уничтожение"],
                "Безвозвратно уничтожает бустер/предмет из инвентаря (без монет взамен) — полезно для нетоварных вещей: «уничтожение б/п <название>»."),
    "balance": ("💳", ["баланс"],
                "Показывает текущий баланс: очки ноги, монеты, очки перерождения/крафта и статус VIP."),
    "vip": ("💎", ["вип"],
            "Информация о VIP-статусе и его покупке — постоянный сильный бустер и доступ к особым фичам."),
    "badges_toggle": ("🏷", ["бейджи"],
                       "Меню управления своими бейджами — какие показывать рядом с ником в топах."),
    "top": ("🏆", ["топ ног", "топ эво", "топ коин", "топ очкп"],
            "Топы игроков по разным метрикам (ноги/эволюция/монеты/очки перерождения), в своём чате или глобально («гл топ ...»)."),
    "info": ("ℹ️", ["инфо"],
             "Показывает игровую карточку другого игрока по юзернейму: «инфо @ник»."),
    "promo": ("🎟", ["промокод", "промо"],
              "Активирует промокод и выдаёт награду, если код существует и ещё не использован тобой: «промокод <код>»."),
    "nick": ("✏️", ["+ник", "-ник"],
             "Устанавливает или сбрасывает отображаемый игровой ник: «+ник <текст>» / «-ник»."),
    "help": ("❓", ["помощь"],
             "Эта самая справка — «помощь бустер/предмет/зелье/бейдж/команда <название>»."),
}

def find_help_command_key(query: str):
    """Ищет ключ HELP_COMMANDS по названию/алиасу команды. Сначала точное совпадение,
    иначе — по вхождению подстроки в любой алиас. Возвращает (key, None) при однозначном
    совпадении, (None, [варианты]) при неоднозначности, (None, []) если не найдено."""
    q = (query or "").strip().lower()
    if not q:
        return None, []
    for key, (_, aliases, _) in HELP_COMMANDS.items():
        if q in (a.lower() for a in aliases):
            return key, None
    matches = [key for key, (_, aliases, _) in HELP_COMMANDS.items() if any(q in a.lower() for a in aliases)]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        matches.sort(key=lambda k: HELP_COMMANDS[k][1][0])
        return None, matches
    return None, []

@dp.message(F.text.lower() == "помощь")
async def help_root(message: Message):
    await message.reply(TEXTS["help_root_1"])

@dp.message(F.text.regexp(r"(?i)^помощь\s+(\S+)(?:\s+(.+))?$"))
async def help_dispatch(message: Message):
    match = re.match(r"(?i)^помощь\s+(\S+)(?:\s+(.+))?$", message.text.strip())
    raw_section = match.group(1).strip().lower()
    query = (match.group(2) or "").strip()

    section = HELP_SECTION_ALIASES.get(raw_section)
    if not section:
        await message.reply(TEXTS["help_unknown_section_1"].format(v0=esc(match.group(1))))
        return

    if section == "бейдж":
        await help_badge(message, query)
        return

    if section == "бустер":
        await help_booster(message, query)
        return

    if section == "предмет":
        await help_item(message, query)
        return

    if section == "зелье":
        await help_potion(message, query)
        return

    if section == "команда":
        await help_command(message, query)
        return

    await message.reply(TEXTS["help_unknown_section_1"].format(v0=esc(raw_section)))

async def help_badge(message: Message, query: str):
    if not query:
        await message.reply(TEXTS["help_badge_general_1"])
        return

    key, matches = find_help_badge_key(query)
    if key:
        emoji, aliases, desc = HELP_BADGES[key]
        await message.reply(f"🏷 <b>{emoji} {esc(aliases[0].capitalize())}</b>\n{desc}")
        return

    if matches:
        options = "\n".join(f"• {HELP_BADGES[m][1][0]}" for m in matches)
        await message.reply(TEXTS["help_badge_ambiguous_1"].format(v0=esc(query), v1=options))
        return

    available = ", ".join(aliases[0] for _, aliases, _ in HELP_BADGES.values())
    await message.reply(TEXTS["help_badge_not_found_1"].format(v0=esc(query), v1=esc(available)))

async def help_booster(message: Message, query: str):
    if not query:
        await message.reply(TEXTS["help_booster_general_1"])
        return

    key, matches = find_item_key_by_name(query, HELP_BOOSTER_KEYS)
    if key:
        emoji, name, _, _ = ITEMS[key]
        await message.reply(TEXTS["help_booster_info_1"].format(v0=emoji, v1=esc(name), v2=format_help_booster_text(key)))
        return

    if matches:
        options = "\n".join(f"• {ITEMS[m][1]}" for m in matches)
        await message.reply(TEXTS["help_booster_ambiguous_1"].format(v0=esc(query), v1=options))
        return

    await message.reply(TEXTS["help_booster_not_found_1"].format(v0=esc(query)))

async def help_item(message: Message, query: str):
    if not query:
        await message.reply(TEXTS["help_item_general_1"])
        return

    key, matches = find_item_key_by_name(query, HELP_ITEM_KEYS)
    if key:
        emoji, name, _, _ = ITEMS[key]
        await message.reply(TEXTS["help_item_info_1"].format(v0=emoji, v1=esc(name), v2=format_help_item_text(key)))
        return

    if matches:
        options = "\n".join(f"• {ITEMS[m][1]}" for m in matches)
        await message.reply(TEXTS["help_item_ambiguous_1"].format(v0=esc(query), v1=options))
        return

    await message.reply(TEXTS["help_item_not_found_1"].format(v0=esc(query)))

async def help_potion(message: Message, query: str):
    if not query:
        await message.reply(TEXTS["help_potion_general_1"])
        return

    key, matches = find_potion_key_by_name(query)
    if key:
        cfg = POTIONS[key]
        await message.reply(TEXTS["help_potion_info_1"].format(v0=cfg["emoji"], v1=esc(cfg["name"]), v2=format_help_potion_text(key)))
        return

    if matches:
        options = "\n".join(f"• {POTIONS[m]['name']}" for m in matches)
        await message.reply(TEXTS["help_potion_ambiguous_1"].format(v0=esc(query), v1=options))
        return

    await message.reply(TEXTS["help_potion_not_found_1"].format(v0=esc(query)))

async def help_command(message: Message, query: str):
    if not query:
        await message.reply(TEXTS["help_command_general_1"])
        return

    key, matches = find_help_command_key(query)
    if key:
        emoji, aliases, desc = HELP_COMMANDS[key]
        await message.reply(TEXTS["help_command_info_1"].format(v0=emoji, v1=esc(aliases[0]), v2=desc))
        return

    if matches:
        options = "\n".join(f"• {HELP_COMMANDS[m][1][0]}" for m in matches)
        await message.reply(TEXTS["help_command_ambiguous_1"].format(v0=esc(query), v1=options))
        return

    available = ", ".join(aliases[0] for _, aliases, _ in HELP_COMMANDS.values())
    await message.reply(TEXTS["help_command_not_found_1"].format(v0=esc(query), v1=esc(available)))

