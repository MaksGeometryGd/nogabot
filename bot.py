import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiohttp import web

# ВСТАВЬ СВОЙ ТОКЕН СЮДА
TOKEN = "8383839196:AAEJAbGIB1gqtQ85M4ZRZ98Z9m4MeCvlank"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

# База данных
conn = sqlite3.connect("nogost.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    score INTEGER DEFAULT 0
)
""")
conn.commit()

MILESTONES = [10, 50, 150, 300, 500, 800, 1200, 1600, 2000, 2400, 3000, 3600, 4200, 4800, 5400, 6000]

def get_level_visual(score: int) -> str:
    if score < 10:   return "Обычный безногий челик 🧍 (0 ур)"
    if score < 50:   return "🦵 (1 ур)"
    if score < 150:  return "🦵🦵 (2 ур)"
    if score < 300:  return "🦵🦵🦵 (3 ур)"
    if score < 500:  return "🦵🦵🦵🦵 (4 ур)"
    if score < 800:  return "🦵🦵🦵🦵🦵 (5 ур)"
    if score < 1200: return "🦿🦵🦵🦵🦵 (6 ур)"
    if score < 1600: return "🦿🦿🦵🦵🦵 (7 ур)"
    if score < 2000: return "🦿🦿🦿🦵🦵 (8 ур)"
    if score < 2400: return "🦿🦿🦿🦿🦵 (9 ур)"
    if score < 3000: return "🦿🦿🦿🦿🦿 (10 ур)"
    if score < 3600: return "🍗 Куринная ношка(11 ур)"
    if score < 4200: return "🐾 Нога котости(12 ур)"
    if score < 4800: return "🩴 Тапость (13 ур)"
    if score < 5400: return "🧦 Носочек (14 ур)"
    if score < 6000: return "🦶 Пяткость (15 ур)"
    return "🛸🦵 НОГА БОГА (Макс ур)"

def get_next_level_info(score: int) -> str:
    for m in MILESTONES:
        if score < m:
            return f"До некст уровня надо еще {m - score} очков 🦵"
    return "Ты стал абсолютной Ногой. Выше расти некуда! 🛸"

@dp.message(F.text.contains("🦵"))
async def count_legs(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    legs_count = message.text.count("🦵")
    if legs_count == 0:
        return

    cursor.execute("SELECT score FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row:
        new_score = row[0] + legs_count
        cursor.execute("UPDATE users SET score = ?, username = ? WHERE user_id = ?", (new_score, username, user_id))
    else:
        new_score = legs_count
        cursor.execute("INSERT INTO users (user_id, username, score) VALUES (?, ?, ?)", (user_id, username, new_score))
    
    conn.commit()
    await message.reply(f"+{legs_count} к ногости 👣 (Всего: {new_score})")

@dp.message(F.text.lower() == "!моя нога")
async def my_profile(message: Message):
    user_id = message.from_user.id
    cursor.execute("SELECT score FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    score = row[0] if row else 0
    
    status = get_level_visual(score)
    next_lvl = get_next_level_info(score)
    
    text = (
        f"👣 **ТВОЯ ЛЮТАЯ НОГОСТЬ:**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"● Твои очки: `{score}`\n"
        f"● Вид твоих ног: {status}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"● {next_lvl}"
    )
    await message.reply(text)

@dp.message(F.text.lower() == "!топ ног")
async def top_players(message: Message):
    cursor.execute("SELECT username, score FROM users ORDER BY score DESC LIMIT 10")
    rows = cursor.fetchall()
    
    if not rows:
        await message.reply("В топе пока пусто, никто еще не кинул ногу... 🧍")
        return
        
    text = "🏆 **ТОП-10 САМЫХ НОГОСТЬ:**\n\n"
    for idx, (username, score) in enumerate(rows, 1):
        mention = f"@{username}" if not username.startswith("@") else username
        mention = mention.replace("_", "\\_")
        status = get_level_visual(score)
        text += f"{idx}. {mention} — `{score}` очков\n   └ Вид: {status}\n\n"
        
    await message.reply(text)

# Мини-сервер для обмана Render (чтобы бот не отключался)
async def handle(request):
    return web.Response(text="Бот Нога Работает!")

async def main():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    asyncio.create_task(site.start())
    
    print("Бот НОГА запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
