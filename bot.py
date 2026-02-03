cd ~/poultry_bot
cat > bot.py << 'EOF'
import asyncio
import aiohttp
import aiocron
from datetime import datetime, timedelta
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from google import genai
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
WEATHER_KEY = os.getenv("WEATHER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not all([TOKEN, WEATHER_KEY, GEMINI_KEY]):
    logger.error("❌ Не знайдено всі ключі в .env!")
    exit(1)

logger.info("✅ Ключі завантажено")

client = genai.Client(api_key=GEMINI_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Тільки цей ID може писати боту
ADMIN_ID = 708323174

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

    # Скорочені поради (~400 знаків)
    try:
        prompt = f"Ти птахівник в Україні. Завтра: {summary}. Дай коротку пораду на 400 знаків українською про догляд за птицею в таку погоду."
        resp = client.models.generate_content(model="models/gemini-2.5-flash-lite", contents=prompt)
        advice = f"\n\n📝 <b>ПОРАДА:</b>\n\n{resp.text}"
        logger.info("✅ Поради отримано")
    except Exception as e:
        logger.error(f"❌ Gemini помилка: {e}")
        advice = "\n\n⚠️ <b>ШІ в режимі сну</b>"

    return report + advice + "\n\n<b>Вдалого господарювання! 🐔</b>"

# РОЗСИЛКА О 19:00 (змінено з 22:00)
@aiocron.crontab('0 19 * * *', tz=pytz.timezone('Europe/Kiev'))
async def daily():
    logger.info("🕐 Запуск розсилки о 19:00...")
    try:
        text = await get_weather_forecast()
        await bot.send_message(-1001761937362, text, parse_mode=ParseMode.HTML)
        logger.info("✅ Надіслано в групу!")
    except Exception as e:
        logger.error(f"❌ Помилка розсилки: {e}")

# ТІЛЬКИ ДЛЯ АДМІНА (ID 708323174)
@dp.message()
async def manual(m: types.Message):
    # Перевірка ID
    if m.from_user.id != ADMIN_ID:
        logger.warning(f"❌ Спроба доступу від {m.from_user.id}")
        return  # Ігноруємо чужі повідомлення
    
    logger.info(f"👤 Ручний запит від адміна {m.from_user.id}")
    try:
        text = await get_weather_forecast()
        await m.answer(text, parse_mode=ParseMode.HTML)
        logger.info("✅ Ручний прогноз надіслано")
    except Exception as e:
        logger.error(f"❌ Помилка: {e}")
        await m.answer("❌ Помилка при формуванні прогнозу")

async def main():
    logger.info("🚀 БОТ ЗАПУЩЕНО")
    logger.info(f"📍 Група: -1001761937362")
    logger.info(f"👤 Адмін ID: {ADMIN_ID}")
    logger.info("⏰ Авторозсилка: 19:00 (Київ)")
    daily.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
EOF
