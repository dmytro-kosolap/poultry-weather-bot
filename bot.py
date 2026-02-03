cd ~/poultry_bot && cat > bot.py << 'EOF'
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

    # ПОРАДИ ВІД GEMINI з системною інструкцією
    try:
        # Системна інструкція - "закон" для моделі
        system_msg = (
            "Ти — лаконічний помічник птахівника. Твоє завдання: дати одну коротку практичну пораду. "
            "ПРАВИЛА: Категорично заборонено будь-яке форматування (без **, без #, без списків). "
            "Тільки текст поради одним-двома реченнями. Жодних привітань чи заголовків."
        )
        
        user_msg = f"Погода: {summary}. Дай пораду до 150 символів."

        # Використовуємо системну інструкцію та ліміти
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_msg,
            config={
                "system_instruction": system_msg,
                "max_output_tokens": 80,  # Фізично обмежуємо довжину
                "temperature": 0.4,       # Чим менше, тим конкретніша відповідь
            }
        )
        
        # Додаткова чистка тексту
        text = resp.text.strip().replace("*", "").replace("#", "").replace("_", "")
        # Беремо тільки перший рядок
        text = text.split('\n')[0]
        
        if len(text) > 200:
            text = text[:197] + "..."
            
        advice = f"\n\n📝 <b>ПОРАДА:</b> {text}"
        logger.info(f"✅ Порада: {len(text)} симв.")
        
    except Exception as e:
        logger.error(f"❌ Gemini помилка: {e}")
        advice = "\n\n⚠️ <b>ШІ в режимі сну</b>"

    return report + advice + "\n\n<b>Вдалого господарювання! 🐔</b>"

@aiocron.crontab('0 19 * * *', tz=pytz.timezone('Europe/Kiev'))
async def daily():
    logger.info("🕐 Розсилка о 19:00...")
    try:
        text = await get_weather_forecast()
        await bot.send_message(-1001761937362, text, parse_mode=ParseMode.HTML)
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
    daily.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
EOF
