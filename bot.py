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
GEMINI_KEY = "AIzaSyCI6btpcCFZIrrsq9CzaVMwnb3ckpztpk0" # Твій ключ Gemini

client = genai.Client(api_key=GEMINI_KEY.strip())
bot = Bot(token=TOKEN)
dp = Dispatcher()

ICONS = {"ясно": "☀️", "хмарно": "☁️", "хмарність": "⛅", "дощ": "🌧", "сніг": "❄️", "туман": "🌫", "злива": "🌦"}

async def get_weather_forecast():
    cities = {"Київ": "Kyiv", "Одеса": "Odesa", "Львів": "Lviv", "Харків": "Kharkiv", "Чернігів": "Chernihiv"}
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    report = f"📅 **ПРОГНОЗ НА ЗАВТРА ({tomorrow})**\n\n"
    summary_text = ""

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
                        summary_text += f"{name}: {d_t} in day, {n_t} at night. " # Використовуємо латиницю для ШІ, щоб уникнути помилок кодування
            except: report += f"❌ {name}: помилка\n"

    # --- ВИПРАВЛЕНИЙ БЛОК GEMINI ---
    try:
        # Формуємо запит так, щоб уникнути проблем з кодуванням
        prompt = f"Poultry expert advice for weather: {summary_text}. Write in UKRAINIAN 1000 symbols."
        response = client.models.generate_content(
            model="gemini-1.5-flash", 
            contents=prompt
        )
        advice = f"\n📝 **ПОРАДИ ПТАХІВНИКАМ:**\n\n{response.text}"
    except Exception as e:
        advice = f"\n\n❌ Помилка Gemini: Перевірте ключ або з'єднання."

    return report + advice

@aiocron.crontab('0 19 * * *')
async def daily_job():
    text = await get_weather_forecast()
    await bot.send_message(-1001761937362, text, parse_mode=ParseMode.MARKDOWN)

@dp.message()
async def manual(message: types.Message):
    if message.from_user.id == 708323174:
        status_msg = await message.answer("🔍 Аналізую морози та готую поради...")
        text = await get_weather_forecast()
        await status_msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)

async def main():
    print("🚀 ЕТАЛОН v3 (UTF-8 FIX) ЗАПУЩЕНО")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())








