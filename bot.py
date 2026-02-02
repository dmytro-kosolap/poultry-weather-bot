import os
import asyncio
import requests
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from dotenv import load_dotenv
import google.generativeai as genai
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)
load_dotenv()

# Безпечне налаштування Gemini
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel('models/gemini-1.5-flash')
except Exception as e:
    logging.error(f"Помилка ініціалізації Gemini: {e}")
    model = None

ADMIN_ID = 708323174 
GROUP_ID = -1001761937362

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

@dp.message(Command("weather"))
async def weather_manual(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("📡 Запит отримано! Готую прогноз...")
        # Тут логіка відправки звіту...
        # (код звіту лишається тим самим)

async def main():
    scheduler.start()
    logging.info("🚀 Бот намагається стартувати...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

if __name__ == "__main__":

    asyncio.run(main())

