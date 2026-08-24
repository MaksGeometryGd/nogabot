"""
text_utils.py — нормализация текста команд (алиасы, fuzzy-подсказки),
эскейпинг HTML, безопасные reply/edit_text обёртки для aiogram.
"""
import re

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery

from command_patterns import FIXED_COMMANDS, PREFIX_COMMANDS, _AMOUNT_TOKEN_RE

def is_command_text(text: str) -> bool:
    t = text.lower()
    if t in FIXED_COMMANDS:
        return True
    return any(t.startswith(p) for p in PREFIX_COMMANDS)

_TOP_WORDS = ["топ", "топчик", "ладдер", "лидеры", "лиддеры", "рейтинг", "top", "ladder", "lider", "liders", "leaders", "rating"]
_LEG_WORDS = ["ног", "ноги", "ногой", "leg", "legs", "foot", "feet"]
_COIN_WORDS = ["коин", "коины", "коинов", "монета", "монеты", "монет", "coin", "coins", "money", "валюта"]
_EVO_WORDS = ["эво", "эволюция", "эволюции", "эволюционировать", "evolution", "evolutions", "evo"]
_BALANCE_WORDS = ["баланс", "бал", "кошелек", "кошелёк", "деньги", "bal", "balance", "cash", "счет", "счёт"]
_REBIRTH_WORDS = ["перерождение", "перерождения", "ребёрт", "реберт", "ребёрты", "ребирты", "рб", "rebirth", "rb", "rebith"]
_CASE_WORDS = ["кейс", "сундук", "коробка", "case", "box"]
_CASES_WORDS = ["кейсы", "сундуки", "коробки", "cases", "boxes"]
_VIP_WORDS = ["вип", "vip", "випка", "premium", "премиум"]
_EXCHANGE_WORDS = ["обменять", "обмен", "обменник", "свап", "swap", "exchange"]

ALIAS_PHRASES = {}

def _register_phrases(canon: str, words):
    for w in words:
        ALIAS_PHRASES[w.lower()] = canon

_register_phrases("вип", _VIP_WORDS)
_register_phrases("баланс", _BALANCE_WORDS)
_register_phrases("перерождение", _REBIRTH_WORDS)
_register_phrases("эволюция", _EVO_WORDS)
_register_phrases("кейс", _CASE_WORDS)
_register_phrases("кейсы", _CASES_WORDS)
ALIAS_PHRASES["моя ношка"] = "моя нога"
ALIAS_PHRASES["моя ножка"] = "моя нога"
ALIAS_PHRASES["моя ноги"] = "моя нога"

for _top in _TOP_WORDS:
    for _leg in _LEG_WORDS:
        ALIAS_PHRASES[f"{_top} {_leg}"] = "топ ног"
        ALIAS_PHRASES[f"гл {_top} {_leg}"] = "гл топ ног"
        ALIAS_PHRASES[f"{_top} {_leg} вся"] = "топ ноги вся"
    for _coin in _COIN_WORDS:
        ALIAS_PHRASES[f"{_top} {_coin}"] = "топ коин"
        ALIAS_PHRASES[f"гл {_top} {_coin}"] = "гл топ коин"
        ALIAS_PHRASES[f"{_top} {_coin} вся"] = "топ коин вся"
    for _evo in _EVO_WORDS:
        ALIAS_PHRASES[f"{_top} {_evo}"] = "топ эво"
        ALIAS_PHRASES[f"гл {_top} {_evo}"] = "гл топ эво"
        ALIAS_PHRASES[f"{_top} {_evo} вся"] = "топ эво вся"
    for _rb in _REBIRTH_WORDS:
        ALIAS_PHRASES[f"{_top} {_rb}"] = "топ очкп"
        ALIAS_PHRASES[f"гл {_top} {_rb}"] = "гл топ очкп"
        ALIAS_PHRASES[f"{_top} {_rb} вся"] = "топ очкп вся"
    ALIAS_PHRASES[f"{_top} вся"] = "топ вся"
ALIAS_PHRASES.pop("топ топ", None)

