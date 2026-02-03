import os
import asyncio
import requests
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from dotenv import load_dotenv
import google.generativeai as genai
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone

# 1. Налаштування
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

ADMIN_ID = 708323174
GROUP_ID = -1001761937362
RECIPIENTS = [ADMIN_ID, GROUP_ID]

bot = Bot(token=os.getenv("BOT_TOKEN"))
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
    "ясно": "☀️",
    "хмарно": "☁️",
    "хмарність": "⛅",
    "дощ": "🌧",
    "сніг": "❄️",
    "туман": "🌫",
    "злива": "🌦"
}

def get_weather_day_night(city):
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={os.getenv('WEATHER_API_KEY')}&units=metric&lang=uk"
    try:
        r = requests.get(url).json()
        if r.get("cod") != "200": return "Н/Д"
        
        day_temp = "Н/Д"
        night_temp = "Н/Д"
        desc = ""

        # Шукаємо прогноз на завтра
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
    except:
        return "Помилка даних"

async def get_poultry_advice(summary):
    tomorrow_date = (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%d.%m.%Y")
    prompt = (
        f"Ти — досвідчений експерт-консультант з птахівництва. На завтра {tomorrow_date} маємо такий прогноз: {summary}.\n\n"
        f"ЗАВДАННЯ: Напиши детальну пораду для фермерів на цей день (обсяг 600-900 символів).\n"
        f"ОБОВ'ЯЗКОВО ВРАХУЙ:\n"
        f"1. Почни зі звернення до птахівників та вкажи дату.\n"
        f"2. Проаналізуй нічні морози: якщо нижче -15°C, наголоси на екстремальному обігріві та калорійності корму (кукурудза, жири).\n"
        f"3. Напиши про воду: як запобігти замерзанню напувалок.\n"
        f"4. Порадь щодо підстилки (товщина, сухість) та вентиляції (щоб не було протягів).\n"
        f"5. Тон має бути професійним, експертним і застережливим.\n"
        f"НЕ ПИШИ загальних фраз типу 'дбайте про птахів', пиши конкретні дії."
    )
    try:
        # Додаємо параметри температури генерації для більшої креативності
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.7)
        )
        return response.text.strip()
    except Exception as e:
        print(f"Помилка Gemini: {e}")
        return "Увага! Очікуються морози. Забезпечте птахам глибоку підстилку, калорійний корм та стежте, щоб вода в напувалках не замерзала."

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
        f"📅 <b>Метеозведення для птахівників</b>\n"
        f"Прогноз на завтра: {tomorrow_str}\n\n"
        + "\n".join(weather_rows) + "\n\n"
        f"--- 📝 <b>ПОРАДИ ПТАХІВНИКАМ</b> ---\n"
        f"{advice}\n\n"
        f"🍀 <i>Вдалого господарювання!</i>\n"
        f"🔗 <a href='https://kormikorm.com.ua'>kormikorm.com.ua</a>"
    )

    try:
        await bot.send_message(chat_id, report, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        print(f"Error: {e}")

@dp.message(Command("weather"))
async def weather_manual(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await send_daily_report(message.chat.id)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("✅ Бот готовий до роботи. Розсилка о 19:00.")

async def scheduled_broadcast():
    for cid in RECIPIENTS:
        await send_daily_report(cid)
        await asyncio.sleep(1)

async def main():
    scheduler.add_job(scheduled_broadcast, 'cron', hour=19, minute=0)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

