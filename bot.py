import os
import asyncio
import requests
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
import google.generativeai as genai
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone

# --- НАЛАШТУВАННЯ (Впиши свої дані сюди) ---
TOKEN = "ТВІЙ_ТОКЕН_ВІД_BOTFATHER"
WEATHER_KEY = "d51d1391f46e9ac8d58cf6a1b908ac66"
GEMINI_KEY = "ТВІЙ_КЛЮЧ_GEMINI"
ADMIN_ID = 708323174
GROUP_ID = -1001761937362  # Твоя група Птахівництво України
RECIPIENTS = [ADMIN_ID, GROUP_ID]

# Налаштування ШІ
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-pro')

# Ініціалізація бота
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Виправлення помилки часового поясу (Kyiv/Kiev)
try:
    kyiv_tz = timezone("Europe/Kyiv")
except:
    kyiv_tz = timezone("Europe/Kiev")

scheduler = AsyncIOScheduler(timezone=kyiv_tz)

REGIONS = {
    "Центр (Київ)": "Kyiv",
    "Південь (Одеса)": "Odesa",
    "Захід (Львів)": "Lviv",
    "Схід (Харків)": "Kharkiv",
    "Північ (Чернігів)": "Chernihiv"
}

WEATHER_ICONS = {
    "ясно": "☀️", "хмарно": "☁️", "хмарність": "⛅", "дощ": "🌧", "сніг": "❄️", "туман": "🌫", "злива": "🌦"
}

def get_weather_day_night(city):
    """Отримує прогноз погоди на завтра (день та ніч)"""
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_KEY}&units=metric&lang=uk"
    try:
        r = requests.get(url, timeout=10).json()
        if r.get("cod") != "200": return "Помилка API"
        
        day_temp, night_temp, desc = "Н/Д", "Н/Д", "хмарно"
        tomorrow = (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%Y-%m-%d")
        
        for item in r["list"]:
            if tomorrow in item["dt_txt"]:
                if "12:00:00" in item["dt_txt"]:
                    day_temp = round(item["main"]["temp"])
                    desc = item["weather"][0]["description"]
                if "00:00:00" in item["dt_txt"]:
                    night_temp = round(item["main"]["temp"])

        icon = "☁️"
        for key, emoji in WEATHER_ICONS.items():
            if key in desc.lower():
                icon = emoji
                break
        return f"{icon} День: {day_temp}° | Ніч: {night_temp}°C ({desc})"
    except:
        return "Сервер недоступний"

async def get_poultry_advice(summary):
    """Генерує розгорнуту пораду через Gemini"""
    prompt = (
        f"Ти професійний технолог-птахівник. Прогноз погоди на завтра: {summary}. "
        "Напиши дуже розгорнуту пораду для власників домашньої птиці (кури, качки, бройлери). "
        "Текст має бути мінімум 800-1000 символів, розділений на абзаци. "
        "Опиши: 1. Режим обігріву та вентиляції. 2. Раціон (калорійність, добавки). 3. Стан підстилки та води. "
        "Пиши професійно, але зрозуміло. Не використовуй загальні фрази, давай конкретику для вказаних температур."
    )
    try:
        response = await model.generate_content_async(prompt)
        return response.text.strip()
    except:
        return "Помилка зв'язку з експертним ШІ. Перевірте температурний режим та наявність теплої води у пташниках."

async def send_daily_report(chat_id):
    """Формує та надсилає повний звіт"""
    tomorrow_str = (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%d.%m.%Y")
    weather_rows = []
    summary_for_ai = ""

    for label, city in REGIONS.items():
        res = get_weather_day_night(city)
        weather_rows.append(f"📍 <b>{label}:</b> {res}")
        summary_for_ai += f"{label}: {res}; "

    advice = await get_poultry_advice(summary_for_ai)

    report = (
        f"📅 <b>МЕТЕОЗВЕДЕННЯ ДЛЯ ПТАХІВНИКІВ</b>\n"
        f"Прогноз на завтра: {tomorrow_str}\n\n"
        + "\n".join(weather_rows) + "\n\n"
        f"📝 <b>ПРОФЕСІЙНА ПОРАДА:</b>\n\n{advice}\n\n"
        f"🍀 <i>Вдалого господарювання!</i>"
    )

    try:
        await bot.send_message(chat_id, report, parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"Помилка надсилання: {e}")

# Команда для ручної перевірки адміном
@dp.message(Command("weather"))
async def weather_manual(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🔄 Формую звіт, зачекайте...")
        await send_daily_report(message.chat.id)

async def scheduled_broadcast():
    """Розсилка для всіх реципієнтів"""
    for cid in RECIPIENTS:
        await send_daily_report(cid)
        await asyncio.sleep(2) # Пауза між повідомленнями

async def main():
    # Налаштовуємо розсилку на 19:00
    scheduler.add_job(scheduled_broadcast, 'cron', hour=19, minute=0)
    scheduler.start()
    
    print("🚀 БОТ ЗАПУЩЕНИЙ. Автоматичний звіт о 19:00 щодня.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
