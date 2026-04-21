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


async def get_weather_forecast():
    cities = [
        {"reg": "Центр", "name": "Київ", "eng": "Kyiv"},
        {"reg": "Південь", "name": "Одеса", "eng": "Odesa"},
        {"reg": "Захід", "name": "Львів", "eng": "Lviv"},
        {"reg": "Схід", "name": "Харків", "eng": "Kharkiv"},
        {"reg": "Північ", "name": "Чернігів", "eng": "Chernihiv"},
        {"reg": "Центр-Схід", "name": "Дніпро", "eng": "Dnipro"},
        {"reg": "Центр-Південь", "name": "Кривий Ріг", "eng": "Kryvyi Rih"},
    ]

    now = datetime.now(pytz.timezone('Europe/Kiev'))
    today_str = now.strftime("%d.%m.%Y")

    tomorrow = now + timedelta(days=1)
    iso_date = tomorrow.strftime("%Y-%m-%d")

    report = f"🐔 <b>Інформаційний дайджест Птахівника</b>\n📅 <b>{today_str}</b>\n\n"
    report += "☁️ <b>ПОГОДА НА ЗАВТРА:</b>\n"
    report += "<code>Регіон (Місто)        День | Ніч</code>\n"

    weather_lines_for_prompt = []

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
                    report += f"{icon} <code>{(c['reg']+' ('+c['name']+')').ljust(19)} {fmt(d)}° | {fmt(n)}°</code>\n"
                    weather_lines_for_prompt.append(
                        f"{c['reg']} ({c['name']}): день {d}°C, ніч {n}°C, {wd}"
                    )
            except Exception as e:
                logger.error(f"Помилка {c['name']}: {e}")
                report += f"❌ <code>{c['name'].ljust(19)} помилка</code>\n"

    # --- Отримуємо grain context і дані для Gemini ---
    grain_info = ""
    market_data_for_prompt = ""

    try:
        from grain_context import get_grain_context, get_nbu_rates, get_fuel_prices, get_grain_prices
        from grain_context import load_prev_rates, load_prev_fuel, load_prev_poultry

        async with aiohttp.ClientSession() as session:
            rates = await get_nbu_rates(session)
            fuel = await get_fuel_prices(session)
        grain_prices = get_grain_prices()

        usd = rates.get("USD", 41.5)
        eur = rates.get("EUR", 0)

        # Попередні значення для розрахунку змін
        prev_rates = load_prev_rates()
        prev_fuel = load_prev_fuel()
        prev_poultry = load_prev_poultry()

        def fmt_change(curr, prev):
            if prev is None or curr is None:
                return "без змін"
            diff = curr - prev
            if abs(diff) < 0.01:
                return "без змін"
            return f"{'зріс' if diff > 0 else 'впав'} на {abs(diff):.2f}"

        wheat_line = next(
            (f"~${p:.0f}/т, динаміка {ch:+.1f}%"
             for n, p, ch, _ in grain_prices if "Пшениця" in n and ch is not None),
            "без змін"
        )
        corn_line = next(
            (f"~${p:.0f}/т, динаміка {ch:+.1f}%"
             for n, p, ch, _ in grain_prices if "Кукурудза" in n and ch is not None),
            "без змін"
        )

        market_data_for_prompt = f"""Зміни цін сьогодні:

Курси НБУ:
- USD: {usd:.2f} грн ({fmt_change(usd, prev_rates.get('USD'))})
- EUR: {eur:.2f} грн ({fmt_change(eur, prev_rates.get('EUR'))})

Паливо (УкрНафта):
- А-95: {fuel.get('A95', '–')} грн ({fmt_change(fuel.get('A95'), prev_fuel.get('A95'))})
- Дизель: {fuel.get('ДП', '–')} грн ({fmt_change(fuel.get('ДП'), prev_fuel.get('ДП'))})

Зерно (CME):
- Пшениця: {wheat_line}
- Кукурудза: {corn_line}

Продукція птахівництва (Novus):
- Куряче філе: {fmt_change(prev_poultry.get('chicken_fillet'), prev_poultry.get('chicken_fillet'))}
- Філе індички: {fmt_change(prev_poultry.get('turkey_fillet'), prev_poultry.get('turkey_fillet'))}
- Яйця С0 10шт: {fmt_change(prev_poultry.get('eggs_10'), prev_poultry.get('eggs_10'))}"""

        grain_info = await get_grain_context()
        logger.info("✅ Grain context отримано")

    except Exception as e:
        logger.warning(f"Grain context failed: {e}")

    # --- Gemini: коментар ринку ---
    comment = ""
    try:
        prompt = f"""Ти фінансовий коментатор агроринку України.
Тобі надані зміни цін за сьогодні: курси валют, паливо, зерно, куряче філе, філе індички, яйця.

{market_data_for_prompt}

Напиши ОДНЕ речення — що є найважливішим рухом або трендом сьогодні.
Без цифр, без порад, без звернень типу "рекомендую" або "зверніть увагу".
Якщо нічого суттєвого — напиши: "Спокійний день, суттєвих рухів немає.\""""

        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt
        )

        comment_text = resp.text.strip().replace('\n', ' ').replace('  ', ' ')
        comment_text = comment_text.strip('"').strip("'").strip()

        if len(comment_text) > 300:
            comment_text = comment_text[:297].rsplit(' ', 1)[0] + "..."

        logger.info(f"✅ Коментар Gemini: {len(comment_text)} симв.")
        comment = f"\n\n📌 <b>КОМЕНТАР:</b> {comment_text}"

    except Exception as e:
        logger.error(f"❌ Gemini: {e}")
        comment = "\n\n📌 <b>КОМЕНТАР:</b> Спокійний день, суттєвих рухів немає."

    # --- Збираємо фінальне повідомлення ---
    result = report
    if grain_info:
        result += f"\n{grain_info}"
    result += comment
    result += "\n\n<b>Вдалого господарювання! 🐔</b>"

    return result


async def daily_task():
    """Щоденна розсилка о 19:00"""
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
    """Щотижнева розсилка новин у п'ятницю о 9:00"""
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
    logger.info(f"📰 Тижневий дайджест новин: П'ятниця 09:00")
    logger.info(f"👤 ADMIN_ID: {ADMIN_ID}")

    asyncio.create_task(daily_task())
    asyncio.create_task(weekly_news_task())

    logger.info("✅ Фонові задачі активні!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
