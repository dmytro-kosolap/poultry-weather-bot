import asyncio
import aiohttp
import aiocron
from datetime import datetime, timedelta
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from google import genai
import logging
import os
from dotenv import load_dotenv

# Завантажуємо змінні з .env
load_dotenv()

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# === КЛЮЧІ З .env ===
TOKEN = os.getenv("BOT_TOKEN")
WEATHER_KEY = os.getenv("WEATHER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not all([TOKEN, WEATHER_KEY, GEMINI_KEY]):
    logger.error("❌ Не знайдено всі ключі в .env!")
    exit(1)

logger.info("✅ Ключі завантажено")

# Налаштування Gemini (нова бібліотека)
client = genai.Client(api_key=GEMINI_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

ICONS = {
    "ясно": "☀️", "хмарно": "☁️", "хмарність": "⛅",
    "дощ": "🌧", "сніг": "❄️", "туман": "🌫",
    "злива": "🌦", "гроза": "⛈"
}

async def get_weather_forecast():
    cities = [
        {"reg": "Центр", "name": "Київ", "eng": "Kyiv"},
        {"reg": "Південь", "name": "Одеса", "eng": "Odesa"},
        {"reg": "Захід", "name": "Львів", "eng": "Lviv"},
        {"reg": "Схід", "name": "Харків", "eng": "Kharkiv"},
        {"reg": "Північ", "name": "Чернігів", "eng": "Chernihiv"}
    ]
    
    tomorrow = datetime.now() + timedelta(days=1)
    date_str = tomorrow.strftime("%d-%m-%Y")
    iso_date = tomorrow.strftime("%Y-%m-%d")
    
    report = f"📅 <b>ПОГОДА НА ЗАВТРА ({date_str})</b>\n\n"
    report += "<code>Регіон (Місто)      День | Ніч</code>\n"
    summary = ""

    async with aiohttp.ClientSession() as session:
        for c in cities:
            url = f"http://api.openweathermap.org/data/2.5/forecast?q={c['eng']}&appid={WEATHER_KEY}&units=metric&lang=uk"
            try:
                async with session.get(url, timeout=10) as r:
                    data = await r.json()
                    temps, descs = [], []
                    for entry in data['list']:
                        if iso_date in entry['dt_txt']:
                            temps.append(entry['main']['temp'])
                            descs.append(entry['weather'][0].get('description', 'хмарно'))
                    
                    if temps:
                        d, n = round(max(temps)), round(min(temps))
                        wd = descs[len(descs)//2] if descs else "хмарно"
                    else:
                        d, n, wd = 0, 0, "хмарно"
                    
                    icon = next((ICONS[k] for k in ICONS if k in wd.lower()), "☁️")
                    fmt = lambda t: (f"+{t}" if t > 0 else str(t)).rjust(4)
                    report += f"{icon} <code>{(c['reg']+' ('+c['name']+')').ljust(17)} {fmt(d)}° | {fmt(n)}°</code>\n"
                    summary += f"{c['name']}: {d}/{n}°C. "
            except Exception as e:
                logger.error(f"Помилка {c['name']}: {e}")
                report += f"❌ <code>{c['name'].ljust(17)} помилка</code>\n"

    # Gemini поради
    try:
        prompt = f"Ти птахівник в Україні. Завтра: {summary}. Дай пораду на 800 знаків українською про підготовку курника."
        resp = client.models.generate_content(model="models/gemini-2.5-flash-lite", contents=prompt)
        advice = f"\n\n📝 <b>ПОРАДИ ПТАХІВНИКАМ:</b>\n\n{resp.text}"
        logger.info("✅ Поради отримано")
    except Exception as e:
        logger.error(f"❌ Gemini помилка: {e}")
        advice = "\n\n⚠️ <b>ШІ в режимі сну</b>"

    return report + advice + "\n\n<b>Вдалого господарювання! 🐔</b>"

@aiocron.crontab('0 22 * * *', tz=pytz.timezone('Europe/Kiev'))
async def daily():
    logger.info("🕐 Запуск розсилки...")
    try:
        text = await get_weather_forecast()
        await bot.send_message(-1001761937362, text, parse_mode=ParseMode.HTML)
        logger.info("✅ Надіслано!")
    except Exception as e:
        logger.error(f"❌ Помилка розсилки: {e}")

@dp.message()
async def manual(m: types.Message):
    if m.from_user.id == 708323174:
        logger.info("👤 Ручний запит")
        try:
            text = await get_weather_forecast()
            await m.answer(text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"❌ Помилка: {e}")
            await m.answer("❌ Помилка при формуванні прогнозу")

async def main():
    logger.info("🚀 БОТ ЗАПУЩЕНО")
    logger.info(f"📍 Група: -1001761937362")
    logger.info(f"👤 Адмін: 708323174")
    daily.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())