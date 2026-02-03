import asyncio
import aiohttp
import aiocron
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from google import genai

# === ТВОЇ ДАНІ ===
TOKEN = "8049414176:AAGDwkRxqHU3q9GdZPleq3c4-V2Aep3nipw"
WEATHER_KEY = "d51d1391f46e9ac8d58cf6a1b908ac66"
GEMINI_KEY = "AIzaSyCI6btpcCFZIrrsq9CzaVMwnb3ckpztpk0" 

client = genai.Client(api_key=GEMINI_KEY.strip())
bot = Bot(token=TOKEN)
dp = Dispatcher()

ICONS = {"ясно": "☀️", "хмарно": "☁️", "хмарність": "⛅", "дощ": "🌧", "сніг": "❄️", "туман": "🌫", "злива": "🌦"}

async def get_weather_forecast():
    cities = {"Київ": "Kyiv", "Одеса": "Odesa", "Львів": "Lviv", "Харків": "Kharkiv", "Чернігів": "Chernihiv"}
    # Чітко визначаємо дату ЗАВТРА
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    report = f"📅 <b>ПРОГНОЗ НА ЗАВТРА ({tomorrow_date})</b>\n\n"
    summary_text = ""

    async with aiohttp.ClientSession() as session:
        for name, eng in cities.items():
            url = f"http://api.openweathermap.org/data/2.5/forecast?q={eng}&appid={WEATHER_KEY}&units=metric&lang=uk"
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        d_t, n_t, desc = "Н/Д", "Н/Д", "хмарно"
                        
                        # Шукаємо прогноз саме на завтрашню дату
                        for entry in data['list']:
                            if tomorrow_date in entry['dt_txt']:
                                # Денна температура (близько полудня)
                                if "12:00:00" in entry['dt_txt']:
                                    d_t = round(entry['main']['temp'])
                                    desc = entry['weather'][0].get('description', 'хмарно')
                                # Нічна температура (найближча до опівночі)
                                if "03:00:00" in entry['dt_txt'] or "00:00:00" in entry['dt_txt']:
                                    n_t = round(entry['main']['temp'])
                        
                        icon = "☁️"
                        for k, v in ICONS.items():
                            if k in desc.lower(): icon = v; break
                        
                        report += f"{icon} <b>{name}</b>: День {d_t}° | Ніч {n_t}°\n"
                        summary_text += f"{name}: {d_t}/{n_t}C. "
            except:
                report += f"❌ {name}: помилка\n"

    # --- БЛОК ШІ (З ОБРОБКОЮ ЗАВИСАНЬ) ---
    try:
        # Промпт максимально простий, щоб не провокувати помилки кодування
        prompt = f"Ти птахівник. Завтра морози: {summary_text}. Дай коротку пораду українською на 500 символів."
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        advice = f"\n📝 <b>ПОРАДИ ПТАХІВНИКАМ:</b>\n\n{response.text}"
    except:
        # Якщо ШІ знову "ляже", видаємо лише прогноз, щоб не псувати повідомлення
        advice = "\n\n⚠️ Порада від ШІ зараз готується. Перевірте обігрів при морозах!"

    return report + advice

# РОЗСИЛКА РІВНО О 19:00
@aiocron.crontab('0 19 * * *')
async def daily_job():
    text = await get_weather_forecast()
    # Відправляємо в канал
    await bot.send_message(-1001761937362, text, parse_mode=ParseMode.HTML)

@dp.message()
async def manual(message: types.Message):
    if message.from_user.id == 708323174:
        # Для ручного тесту
        text = await get_weather_forecast()
        await message.answer(text, parse_mode=ParseMode.HTML)

async def main():
    print(f"🚀 Бот активний. Наступна розсилка о 19:00 (за часом сервера).")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())






