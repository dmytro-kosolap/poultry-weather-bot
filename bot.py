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
        {"reg": "Центр-Схід", "name": "Дніпро", "eng": "Dnipro"}
    ]

    tomorrow = datetime.now() + timedelta(days=1)
    date_str = tomorrow.strftime("%d.%m.%Y")
    iso_date = tomorrow.strftime("%Y-%m-%d")

    report = f"🐔 <b>Інформаційний дайджест Птахівника</b>\n📅 <b>{date_str}</b>\n\n"
    report += "☁️ <b>ПОГОДА НА ЗАВТРА:</b>\n"
    report += "<code>Регіон (Місто)      День | Ніч</code>\n"

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
                    report += f"{icon} <code>{(c['reg']+' ('+c['name']+')').ljust(17)} {fmt(d)}° | {fmt(n)}°</code>\n"
                    weather_lines_for_prompt.append(
                        f"{c['reg']} ({c['name']}): день {d}°C, ніч {n}°C, {wd}"
                    )
            except Exception as e:
                logger.error(f"Помилка {c['name']}: {e}")
                report += f"❌ <code>{c['name'].ljust(17)} помилка</code>\n"

    # --- Отримуємо grain context і дані для Gemini ---
    grain_info = ""
    grain_data_for_prompt = ""

    try:
        from grain_context import get_grain_context, get_nbu_rates, get_fuel_prices, get_grain_prices

        async with aiohttp.ClientSession() as session:
            rates = await get_nbu_rates(session)
            fuel = await get_fuel_prices(session)
        grain_prices = get_grain_prices()

        usd = rates.get("USD", 41.5)
        eur = rates.get("EUR", 0)
        pln = rates.get("PLN", 0)

        wheat_line = next(
            (f"~${p:.0f}/т (~{p*usd:,.0f} грн/т), динаміка {ch:+.1f}%"
             for n, p, ch, _ in grain_prices if "Пшениця" in n and ch is not None),
            "немає даних"
        )
        corn_line = next(
            (f"~${p:.0f}/т (~{p*usd:,.0f} грн/т), динаміка {ch:+.1f}%"
             for n, p, ch, _ in grain_prices if "Кукурудза" in n and ch is not None),
            "немає даних"
        )

        fuel_a95 = fuel.get("A95", "–")
        fuel_dp = fuel.get("ДП", "–")

        weather_summary = "\n".join(weather_lines_for_prompt) if weather_lines_for_prompt else "дані відсутні"

        grain_data_for_prompt = f"""Погода на завтра по регіонах України:
{weather_summary}

Курси НБУ: USD={usd:.2f} грн, EUR={eur:.2f} грн, PLN={pln:.2f} грн

Ціни на зерно (CME):
- Пшениця: {wheat_line}
- Кукурудза: {corn_line}

Ціни на паливо (УкрНафта):
- А-95: {fuel_a95} грн/л
- Дизель: {fuel_dp} грн/л"""

        grain_info = await get_grain_context()
        logger.info("✅ Grain context отримано")

    except Exception as e:
        logger.warning(f"Grain context failed: {e}")

    # --- Gemini: порада птахівнику ---
    advice = ""
    try:
        prompt = f"""Ти — досвідчений консультант з птахівництва в Україні.
На основі актуальних даних дай ОДНУ конкретну практичну пораду птахівнику на завтра.

{grain_data_for_prompt}

Вимоги до поради:
- 2-3 речення, чітко і по справі
- Враховуй реальні дані (погода, курс, ціни на корм/паливо)
- Практична дія: що САМЕ зробити завтра
- Без зайвих слів, без вступу типу "Рекомендую" або "Порада:"
- Тільки текст, без форматування і символів"""

        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt
        )

        advice_text = resp.text.strip().replace('\n', ' ').replace('  ', ' ')
        advice_text = advice_text.strip('"').strip("'").strip()

        if len(advice_text) > 400:
            advice_text = advice_text[:397].rsplit(' ', 1)[0] + "..."

        logger.info(f"✅ Порада Gemini: {len(advice_text)} симв.")
        advice = f"\n\n💡 <b>ПОРАДА НА ЗАВТРА:</b> {advice_text}"

    except Exception as e:
        logger.error(f"❌ Gemini: {e}")
        import random
        backup = [
            "Перевірте температуру і вентиляцію в пташнику — різкі перепади погоди впливають на імунітет птиці.",
            "Проконтролюйте залишки корму: при зміні цін на зерно варто скоригувати рецептуру раціону.",
            "Огляньте поголів'я на наявність стресових ознак — зміна погоди може спровокувати зниження несучості.",
            "Перевірте запаси ліків і вітамінів — своєчасна профілактика дешевша за лікування.",
            "Зверніть увагу на споживання води птицею: в холодну погоду потреба у воді зростає."
        ]
        advice = f"\n\n💡 <b>ПОРАДА НА ЗАВТРА:</b> {random.choice(backup)}"

    # --- Збираємо фінальне повідомлення ---
    result = report
    if grain_info:
        result += f"\n{grain_info}"
    result += advice
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

        # weekday(): 0=Пн, 1=Вт, 2=Ср, 3=Чт, 4=Пт, 5=Сб, 6=Нд
        days_until_friday = (4 - now.weekday()) % 7
        target = now.replace(hour=9, minute=0, second=0, microsecond=0)
        target += timedelta(days=days_until_friday)

        # Якщо сьогодні п'ятниця і вже після 9:00 — наступна п'ятниця
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

    # Команда для тесту тижневого дайджесту новин
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

    # Стандартний щоденний дайджест
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
