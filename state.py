"""
state.py — единственный источник правды для общих runtime-объектов бота:
экземпляры Bot/Dispatcher из aiogram, на которые ссылаются все модули
с хендлерами и middleware.
"""
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import TOKEN

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
