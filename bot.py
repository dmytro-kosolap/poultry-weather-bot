import asyncio
import aiohttp
from datetime import datetime, timedelta
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
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

logger.info("✅ Ключі завантажені")

client = genai.Client(api_key=GEMINI_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

ADMIN_ID = 708323174
CHAT_ID = -1001761937362

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
            except Exception as e:
                logger.error(f"Помилка {c['name']}: {e}")
                report += f"❌ <code>{c['name'].ljust(17)} помилка</code>\n"

    # Цікавий факт про птахівництво
    try:
        prompt = "Розкажи один цікавий факт про бройлерів, качок, індиків, перепілок або гусей (обери одне). 1-2 речення, максимально коротко і цікаво. Без форматування, без лапок."
        
        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt
        )
        
        fact = resp.text.strip().replace('\n', ' ').replace('  ', ' ')
        if len(fact) > 300:
            fact = fact[:297].rsplit(' ', 1)[0] + "..."
        
        advice = f"\n\n🐔 <b>ЦІКАВИЙ ФАКТ:</b> {fact}"
        logger.info(f"✅ Факт: {len(fact)} симв.")
        
    except Exception as e:
        logger.error(f"❌ Gemini: {e}")
        backup_facts = [
            "Качки можуть бачити фарби ультрафіолетового спектру, недоступні людському оку.",
            "Перепілка за рік може знести до 300 яєць при вазі всього 150 грамів.",
            "Індики здатні розпізнавати своїх родичів серед сотні птахів.",
            "Гуси були одомашнені раніше за курей — близько 3000 років до н.е.",
            "Бройлер набирає 2 кг ваги всього за 35-40 днів вирощування."
        ]
        import random
        advice = f"\n\n🐔 <b>ЦІКАВИЙ ФАКТ:</b> {random.choice(backup_facts)}"

    return report + advice + "\n\n<b>Вдалого господарювання! 🐔</b>"

async def daily_task():
    """Розсилка о 19:00"""
    while True:
        now = datetime.now(pytz.timezone('Europe/Kiev'))
        target = now.replace(hour=19, minute=0, second=0, microsecond=0)
        
        if now > target:
            target += timedelta(days=1)
        
        wait_seconds = (target - now).total_seconds()
        logger.info(f"⏳ Наступна розсилка через {wait_seconds/3600:.1f} годин (о 19:00)")
        
        await asyncio.sleep(wait_seconds)
        
        logger.info("🕐 Розсилка о 19:00...")
        try:
            text = await get_weather_forecast()
            await bot.send_message(CHAT_ID, text, parse_mode=ParseMode.HTML)
            logger.info("✅ Надіслано!")
        except Exception as e:
            logger.error(f"❌ Помилка: {e}")

@dp.message()
async def manual(m: types.Message):
    if m.from_user.id != ADMIN_ID:
        logger.warning(f"❌ Спроба від {m.from_user.id}")
        return
    
    logger.info(f"👤 Адмін {m.from_user.id}")
    try:
        text = await get_weather_forecast()
        await m.answer(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Помилка: {e}")
        await m.answer("❌ Помилка")

async def main():
    logger.info("🚀 БОТ ЗАПУЩЕНО")
    logger.info(f"⏰ 19:00 | 👤 {ADMIN_ID}")
    
    # Запускаємо фонові задачі
    asyncio.create_task(daily_task())
    logger.info("✅ Фонові задачі активні!")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