def normalize_alias_text(text: str) -> str:
    """Заменяет известную фразу-алиас на канонический текст команды. Не трогает команды
    с параметрами (числа, названия предметов, юзернеймы) — под них есть отдельная токенная
    замена ниже (normalize_alias_prefix), не полнофразовая."""
    if not text:
        return text
    stripped = text.strip()
    if not stripped:
        return text
    lowered = stripped.lower()
    return ALIAS_PHRASES.get(lowered, text)

_PARAM_TERM_TO_CANON = {}
for _w in _LEG_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "ног"
for _w in _COIN_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "коин"
for _w in _EVO_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "эво"
for _w in _REBIRTH_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "очкп"
for _w in _EXCHANGE_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "обменять"
for _w in _CASE_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "кейс"

_PARAM_PROTECTED = {"б", "п"}

_CASE_WORDS_SET = {w.lower() for w in _CASE_WORDS}

def normalize_case_number(text: str) -> str:
    """'сундук 2' / 'box 2' -> 'кейс 2'. Первое слово само является термином кейса,
    число (аргумент) не трогаем."""
    if not text:
        return text
    stripped = text.strip()
    if not stripped:
        return text
    parts = stripped.split(" ", 1)
    if len(parts) != 2:
        return text
    first, rest = parts[0].lower(), parts[1]
    if first in _CASE_WORDS_SET and first != "кейс" and rest.strip().isdigit():
        return "кейс " + rest
    return text

def normalize_alias_prefix(text: str) -> str:
    """Для команд вида '<преф> <термин> <аргументы...>' заменяет только термин сразу после
    известного префикса (!дать/!снять/дать/продать/обменять/кейс), не трогая аргументы."""
    if not text:
        return text
    stripped = text.strip()
    if not stripped:
        return text

    lowered = stripped.lower()
    known_prefixes = ("!дать ", "!снять ", "дать ")
    matched_prefix = None
    for p in known_prefixes:
        if lowered.startswith(p):
            matched_prefix = p
            break
    if matched_prefix is None:
        return text

    original_prefix = stripped[:len(matched_prefix)]
    rest = stripped[len(matched_prefix):]
    if not rest:
        return text

    rest_words = rest.split(" ", 1)
    term = rest_words[0]
    tail = rest_words[1] if len(rest_words) > 1 else ""
    lterm = term.lower()

    if lterm in _PARAM_PROTECTED:
        return text
    if lterm not in _PARAM_TERM_TO_CANON:
        return text

    canon_term = _PARAM_TERM_TO_CANON[lterm]
    if matched_prefix == "!снять " and canon_term == "ног":
        canon_term = "ноги"

    if canon_term == lterm:
        return text

    new_text = original_prefix + canon_term + (" " + tail if tail else "")
    return new_text

def normalize_exchange_suffix(text: str) -> str:
    """'обменять 10 монет' / 'обменять 10 coin' -> 'обменять 10 коин'. Не трогает 'обменять 10'
    (старая команда очки->монеты, без термина в хвосте)."""
    if not text:
        return text
    stripped = text.strip()
    lowered = stripped.lower()
    if not lowered.startswith("обменять "):
        return text
    rest = stripped[len("обменять "):].strip()
    if not rest:
        return text
    parts = rest.split(" ", 1)
    if len(parts) != 2:
        return text
    amount_word, term = parts[0], parts[1].strip()
    if not _AMOUNT_TOKEN_RE.match(amount_word):
        return text
    lterm = term.lower()
    if lterm not in _PARAM_TERM_TO_CANON:
        return text
    canon_term = _PARAM_TERM_TO_CANON[lterm]
    if canon_term != "коин" or canon_term == lterm:
        return text
    return f"обменять {amount_word} {canon_term}"

_FUZZY_CANDIDATES = None
_FUZZY_MAX_DIST = 1
_FUZZY_MIN_LEN = 4

def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]

def _get_fuzzy_candidates():
    global _FUZZY_CANDIDATES
    if _FUZZY_CANDIDATES is None:
        _FUZZY_CANDIDATES = sorted(set(FIXED_COMMANDS) | set(ALIAS_PHRASES.keys()))
    return _FUZZY_CANDIDATES

