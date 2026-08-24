"""
main.py — точка входа: инициализация БД, HTTP-сервер для healthcheck/
self-ping, фоновые задачи (буст Шара Хроноса, очистка логов, флаш буфера
логов игроков) и запуск long-polling бота.

Импортирует все handlers_*-модули ради их побочного эффекта регистрации
хендлеров на общем `dp` (см. state.py) через декораторы @dp.message/
@dp.callback_query — сам импорт больше нигде не используется напрямую,
поэтому многие импорты ниже помечены как "noqa" для линтеров.
"""
import asyncio
import os

import aiohttp
from aiohttp import web

from config import TOKEN, TURSO_URL, TURSO_TOKEN, PING_INTERVAL
from state import bot, dp
from economy import init_db, chronos_orb_boost_loop, auto_log_cleanup_loop, \
    _flush_player_log_buffer, _player_log_buffer, db_exec_many

# Регистрация middleware (важно импортировать до старта polling —
# middleware регистрируется на dp на уровне модуля при импорте).
import middlewares  # noqa: F401
import subscription  # noqa: F401

# Регистрация всех хендлеров (порядок соответствует отсутствию циклических
# зависимостей между модулями; сам dp — общий, см. state.py).
import handlers_inventory  # noqa: F401
import handlers_cases_evo  # noqa: F401
import handlers_profile  # noqa: F401
import handlers_economy  # noqa: F401
import handlers_help  # noqa: F401
import handlers_admin  # noqa: F401

async def handle(request):
    return web.Response(text="Бот Нога Работает!")

async def keep_alive():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        domain = os.environ.get("KOYEB_PUBLIC_DOMAIN")
        if domain:
            url = f"https://{domain}"
    if not url:
        print("Ни RENDER_EXTERNAL_URL, ни KOYEB_PUBLIC_DOMAIN не заданы, self-ping отключён")
        return

    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    print(f"Self-ping: {resp.status}")
            except Exception as e:
                print(f"Self-ping не удался: {e}")

async def main():
    await init_db()

    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    asyncio.create_task(keep_alive())
    asyncio.create_task(chronos_orb_boost_loop())
    asyncio.create_task(auto_log_cleanup_loop())
    asyncio.create_task(_flush_player_log_buffer())

    print("Бот НОГА запущен!")
    try:
        await dp.start_polling(bot, drop_pending_updates=False)
    finally:
        if _player_log_buffer:
            try:
                batch, _player_log_buffer[:] = _player_log_buffer[:], []
                await db_exec_many(
                    "INSERT INTO player_action_log (ts, user_id, username, command) VALUES (?, ?, ?, ?)",
                    batch,
                )
            except Exception as e:
                print(f"Финальный flush player_action_log не удался: {e}")
        await bot.session.close()
        await runner.cleanup()

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Установи переменную окружения BOT_TOKEN")
    if not TURSO_URL or not TURSO_TOKEN:
        raise RuntimeError("Установи переменные окружения TURSO_DATABASE_URL и TURSO_AUTH_TOKEN")
