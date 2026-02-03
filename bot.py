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
    
    # Початок звіту
    header = f"📅 <b>ПРОГНОЗ НА ЗАВТРА ({date_rev})</b>\n\n"
    # Відкриваємо блок моноширинного тексту для всієї таблиці
    table_content = "Регіон (Місто)      День | Ніч\n"
    table_content += "-------------------------------\n"
    
    summary_text = ""

    async with aiohttp.ClientSession() as session:
        for item in cities_config:
            url = f"http://api.openweathermap.org/data/2.5/forecast?q={item['eng']}&appid={WEATHER_KEY}&units=metric&lang=uk"
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        day_temps = [e['main']['temp'] for e in data['list'] if tomorrow_iso in e['dt_txt']]
                        
                        if day_temps:
                            d_t, n_t = round(max(day_temps)), round(min(day_temps))
                        else:
                            d_t, n_t = 0, 0
                        
                        def fmt(t):
                            res = f"+{t}" if t > 0 else str(t)
                            return res.rjust(4)

                        city_part = f"{item['reg']} ({item['name']})".ljust(17)
                        table_content += f"☁️ {city_part} {fmt(d_t)}° | {fmt(n_t)}°\n"
                        summary_text += f"{item['name']}: {d_t}/{n_t}C. "
            except:
                table_content += f"❌ {item['name']}: помилка\n"

    # Закриваємо моноширинний блок
    full_table = f"<code>{table_content}</code>"

    try:
        prompt = f"Ти птахівник. Завтра морози: {summary_text}. Порада українською на 800 знаків."
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        advice = f"\n📝 <b>ПОРАДИ ПТАХІВНИКАМ:</b>\n\n{response.text}"
    except:
        advice = "\n\n⚠️ Порада від ШІ зараз готується. Перевірте обігрів при морозах!"

    return header + full_table + advice + "\n\n<b>Вдалого господарювання!</b>"

@dp.message()
async def manual(message: types.Message):
    if message.from_user.id == 708323174:
        text = await get_weather_forecast()
        await message.answer(text, parse_mode=ParseMode.HTML)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())













