import asyncio
import aiohttp
import aiocron
from datetime import datetime, timedelta
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
import google.generativeai as genai

# === ТВОЇ ДАНІ ===
TOKEN = "8049414176:AAGDwkRxqHU3q9GdZPleq3c4-V2Aep3nipw"
WEATHER_KEY = "d51d1391f46e9ac8d58cf6a1b908ac66"
GEMINI_KEY = "AIzaSyCI6btpcCFZIrrsq9CzaVMwnb3ckpztpk0"

# Налаштування Gemini
genai.configure(api_key=GEMINI_KEY)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Словник іконок (автоматично підбирається за описом погоди)
ICONS = {
    "ясно": "☀️", 
    "хмарно": "☁️", 
    "хмарність": "⛅", 
    "дощ": "🌧", 
    "сніг": "❄️", 
    "туман": "🌫", 
    "злива": "🌦",
    "гроза": "⛈"
}

async def get_weather_forecast():
    cities_config = [
        {"reg": "Центр",  "name": "Київ",     "eng": "Kyiv"},
        {"reg": "Південь", "name": "Одеса",    "eng": "Odesa"},
        {"reg": "Захід",  "name": "Львів",    "eng": "Lviv"},
        {"reg": "Схід",   "name": "Харків",   "eng": "Kharkiv"},
        {"reg": "Північ", "name": "Чернігів", "eng": "Chernihiv"}
    ]
    
    tomorrow_dt = datetime.now() + timedelta(days=1)
    date_rev = tomorrow_dt.strftime("%d-%m-%Y")
    tomorrow_iso = tomorrow_dt.strftime("%Y-%m-%d")
    
    report = f"📅 <b>ПОГОДА НА ЗАВТРА ({date_rev})</b>\n\n"
    # Заголовок таблиці
    report += "<code>Регіон (Місто)      День | Ніч</code>\n"
    
    summary_text = ""

    async with aiohttp.ClientSession() as session:
        for item in cities_config:
            url = f"http://api.openweathermap.org/data/2.5/forecast?q={item['eng']}&appid={WEATHER_KEY}&units=metric&lang=uk"
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        day_temps = []
                        descriptions = []
                        
                        for entry in data['list']:
                            if tomorrow_iso in entry['dt_txt']:
                                day_temps.append(entry['main']['temp'])
                                descriptions.append(entry['weather'][0].get('description', 'хмарно'))
                        
                        if day_temps:
                            d_t, n_t = round(max(day_temps)), round(min(day_temps))
                            # Беремо опис погоди на 12:00 дня
                            weather_desc = descriptions[len(descriptions)//2] if descriptions else "хмарно"
                        else:
                            d_t, n_t, weather_desc = 0, 0, "хмарно"
                        
                        # Вибір іконки
                        icon = "☁️"  # Стандартна
                        for key, emoji in ICONS.items():
                            if key in weather_desc.lower():
                                icon = emoji
                                break
                        
                        def fmt(t):
                            res = f"+{t}" if t > 0 else str(t)
                            return res.rjust(4)

                        city_part = f"{item['reg']} ({item['name']})".ljust(17)
                        # Іконка ззовні <code>, щоб не збивати ширину символів
                        report += f"{icon} <code>{city_part} {fmt(d_t)}° | {fmt(n_t)}°</code>\n"
                        summary_text += f"{item['name']}: {d_t}/{n_t}C. "
            except Exception as e:
                print(f"Помилка отримання погоди для {item['name']}: {e}")
                report += f"❌ <code>{item['name'].ljust(17)} помилка</code>\n"

    # Отримання порад від Gemini
    try:
        prompt = f"Ти досвідчений птахівник в Україні. Завтра прогнозуються такі температури: {summary_text}. Дай корисну пораду птахівникам українською мовою на 800 знаків про те, як підготувати курник та доглядати за птицею в таку погоду."
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        advice = f"\n\n📝 <b>ПОРАДИ ПТАХІВНИКАМ:</b>\n\n{response.text}"
    except Exception as e:
        print(f"Помилка Gemini API: {e}")
        advice = "\n\n⚠️ ШІ в режимі сну"

    return report + advice + "\n\n<b>Вдалого господарювання! 🐔</b>"

# Автоматична розсилка о 22:00 за київським часом
@aiocron.crontab('0 22 * * *', tz=pytz.timezone('Europe/Kiev'))
async def daily_job():
    """Щоденна розсилка прогнозу погоди о 22:00 за Києвом"""
    print(f"[{datetime.now()}] Запуск автоматичної розсилки...")
    try:
        text = await get_weather_forecast()
        await bot.send_message(-1001761937362, text, parse_mode=ParseMode.HTML)
        print(f"[{datetime.now()}] Повідомлення успішно надіслано!")
    except Exception as e:
        print(f"[{datetime.now()}] Помилка при розсилці: {e}")

# Ручний запуск (лише для адміністратора)
@dp.message()
async def manual(message: types.Message):
    """Обробка ручного запиту прогнозу"""
    if message.from_user.id == 708323174:
        print(f"[{datetime.now()}] Ручний запит від адміністратора")
        try:
            text = await get_weather_forecast()
            await message.answer(text, parse_mode=ParseMode.HTML)
        except Exception as e:
            print(f"Помилка відправки: {e}")
            await message.answer("❌ Помилка при формуванні прогнозу")

async def main():
    """Головна функція запуску бота"""
    print("=" * 50)
    print("🚀 БОТ ПОГОДИ ДЛЯ ПТАХІВНИКІВ ЗАПУЩЕНО")
    print("=" * 50)
    print(f"⏰ Автоматична розсилка: щодня о 22:00 (Київ)")
    print(f"📍 Група: -1001761937362")
    print(f"👤 Адмін ID: 708323174")
    print("=" * 50)
    
    # Запускаємо cron-задачу
    daily_job.start()
    
    # Запускаємо polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

















