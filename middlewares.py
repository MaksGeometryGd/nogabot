"""
middlewares.py — aiogram middleware: нормализация алиасов команд,
блокировка личных сообщений (кроме админа), учёт участия в чатах,
троттлинг текстовых команд и callback-кнопок, защита от устаревших
callback_data, глобальный обработчик ошибок.
"""
import asyncio
import time

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Message, CallbackQuery, ErrorEvent

from config import ADMIN_USERNAME
from state import dp
from text_utils import apply_command_aliases, is_command_text
from economy import _log_player_action, track_membership

def get_chat(event):
    if isinstance(event, Message):
        return event.chat
    if isinstance(event, CallbackQuery) and event.message:
        return event.message.chat
    return None

_leg_farm_last: dict = {}

class AliasNormalizeMiddleware(BaseMiddleware):
    """Переписывает message.text на канонический вид команды ДО того, как текст попадёт
    в остальные middleware/хендлеры (is_command_text, ThrottleMiddleware, сами @dp.message)."""
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.text:
            new_text = apply_command_aliases(event.text)
            if new_text != event.text:
                event = event.model_copy(update={"text": new_text})
        return await handler(event, data)

class PrivateBlockMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        chat = get_chat(event)
        if chat is not None and chat.type == "private":
            user = event.from_user
            if not (user and (user.username or "").lower() == ADMIN_USERNAME.lower()):
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer()
                    except Exception:
                        pass
                return
        return await handler(event, data)

class TrackMembershipMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.chat.type in ("group", "supergroup") and event.from_user:
            await track_membership(event.from_user.id, event.chat.id)
        return await handler(event, data)

class ThrottleMiddleware(BaseMiddleware):
    """Троттлинг для текстовых команд."""
    def __init__(self, rate: float = 1.5):
        self.rate = rate
        self.last_call = {}

    async def __call__(self, handler, event, data):
        user_id = event.from_user.id if event.from_user else None
        if user_id is None:
            return await handler(event, data)

        text = getattr(event, "text", None)
        if not text or not is_command_text(text):
            return await handler(event, data)

        username = event.from_user.username or str(user_id)
        asyncio.create_task(_log_player_action(user_id, username, text))

        now = time.monotonic()
        key = (user_id, "cmd")
        if now - self.last_call.get(key, 0) < self.rate:
            return
        self.last_call[key] = now
        return await handler(event, data)

class CallbackThrottleMiddleware(BaseMiddleware):
    """Троттлинг для инлайн-кнопок. Короткий кулдаун (350-500мс) и, что критично,
    ВСЕГДА отвечает на callback_query — иначе Telegram держит кнопку в состоянии
    "загрузка" до собственного таймаута, что выглядит как зависшая/незажимаемая кнопка.

    ВАЖНО: ключ (user_id, callback_data) почти всегда уникален (страница/предмет/id
    внутри callback_data), поэтому last_call растёт без ограничений и никогда не
    чистится сам — за часы работы с активной аудиторией это утечка памяти и
    постепенное замедление (в т.ч. ощущается как "кнопки тормозят"). Раз в
    CLEANUP_EVERY вызовов выбрасываем протухшие записи (старше rate * 20)."""
    CLEANUP_EVERY = 500

    def __init__(self, rate: float = 0.4):
        self.rate = rate
        self.last_call = {}
        self._calls_since_cleanup = 0

    def _cleanup(self, now: float):
        ttl = self.rate * 20
        stale = [k for k, t in self.last_call.items() if now - t > ttl]
        for k in stale:
            del self.last_call[k]

    async def __call__(self, handler, event: CallbackQuery, data):
        user_id = event.from_user.id if event.from_user else None
        if user_id is None:
            return await handler(event, data)

        now = time.monotonic()
        key = (user_id, event.data)
        if now - self.last_call.get(key, 0) < self.rate:
            try:
                await event.answer()
            except Exception:
                pass
            return
        self.last_call[key] = now

        self._calls_since_cleanup += 1
        if self._calls_since_cleanup >= self.CLEANUP_EVERY:
            self._calls_since_cleanup = 0
            self._cleanup(now)

        return await handler(event, data)

class StaleCallbackGuardMiddleware(BaseMiddleware):
    """Многие callback-хендлеры делают callback.data.split(":") и int(parts[N]) без
    защиты, полагаясь на то, что бот сам генерирует callback_data. Это верно почти
    всегда — но если формат callback_data когда-нибудь поменяется (новая версия
    бота), кнопки под СТАРЫМИ сообщениями (отправленными до обновления) начнут
    падать с ValueError/IndexError прямо на парсинге, ДО вызова callback.answer().
    Без этой страховки такая кнопка виснет с "часиками" до таймаута Telegram —
    тот же симптом, что чинили в safe_edit_text, только с другим триггером.
    Ловим узко (только ValueError/IndexError) — остальные ошибки идут в общий
    @dp.errors() как и раньше, тут ничего не маскируем сверх этого."""
    async def __call__(self, handler, event: CallbackQuery, data):
        try:
            return await handler(event, data)
        except (ValueError, IndexError):
            try:
                await event.answer("Кнопка устарела, обнови меню заново.", show_alert=True)
            except Exception:
                pass
            return

dp.callback_query.middleware(StaleCallbackGuardMiddleware())

dp.message.outer_middleware(AliasNormalizeMiddleware())
dp.message.middleware(TrackMembershipMiddleware())
dp.message.middleware(ThrottleMiddleware(0.6))
dp.callback_query.middleware(CallbackThrottleMiddleware(0.15))

_last_leg_reply = {}

@dp.errors()
async def error_handler(event: ErrorEvent):
    """ВАЖНО (баг, который ломал ВСЕ текстовые команды молча): в aiogram 3.x хендлер
    @dp.errors() получает ОДИН аргумент — объект ErrorEvent (с .update и .exception
    внутри), а не два отдельных позиционных (event, exception), как было раньше в
    aiogram 2.x. Со старой сигнатурой def error_handler(event, exception) aiogram на
    каждый вызов бросал TypeError ("missing 1 required positional argument") ВНУТРИ
    самого обработчика ошибок — а это значит, что при любом исключении в любом
    хендляре (farm/эволюция/перерождение/...) юзер не получал вообще ничего: ни
    результата команды, ни даже фолбэк-сообщения "попробуй ещё раз", потому что
    сам механизм отправки этого фолбэка падал ещё до отправки. Симптом ровно такой,
    какой был на скрине: команда молчит всегда, при любом отдельном вызове, без
    исключений в логах (потому что traceback.print_exc() тоже не успевал выполниться
    в старой версии — TypeError происходил на уровне вызова хендлера aiogram'ом).
    Теперь сигнатура правильная: exception достаём из event.exception."""
    exception = event.exception

    if isinstance(exception, TelegramRetryAfter):
        await asyncio.sleep(exception.retry_after)
        return True

    import traceback
    traceback.print_exc()
    print(f"Необработанная ошибка: {exception!r}")

    try:
        message = getattr(event.update, "message", None)
        if message is not None:
            await message.reply("⚠️ Что-то пошло не так при обработке команды, попробуй ещё раз.")
    except Exception:
        pass

    return True

