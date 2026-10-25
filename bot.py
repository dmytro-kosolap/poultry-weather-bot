import asyncio
import aiohttp
from datetime import datetime, timedelta
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
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

if not all([TOKEN, WEATHER_KEY]):
    logger.error("❌ Не знайдено всі ключі в .env!")
    exit(1)

logger.info("✅ Ключі завантажені")

bot = Bot(token=TOKEN)
dp = Dispatcher()

ADMIN_ID = 708323174
CHAT_ID = -1001761937362

ICONS = {
    "ясно": "☀️", "ясне": "☀️", "сонячно": "☀️", "чисте небо": "☀️",
    "хмарно": "☁️", "похмуро": "☁️", "суцільна хмарність": "☁️",
    "мінлива хмарність": "⛅", "невелика хмарність": "⛅", "хмарність": "⛅",
    "дощ": "🌧️", "невеликий дощ": "🌦️", "помірний дощ": "🌧️",
    "злива": "🌦️", "сильний дощ": "🌧️", "невеликий мрячний дощ": "🌦️",
    "мряка": "🌦️", "невелика мряка": "🌦️",
    "сніг": "❄️", "невеликий сніг": "🌨️", "снігопад": "❄️",
    "дощ зі снігом": "🌨️", "мокрий сніг": "🌨️",
    "туман": "🌫️", "серпанок": "🌫️", "димка": "🌫️",
    "гроза": "⛈️", "шторм": "⛈️", "гроза з дощем": "⛈️"
}

# Автоматична п'ятнична розсилка новин у групу (True = вмикає, False = вимкнено).
# Команда "новини" для адміна працює завжди, незалежно від цього прапорця.
WEEKLY_NEWS_ENABLED = False



async def get_weather_forecast():
    cities = [
        {"name": "Київ",             "eng": "Kyiv"},
        {"name": "Вінниця",          "eng": "Vinnytsia"},
        {"name": "Житомир",          "eng": "Zhytomyr"},
        {"name": "Ужгород",          "eng": "Uzhhorod"},
        {"name": "Івано-Франківськ", "eng": "Ivano-Frankivsk"},
        {"name": "Львів",            "eng": "Lviv"},
        {"name": "Луцьк",            "eng": "Lutsk"},
        {"name": "Рівне",            "eng": "Rivne"},
        {"name": "Тернопіль",        "eng": "Ternopil"},
        {"name": "Хмельницький",     "eng": "Khmelnytskyi"},
        {"name": "Чернівці",         "eng": "Chernivtsi"},
        {"name": "Черкаси",          "eng": "Cherkasy"},
        {"name": "Кропивницький",    "eng": "Kropyvnytskyi"},
        {"name": "Миколаїв",         "eng": "Mykolaiv"},
        {"name": "Одеса",            "eng": "Odesa"},
        {"name": "Херсон",           "eng": "Kherson"},
        {"name": "Запоріжжя",        "eng": "Zaporizhzhia"},
        {"name": "Дніпро",           "eng": "Dnipro"},
        {"name": "Кривий Ріг",       "eng": "Kryvyi Rih"},
        {"name": "Полтава",          "eng": "Poltava"},
        {"name": "Харків",           "eng": "Kharkiv"},
        {"name": "Суми",             "eng": "Sumy"},
        {"name": "Чернігів",         "eng": "Chernihiv"},
    ]

    now = datetime.now(pytz.timezone('Europe/Kiev'))
    today_str = now.strftime("%d.%m.%Y")

    tomorrow = now + timedelta(days=1)
    iso_date = tomorrow.strftime("%Y-%m-%d")

    report = f"🐔 <b>Інформаційний дайджест Птахівника</b>\n📅 <b>{today_str}</b>\n\n"
    report += "☁️ <b>ПОГОДА НА ЗАВТРА:</b>\n"
    report += "<code>Місто              День | Ніч</code>\n"

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
                    report += f"{icon} <code>{c['name'].ljust(18)} {fmt(d)}° | {fmt(n)}°</code>\n"
            except Exception as e:
                logger.error(f"Помилка {c['name']}: {e}")
                report += f"❌ <code>{c['name'].ljust(18)} помилка</code>\n"

    # --- Ринкові цифри (курси, паливо, зерно, ціни Novus) ---
    grain_info = ""
    try:
        from grain_context import get_grain_context
        grain_info = await get_grain_context()
        logger.info("✅ Grain context отримано")
    except Exception as e:
        logger.warning(f"Grain context failed: {e}")

    # --- Збираємо фінальне повідомлення ---
    result = report
    if grain_info:
        result += f"\n{grain_info}"
    result += "\n\n<b>Вдалого господарювання! 🐔</b>"

    return result


