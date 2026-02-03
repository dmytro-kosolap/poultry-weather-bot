import asyncio
import aiohttp
import aiocron
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
import google.generativeai as genai

# === ТВОЇ ДАНІ ===
TOKEN = "8049414176:AAGDwkRxqHU3q9GdZPleq3c4-V2Aep3nipw"
WEATHER_KEY = "d51d1391f46e9ac8d58cf6a1b908ac66"
GEMINI_KEY = "AIzaSyAVUWNX8E6nVeu3i7mOM7Qk9IKekFduxkk" 

genai.configure(api_key=GEMINI_KEY.strip())
model = genai.GenerativeModel('gemini-1.5-flash')

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Словник іконок
ICONS = {
    "ясно": "☀️", "хмарно": "☁️", "хмарність": "⛅", 
    "дощ": "🌧", "сніг": "❄️", "туман": "🌫", "злива": "🌦"
}

async def get_weather_forecast():
    cities = {"Київ": "Kyiv", "Одеса": "Odesa", "Львів": "Lviv", "Харків": "Kharkiv", "Чернігів": "Chernihiv"}
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    report = f"📅 **ПРОГНОЗ НА ЗАВТРА ({tomorrow_date})**\n\n"
    summary_for_ai = ""

    async with aiohttp.ClientSession() as session:
        for name, eng in cities.items():
            # Використовуємо /forecast замість /weather
            url = f"http://api.openweathermap.org/data/2.5/forecast?q={eng}&appid={WEATHER_KEY}&units=metric&lang=uk"
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        day_temp, night_temp, desc = "Н/Д", "Н/Д", "мінлива хмарність"
                        
                        # Шукаємо прогноз на завтра: 12:00 (день) та 00:00 (ніч)
                        for entry in data['list']:
                            if tomorrow_date in entry['dt_txt']:
                                if "12:00:00" in entry['dt_txt']:
                                    day_temp = round(entry['main']['temp'])
                                    desc = entry['weather'][0]['description']
                                if "00:00:00" in entry['dt_txt']:
                                    night_temp = round(entry['main']['temp'])

                        # Вибір іконки
                        icon = "☁️"
                        for key, emoji in ICONS.items():
                            if key in desc.lower():
                                icon = emoji
                                break
                        
                        report += f"{icon} **{name}**: День {day_temp}° | Ніч {night_temp}°\n"
                        summary_for_ai += f"{name}: день {day_temp}, ніч {night_temp}, {desc}; "
            except:
                report += f"❌ {name}: дані відсутні\n"

    # Запит до Gemini
    prompt = (
        f"Ти експерт-птахівник. Завтра така погода в регіонах: {summary_for_ai}. "
        "Напиши розгорнуту пораду (800 символів). Опиши ризики замерзання води, "
        "потребу в енергії (корм) та вентиляції. Пиши професійно."
    )
    try:
        response = model.generate_content(prompt)
        advice = f"\n📝 **ПОРАДИ ПТАХІВНИКАМ:**\n\n{response.text}"
    except:
        advice = "\n\n⚠️ Порада від ШІ недоступна. Перевірте обігрів."

    return report + advice

@aiocron.crontab('0 19 * * *')
async def daily_job():
    text = await get_weather_forecast()
    await bot.send_message(-1001761937362, text, parse_mode=ParseMode.MARKDOWN)

@dp.message()
async def manual(message: types.Message):
    if message.from_user.id == 708323174:
        wait_msg = await message.answer("🔍 Аналізую метеодані та готую поради...")
        text = await get_weather_forecast()
        await wait_msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)

async def main():
    print("🚀 ПОВНОЦІННИЙ ЕКСПЕРТ ЗАПУЩЕНИЙ!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