def normalize_alias_fuzzy(text: str) -> str:
    if not text:
        return text
    stripped = text.strip()
    if not stripped or " " in stripped:
        return text
    lowered = stripped.lower()
    if lowered in FIXED_COMMANDS or lowered in ALIAS_PHRASES:
        return text
    if len(lowered) < _FUZZY_MIN_LEN:
        return text
    best_word = None
    best_dist = _FUZZY_MAX_DIST + 1
    for cand in _get_fuzzy_candidates():
        if " " in cand:
            continue
        if abs(len(cand) - len(lowered)) > _FUZZY_MAX_DIST:
            continue
        d = _levenshtein(lowered, cand)
        if d < best_dist:
            best_dist = d
            best_word = cand
            if d == 0:
                break
    if best_word is None or best_dist > _FUZZY_MAX_DIST:
        return text
    canon = ALIAS_PHRASES.get(best_word, best_word)
    return canon

def apply_command_aliases(text: str) -> str:
    """Единая точка входа: применяет все виды алиасинга по порядку. Возвращает исходный текст,
    если ни один нормализатор не нашёл, что менять (в т.ч. для обычных сообщений с ногами 🦵/🦿 —
    там нет алиасов, и текст останется как есть)."""
    if not text:
        return text
    if text != text.strip():
        stripped_lower = text.strip().lower()
        if stripped_lower in FIXED_COMMANDS or stripped_lower in ALIAS_PHRASES:
            text = text.strip()
    result = normalize_alias_text(text)
    if result != text:
        return result
    result = normalize_case_number(text)
    if result != text:
        return result
    result = normalize_exchange_suffix(text)
    if result != text:
        return result
    result = normalize_alias_prefix(text)
    if result != text:
        return result
    result = normalize_alias_fuzzy(text)
    return result

def esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def parse_amount(text: str):
    m = re.match(r"^(\d+(?:\.\d+)?)(к{0,4})$", text.strip().lower())
    if not m:
        return None
    number = float(m.group(1))
    k_count = len(m.group(2))
    return round(number * (1000 ** k_count))

TG_EMOJI_RE = re.compile(r"<tg-emoji[^>]*>(.*?)</tg-emoji>")

def plain_emoji(emoji_html: str) -> str:
    m = TG_EMOJI_RE.match(emoji_html or "")
    return m.group(1) if m else (emoji_html or "")

def strip_premium_emoji(text: str) -> str:
    """Убирает все <tg-emoji> обёртки из готового текста, оставляя фолбэк-символы."""
    return TG_EMOJI_RE.sub(lambda m: m.group(1), text or "")

async def safe_reply(message: Message, text: str, reply_markup=None):
    """Как message.reply(), но если Telegram отклонил сообщение из-за невалидного
    emoji-id в premium-эмодзи (битый/непризнанный custom_emoji_id) — повторяет
    отправку с обычными эмодзи вместо того, чтобы command тихо "не открывался"."""
    try:
        return await message.reply(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        return await message.reply(strip_premium_emoji(text), reply_markup=reply_markup)

async def safe_edit_text(callback: CallbackQuery, text: str, reply_markup=None):
    """Как callback.message.edit_text(), но не роняет хендлер, если Telegram отклонил
    правку. Это критично для инлайн-кнопок: если edit_text бросает исключение ДО того,
    как хендлер успел вызвать callback.answer(), Telegram держит кнопку в состоянии
    "часики" до собственного таймаута — именно это ощущается как "не нажимается"/
    "нажимается криво". Ловим и гасим самые частые причины:
    - "message is not modified" — юзер дважды подряд нажал одну и ту же кнопку
      (текст/клавиатура не изменились); это не ошибка, просто нечего обновлять.
    - "message to edit not found" / "query is too old" — сообщение удалено или
      кнопка нажата на старом сообщении после рестарта бота.
    - невалидный premium emoji-id — как и раньше, повторяем без премиум-обёртки.
    """
    try:
        return await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return None
        if "message to edit not found" in err or "query is too old" in err or "message can't be edited" in err:
            return None
        try:
            return await callback.message.edit_text(strip_premium_emoji(text), reply_markup=reply_markup)
        except TelegramBadRequest:
            return None

