import asyncio
import aiohttp
import aiocron
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
import google.generativeai as genai

# === ДАНІ ===
TOKEN = "8049414176:AAGDwkRxqHU3q9GdZPleq3c4-V2Aep3nipw"
WEATHER_KEY = "d51d1391f46e9ac8d58cf6a1b908ac66"
GEMINI_KEY = "AIzaSyAVUWNX8E6nVeu3i7mOM7Qk9IKekFduxkk" 

# Важливо: використовуємо спрощену конфігурацію
genai.configure(api_key=GEMINI_KEY.strip())
model = genai.GenerativeModel('gemini-1.5-flash')

bot = Bot(token=TOKEN)
dp = Dispatcher()

ICONS = {"ясно": "☀️", "хмарно": "☁️", "хмарність": "⛅", "дощ": "🌧", "сніг": "❄️", "туман": "🌫", "злива": "🌦"}

async def get_weather_forecast():
    cities = {"Київ": "Kyiv", "Одеса": "Odesa", "Львів": "Lviv", "Харків": "Kharkiv", "Чернігів": "Chernihiv"}
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    report = f"📅 **ПРОГНОЗ НА ЗАВТРА ({tomorrow})**\n\n"
    summary_for_ai = ""

    async with aiohttp.ClientSession() as session:
        for name, eng in cities.items():
            url = f"http://api.openweathermap.org/data/2.5/forecast?q={eng}&appid={WEATHER_KEY}&units=metric&lang=uk"
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        d_t, n_t, desc = "Н/Д", "Н/Д", "хмарно"
                        for entry in data['list']:
                            if tomorrow in entry['dt_txt']:
                                if "12:00:00" in entry['dt_txt']:
                                    d_t = round(entry['main']['temp'])
                                    desc = entry['weather'][0]['description']
                                if "00:00:00" in entry['dt_txt']:
                                    n_t = round(entry['main']['temp'])
                        
                        icon = "☁️"
                        for k, v in ICONS.items():
                            if k in desc.lower(): icon = v; break
                        
                        report += f"{icon} **{name}**: День {d_t}° | Ніч {n_t}°\n"
                        summary_for_ai += f"{name}: день {d_t}, ніч {n_t}, {desc}. "
            except: report += f"❌ {name}: помилка\n"

    # --- ВИПРАВЛЕНИЙ БЛОК GEMINI ---
    try:
        prompt = (
            f"Ти технолог-птахівник. Прогноз: {summary_for_ai}. "
            "Напиши розгорнуту пораду на 800 символів українською. "
            "Дай конкретні поради щодо калорійності корму при таких морозах та вентиляції."
        )
        # Використовуємо синхронний виклик всередині потоку, щоб уникнути проблем з gRPC
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: model.generate_content(prompt))
        advice = f"\n📝 **ПОРАДИ ПТАХІВНИКАМ:**\n\n{response.text}"
    except Exception as e:
        advice = f"\n\n⚠️ Помилка ШІ: Перевірте налаштування ключа Gemini."

    return report + advice

@aiocron.crontab('0 19 * * *')
async def daily_job():
    text = await get_weather_forecast()
    await bot.send_message(-1001761937362, text, parse_mode=ParseMode.MARKDOWN)

@dp.message()
async def manual(message: types.Message):
    if message.from_user.id == 708323174:
        wait_msg = await message.answer("🔍 Збираю дані та формую експертну пораду...")
        text = await get_weather_forecast()
        await wait_msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())



