import os
import asyncio
import requests
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from dotenv import load_dotenv
from google import genai  # Нова бібліотека 2026
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone

# 1. Налаштування
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

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
    "переважно хмарно": "🌤",
    "мінлива хмарність": "⛅",
    "дощ": "🌧",
    "сніг": "❄️",
    "гроза": "⛈",
    "туман": "🌫",
    "уривчасті хмари": "☁️"
}

def get_weather_day_night(city_name):
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city_name}&appid=654e58f000300185e490586e3097c21e&units=metric&lang=uk"
    try:
        r = requests.get(url).json()
        tomorrow = (datetime.now(kyiv_tz) + timedelta(days=1)).date()
        
        day_temps = []
        night_temps = []
        desc = "мінлива хмарність"

        for item in r.get('list', []):
            dt_obj = datetime.fromtimestamp(item['dt'], tz=kyiv_tz)
            if dt_obj.date() == tomorrow:
                temp = item['main']['temp']
                hour = dt_obj.hour
                if 9 <= hour <= 18:
                    day_temps.append(temp)
                    desc = item['weather'][0]['description']
                else:
                    night_temps.append(temp)

        d_t = f"{max(day_temps):.1f}°" if day_temps else "?°"
        n_t = f"{min(night_temps):.1f}°" if night_temps else "?°"
        icon = WEATHER_ICONS.get(desc.lower(), "☁️")
        
        return f"{icon} День: {d_t} | Ніч: {n_t}C ({desc})"
    except:
        return "❌ Дані недоступні"

async def get_poultry_advice(summary):
    prompt = (
        f"Ти — провідний технолог компанії з виробництва комбікормів kormikorm.com.ua. "
        f"На основі цього прогнозу: {summary}, напиши професійну пораду для птахівників (600+ символів). "
        f"Акцентуй на обмінній енергії корму, температурі води та вентиляції. "
        f"Стиль: експертний, діловий."
    )
    try:
        # Новий метод виклику Gemini у 2026 році
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"!!! КРИТИЧНА ПОМИЛКА ШІ: {e}")
        return "У зв'язку з погодними умовами рекомендуємо посилити енергетичну цінність раціону та стежити за температурою підстилки."

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
    await message.answer("Бот запущено. Очікуйте розсилку о 19:00 або натисніть /weather (тільки для адміна).")

async def main():
    scheduler.add_job(send_daily_report, 'cron', hour=19, minute=0, args=[GROUP_ID])
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())







