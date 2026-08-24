"""
command_patterns.py — регулярные выражения и наборы текстовых команд,
используемые для парсинга сообщений (админ-команды, обмены, алиасы и т.д.).
"""
import re

AMOUNT = r"(\d+(?:\.\d+)?к{0,4})"
_AMOUNT_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?к{0,4}$", re.IGNORECASE)

ADMIN_GIVE_LEGS_RE = re.compile(rf"^!дать ног {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_LEGS_RE = re.compile(rf"^!снять ноги (?:{AMOUNT}|все)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_EVO_RE = re.compile(rf"^!дать эво {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_EVO_RE = re.compile(rf"^!снять эво (?:{AMOUNT}|все)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_COIN_RE = re.compile(rf"^!дать коин {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_COIN_RE = re.compile(rf"^!снять коин (?:{AMOUNT}|все)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_BOOST_RE = re.compile(r"^!дать б (.+?)(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_BOOST_RE = re.compile(r"^!снять б (.+?)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_ITEM_RE = re.compile(r"^!дать п (.+?)(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_ITEM_RE = re.compile(r"^!снять п (.+?)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_VIP_RE = re.compile(rf"^!дать вип {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_VIP_RE = re.compile(r"^!снять вип(\s+себе)?$", re.IGNORECASE)
ADMIN_RESET_RE = re.compile(r"^!сбросить(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_REBIRTH_RE = re.compile(rf"^!дать очкп {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_REBIRTH_RE = re.compile(rf"^!снять очкп (?:{AMOUNT}|все)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_CRAFT_RE = re.compile(rf"^!дать (?:крафт|очкк) {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_CRAFT_RE = re.compile(rf"^!снять (?:крафт|очкк) (?:{AMOUNT}|все)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_LEGS_LVL_RE = re.compile(r"^!дать ноги лвл(\d+)(\s+себе)?$", re.IGNORECASE)

PEER_GIVE_LEGS_RE = re.compile(rf"^дать ног {AMOUNT}$", re.IGNORECASE)
PEER_GIVE_COIN_RE = re.compile(rf"^дать коин {AMOUNT}$", re.IGNORECASE)

EXCHANGE_RE = re.compile(rf"^обменять {AMOUNT}$", re.IGNORECASE)
REVERSE_EXCHANGE_RE = re.compile(rf"^обменять {AMOUNT} коин$", re.IGNORECASE)
CRAFT_EXCHANGE_RE = re.compile(rf"^обменять {AMOUNT} (?:крафт|очкк)$", re.IGNORECASE)
CRAFT_EXCHANGE_TO_RE = re.compile(rf"^обменять (?:крафт|очкк) {AMOUNT}$", re.IGNORECASE)
CASE_NUM_RE = re.compile(r"^кейс (\d+)$", re.IGNORECASE)
INFO_RE = re.compile(r"^инфо\s+@?(\w+)$", re.IGNORECASE)
NICK_SET_RE = re.compile(r"^\+ник\s+(.+)$", re.IGNORECASE)
NICK_CLEAR_RE = re.compile(r"^-ник$", re.IGNORECASE)
ADMIN_SET_LEGS_RE = re.compile(rf"^!установить ног {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_SET_EVO_RE = re.compile(rf"^!установить эво {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_RESET_CD_RE = re.compile(r"^!сброс кд(\s+себе)?$", re.IGNORECASE)
ADMIN_RESET_BONUS_RE = re.compile(r"^!сброс бонус(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_CASE_RE = re.compile(r"^!дать кейс\s+(\d+)\s+(\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_DEBUG_RE = re.compile(r"^!дебаг\s+@?(\w+)$", re.IGNORECASE)
ADMIN_SHOW_TEXT_RE = re.compile(r"^!текст\s+(\S+)$", re.IGNORECASE)
ADMIN_SIMULATE_EVO_RE = re.compile(r"^!симулировать эволюция\s+@?(\w+)$", re.IGNORECASE)
ADMIN_EVENT_CUSTOM_RE = re.compile(r"^!ивент\s+х(\d+(?:\.\d+)?)\s+(\d+)$", re.IGNORECASE)

ADMIN_SET_REBIRTH_RE = re.compile(rf"^!установить очкп {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_WIPE_ECONOMY_RE = re.compile(r"^!обнулить экономику\s+@?(\w+)$", re.IGNORECASE)
ADMIN_PERSONAL_BOOST_RE = re.compile(r"^!мультипликатор ферма\s+(\d+(?:\.\d+)?)\s+(\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_ITEM_RE = re.compile(r"^!дать предмет\s+(\S+)\s+(\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_KEY_RE = re.compile(r"^!дать ключ\s+(\S+)\s+(\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_CLEAR_INVENTORY_RE = re.compile(r"^!очистить инвентарь\s+@?(\w+)$", re.IGNORECASE)
ADMIN_SET_UPGRADE_RE = re.compile(r"^!дать апгрейд\s+(\S+)\s+(\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_VIP_FOREVER_RE = re.compile(r"^!вип навсегда(\s+себе)?$", re.IGNORECASE)
ADMIN_ULTRA_REBIRTH_RE = re.compile(r"^!ультра навсегда(\s+себе)?$", re.IGNORECASE)
ADMIN_RESET_NICK_RE = re.compile(r"^!сброс ник\s+@?(\w+)$", re.IGNORECASE)
ADMIN_FIND_RE = re.compile(r"^!найти\s+@?(\w+)$", re.IGNORECASE)
ADMIN_GIVE_ALL_RE = re.compile(r"^!дать всё(\s+себе)?$", re.IGNORECASE)
ADMIN_LEVELUP_NOTIFY_OFF_ALL_RE = re.compile(r"^!смс выкл всем$", re.IGNORECASE)

PROMO_CREATE_RE = re.compile(
    r'^!промокод создать\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"$', re.IGNORECASE
)
PROMO_CREATE_BADGE_RE = re.compile(
    r'^!промокод создать бейдж\s+"([^"]+)"\s+"([^"]+)"$', re.IGNORECASE
)
PROMO_DELETE_RE = re.compile(r'^!промокод удалить\s+"([^"]+)"$', re.IGNORECASE)
PROMO_LIST_RE = re.compile(r'^!промокод список$', re.IGNORECASE)
PROMO_REDEEM_RE = re.compile(r'^(?:промокод|промо)\s+(\S+)$', re.IGNORECASE)

NEWS_PREFIX = "!новость "

FIXED_COMMANDS = {
    "моя нога", "топ ног", "гл топ ног", "топ эво", "гл топ эво", "топ коин", "гл топ коин",
    "ферма", "фарма", "инвентарь", "эволюция", "кейс", "кейсы", "бонус",
    "смс выкл", "смс вкл", "вип", "!ивент ноги", "бейджи",
    "перерождение", "апгрейд", "прокачка", "апг", "престиж", "баланс", "топ очкп", "гл топ очкп",
    "топ ноги вся", "топ коин вся", "топ эво вся", "топ очкп вся", "топ вся", "гл топ", "крафты", "крафт",
    "мои предметы", "предметы", "мои бустеры", "бустеры", "мой инвентарь", "-ник",
    "мои зелья", "зелья",
    "!список вип", "!список ников", "!список чат", "!логи", "!логи вся", "!пинг", "!ивент стоп", "!ивент статус",
    "!игроки",
    "ультра перерождение", "ультра перерождение подтверждаю",
    "авто эво вкл", "авто эво выкл", "авто эволюция вкл", "авто эволюция выкл",
    "авто перерождение вкл", "авто перерождение выкл", "авто рб вкл", "авто рб выкл",
    "авто ребёрт вкл", "авто ребёрт выкл", "авто реберт вкл", "авто реберт выкл",
    "авто продажа вкл", "авто продажа выкл", "авто продажа настройка", "авто продажа конфиг", "авто продажа настройки",
    "!смс выкл всем",
}
PREFIX_COMMANDS = (
    "обменять ", "!дать ног", "!снять ноги", "!дать эво", "!снять эво",
    "!дать коин", "!снять коин", "!дать б", "!снять б", "!дать п", "!снять п", "!дать вип", "!снять вип", "!сбросить",
    "передать ", "дать ", "кейс ", NEWS_PREFIX, "инфо ", "продать",
    "!дать очкп", "!снять очкп", "!дать крафт", "открыть кейс", "осмотреть кейс", "осмотр кейс", "крафты ", "крафт ", "уничтожение",
    "+ник ", "!установить ног", "!установить эво",
    "!сброс кд", "!сброс бонус", "!дать кейс", "!дебаг ", "!текст ", "!симулировать эволюция", "!ивент х",
    "!установить очкп", "!обнулить экономику", "!мультипликатор ферма", "!дать предмет",
    "!очистить инвентарь", "!дать апгрейд", "!вип навсегда", "!сброс ник", "!найти ", "!ультра навсегда",
    "вип открыть кейс", "бустеры поиск ", "!дать ключ", "!дать всё",
)

