"""
subscription.py — проверка обязательной подписки на канал перед фармом/
эволюцией/перерождением: кэш проверки, клавиатура с кнопкой подписки,
хендлер подтверждения подписки.
"""
import time

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import (
    ADMIN_USERNAME, ADMIN_USER_ID, REQUIRED_CHANNEL_URL, REQUIRED_CHANNEL_CHAT_ID,
    SUBSCRIPTION_CHECK_CACHE_TTL, TEXTS, _subscription_cache,
)
from state import bot, dp

def is_admin(message: Message) -> bool:
    return message.from_user.id == ADMIN_USER_ID or (message.from_user.username or "").lower() == ADMIN_USERNAME.lower()

def subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")],
    ])

async def is_subscribed(user_id: int) -> bool:
    """Проверяет подписку на REQUIRED_CHANNEL_CHAT_ID с коротким кэшем,
    чтобы не спамить getChatMember на каждый фарм/эво/перерождение."""
    cached = _subscription_cache.get(user_id)
    now = time.monotonic()
    if cached and now - cached[1] < SUBSCRIPTION_CHECK_CACHE_TTL:
        return cached[0]

    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL_CHAT_ID, user_id)
        subscribed = member.status not in ("left", "kicked")
        print(f"[sub-check] user={user_id} status={member.status} -> subscribed={subscribed}")
    except Exception as e:
        # ВРЕМЕННО (диагностика): раньше любая ошибка тут пропускала пользователя (subscribed=True).
        # Сейчас логируем во весь голос, чтобы увидеть причину. Пока не разберёмся — считаем НЕ подписанным.
        print(f"[sub-check] ОШИБКА при проверке ({REQUIRED_CHANNEL_CHAT_ID}, user={user_id}): {type(e).__name__}: {e}")
        subscribed = False

    _subscription_cache[user_id] = (subscribed, now)
    return subscribed

async def require_subscription(message: Message) -> bool:
    """Возвращает True если можно продолжать выполнение команды.
    Если пользователь не подписан — отправляет требование подписаться и возвращает False."""
    user_id = message.from_user.id
    if is_admin(message):
        return True
    if await is_subscribed(user_id):
        return True
    await message.reply(TEXTS["require_subscription_1"], reply_markup=subscription_keyboard())
    return False

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    _subscription_cache.pop(user_id, None)  # форс-рекheck, не ждём TTL кэша
    if await is_subscribed(user_id):
        await callback.answer("✅ Подписка подтверждена! Можешь фармить дальше.", show_alert=True)
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
    else:
        await callback.answer("❌ Подписки пока не вижу. Подпишись на канал и попробуй ещё раз.", show_alert=True)