async def daily_task():
    while True:
        now = datetime.now(pytz.timezone('Europe/Kiev'))
        target = now.replace(hour=19, minute=0, second=0, microsecond=0)

        if now >= target:
            target += timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        logger.info(f"⏳ Наступний дайджест через {wait_seconds/3600:.1f} год (о 19:00)")

        await asyncio.sleep(wait_seconds)

        logger.info("🕐 Розсилка щоденного дайджесту о 19:00...")
        try:
            text = await get_weather_forecast()
            await bot.send_message(CHAT_ID, text, parse_mode=ParseMode.HTML)
            logger.info("✅ Щоденний дайджест надіслано!")
        except Exception as e:
            logger.error(f"❌ Помилка щоденного дайджесту: {e}")


async def weekly_news_task():
    while True:
        now = datetime.now(pytz.timezone('Europe/Kiev'))

        days_until_friday = (4 - now.weekday()) % 7
        target = now.replace(hour=9, minute=0, second=0, microsecond=0)
        target += timedelta(days=days_until_friday)

        if days_until_friday == 0 and now >= target:
            target += timedelta(days=7)

        wait_seconds = (target - now).total_seconds()
        logger.info(
            f"📰 Наступний тижневий дайджест через {wait_seconds/3600:.1f} год "
            f"(п'ятниця {target.strftime('%d.%m.%Y')} о 09:00)"
        )

        await asyncio.sleep(wait_seconds)

        logger.info("📰 Формуємо тижневий дайджест новин...")
        try:
            from news_digest import build_news_digest
            text = await build_news_digest()
            await bot.send_message(CHAT_ID, text, parse_mode=ParseMode.HTML)
            logger.info("✅ Тижневий дайджест новин надіслано!")
        except Exception as e:
            logger.error(f"❌ Помилка тижневого дайджесту: {e}")


@dp.message()
async def manual(m: types.Message):
    if m.from_user.id != ADMIN_ID:
        logger.warning(f"❌ Спроба від {m.from_user.id}")
        return

    logger.info(f"👤 Адмін: '{m.text}'")

    if m.text and m.text.strip().lower() in ["/news", "новини", "/digest"]:
        try:
            await m.answer("⏳ Формую тижневий дайджест новин...")
            from news_digest import build_news_digest
            text = await build_news_digest()
            await m.answer(text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"❌ Помилка: {e}")
            await m.answer(f"❌ Помилка: {e}")
        return

    try:
        text = await get_weather_forecast()
        await m.answer(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Помилка: {e}")
        await m.answer("❌ Помилка")


async def main():
    logger.info("🚀 БОТ ЗАПУЩЕНО")
    logger.info(f"⏰ Щоденний дайджест: 19:00")
    if WEEKLY_NEWS_ENABLED:
        logger.info(f"📰 Тижневий дайджест новин: П'ятниця 09:00")
    else:
        logger.info("📰 Автоматична розсилка новин ВИМКНЕНА (тільки за командою «новини»)")
    logger.info(f"👤 ADMIN_ID: {ADMIN_ID}")

    asyncio.create_task(daily_task())
    if WEEKLY_NEWS_ENABLED:
        asyncio.create_task(weekly_news_task())

    logger.info("✅ Фонові задачі активні!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
