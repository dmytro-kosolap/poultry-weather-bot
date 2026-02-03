import os
import asyncio
import requests
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
import google.generativeai as genai
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone

# --- НАЛАШТУВАННЯ ---
TOKEN = "ТВІЙ_НОВИЙ_ТОКЕН" # Встав сюди свій токен від @BotFather
WEATHER_KEY = "d51d1391f46e9ac8d58cf6a1b908ac66"
GEMINI_KEY = "ТВІЙ_GEMINI_KEY" # Встав ключ Gemini
ADMIN_ID = 708323174
GROUP_ID = -1001761937362
RECIPIENTS = [ADMIN_ID, GROUP_ID]

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-pro')
bot = Bot(token=TOKEN)
dp = Dispatcher()
kyiv_tz = timezone("Europe/Kyiv")
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
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_KEY}&units=metric&lang=uk"
    try:
        r = requests.get(url).json()
        if r.get("cod") != "200": return "Н/Д"
        
        day_temp, night_temp, desc = "Н/Д", "Н/Д", ""
        tomorrow = (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%Y-%m-%d")
        
        for item in r["list"]:
            dt_txt = item["dt_txt"]
            if tomorrow in dt_txt:
                if "12:00:00" in dt_txt:
                    day_temp = round(item["main"]["temp"], 1)
                    desc = item["weather"][0]["description"]
                if "00:00:00" in dt_txt:
                    night_temp = round(item["main"]["temp"], 1)

        icon = "☁️"
        for key, emoji in WEATHER_ICONS.items():
            if key in desc.lower():
                icon = emoji
                break
        return f"{icon} День: {day_temp}° | Ніч: {night_temp}°C ({desc})"
    except: return "Помилка даних"

async def get_poultry_advice(summary):
    prompt = (
        f"Ти головний технолог-птахівник. Прогноз на завтра: {summary}. "
        f"Напиши розгорнуту професійну інструкцію (мінімум 800 символів, 3-4 абзаци). "
        f"Дай конкретні поради по калорійності корму, температурі води та підстилці. "
        f"Уникай води, пиши по суті, використовуй цифри."
    )
    try:
        response = await model.generate_content_async(prompt)
        return response.text.strip() if response.text else "Помилка ШІ."
    except Exception as e:
        print(f"Gemini Error: {e}")
        return "Зверніть увагу на обігрів та якість кормів при заморозках."

async def send_daily_report(chat_id):
    tomorrow_str = (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%d.%m.%Y")
    weather_rows = []
    summary_ai = ""

    for label, city in REGIONS.items():
        res = get_weather_day_night(city)
        weather_rows.append(f"📍 <b>{label}:</b> {res}")
        summary_ai += f"{label}: {res}; "

    advice = await get_poultry_advice(summary_ai)
    report = (
        f"📅 <b>Метеозведення для птахівників</b>\nПрогноз на завтра: {tomorrow_str}\n\n"
        + "\n".join(weather_rows) + "\n\n"
        f"--- 📝 <b>ПОРАДИ ПТАХІВНИКАМ</b> ---\n{advice}\n\n🍀 Вдалого господарювання!"
    )
    try:
        await bot.send_message(chat_id, report, parse_mode=ParseMode.HTML)
    except Exception as e: print(f"Error: {e}")

@dp.message(Command("weather"))
async def weather_manual(message: types.Message):
    if message.from_user.id == ADMIN_ID: await send_daily_report(message.chat.id)

async def scheduled_broadcast():
    for cid in RECIPIENTS:
        await send_daily_report(cid)
        await asyncio.sleep(1)

async def main():
    scheduler.add_job(scheduled_broadcast, 'cron', hour=19, minute=0)
    scheduler.start()
    print("🚀 Автоматика на 19:00 запущена!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
