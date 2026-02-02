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

# Налаштування логування для Railway (щоб ми бачили помилки в Logs)
logging.basicConfig(level=logging.INFO)

load_dotenv()

# Налаштування Gemini (Використовуємо os.getenv для зв'язку з Railway)
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel('models/gemini-1.5-flash')
    logging.info("✅ Gemini налаштовано успішно")
except Exception as e:
    logging.error(f"❌ Помилка налаштування Gemini: {e}")
    model = None

# Твої ID (Залишаємо як числа)
ADMIN_ID = 708323174 
GROUP_ID = -1001761937362

# Налаштування Бота через змінні оточення
bot = Bot(token=os.getenv("8049414176:AAGXfxG611y9L2p4wNX1VrhZQlXxH_YGiog"))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

REGIONS = {
    "Центр (Київ)": "Kyiv",
    "Південь (Одеса)": "Odesa",
    "Захід (Львів)": "Lviv",
    "Схід (Харків)": "Kharkiv",
    "Північ (Чернігів)": "Chernihiv"
}

def get_forecast(city):
    api_key = os.getenv("WEATHER_API_KEY")
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={api_key}&units=metric&lang=ua"
    try:
        r = requests.get(url).json()
        if r.get("cod") != "200": return None
        next_24h = r['list'][:8]
        temps = [item['main']['temp'] for item in next_24h]
        return {
            "min": round(min(temps), 1),
            "max": round(max(temps), 1),
            "desc": next_24h[0]['weather'][0]['description'].capitalize(),
            "hum": next_24h[0]['main']['humidity']
        }
    except Exception as e:
        logging.error(f"⚠️ Помилка погоди для {city}: {e}")
        return None

async def send_daily_report(chat_id):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
    weather_summary = ""
    table_rows = []

    for name, city in REGIONS.items():
        w = get_forecast(city)
        if w:
            table_rows.append(f"📍 {name}: {w['min']}°...{w['max']}°C ({w['desc']})")
            weather_summary += f"{name}: {w['min']}...{w['max']}°C, {w['desc']}. "

    # Промпт для ШІ
    prompt = (
        f"Ти головний технолог групи 'Птахівництво України'. Ось прогноз на ЗАВТРА ({tomorrow}): {weather_summary}. "
        "Дай одну корисну пораду фермерам (до 80 слів). Пиши про воду, вентиляцію або підстилку. "
        "Використовуй зірочки (*) для виділення важливого."
    )

    advice = "⚠️ Порада: Обов'язково перевірте стан підстилки та відсутність протягів у пташнику."
    if model:
        try:
            res = model.generate_content(prompt)
            advice = res.text.strip()
        except Exception as e:
            logging.error(f"⚠️ Помилка Gemini: {e}")

    report = f"📅 **Метеозведення для птахівників**\nПрогноз на: **{tomorrow}**\n\n"
    report += "\n".join(table_rows)
    report += f"\n\n--- 📝 **ПОРАДИ ТЕХНОЛОГА** ---\n{advice}\n\n🍀 Вдалого вечора!"
    
    try:
        await bot.send_message(chat_id, report, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"❌ Не вдалося відправити повідомлення в {chat_id}: {e}")

@dp.message(Command("weather"))
async def weather_manual(message: types.Message):
    # Тільки ти можеш запускати вручну
    if message.from_user.id == ADMIN_ID:
        await message.answer("🔄 Готую прогноз для вас та групи...")
        await send_daily_report(message.chat.id)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🐣 Бот запущений і готовий до роботи! Авто-звіт прийде о 19:00.")

async def main():
    # Налаштовуємо планувальник на 19:00 щодня
    scheduler.add_job(send_daily_report, 'cron', hour=19, minute=0, args=[ADMIN_ID])
    scheduler.add_job(send_daily_report, 'cron', hour=19, minute=0, args=[GROUP_ID])
    
    scheduler.start()
    logging.info("🚀 Бот офіційно запущений у хмарі!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())



