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
    
    report = f"📅 <b>ПРОГНОЗ НА ЗАВТРА ({date_rev})</b>\n\n"
    report += "<code>Регіон (Місто)      День | Ніч</code>\n"
    summary_text = ""

    async with aiohttp.ClientSession() as session:
        for item in cities_config:
            url = f"http://api.openweathermap.org/data/2.5/forecast?q={item['eng']}&appid={WEATHER_KEY}&units=metric&lang=uk"
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Збираємо всі температури за завтрашню добу
                        day_temps = []
                        descriptions = []
                        
                        for entry in data['list']:
                            if tomorrow_iso in entry['dt_txt']:
                                day_temps.append(entry['main']['temp'])
                                descriptions.append(entry['weather'][0].get('description', 'хмарно'))
                        
                        if day_temps:
                            d_t = round(max(day_temps)) # Максимум за добу - це День
                            n_t = round(min(day_temps)) # Мінімум за добу - це Ніч
                            desc = descriptions[len(descriptions)//2] # Беремо опис з середини дня
                        else:
                            d_t, n_t, desc = "??", "??", "хмарно"
                        
                        icon = "☁️"
                        for k, v in ICONS.items():
                            if k in desc.lower(): icon = v; break
                        
                        def fmt_temp(t):
                            if isinstance(t, int):
                                if t > 0: return f"+{t}"
                                return str(t)
                            return t

                        city_part = f"{item['reg']} ({item['name']})".ljust(17)
                        day_part = fmt_temp(d_t).rjust(4)
                        night_part = fmt_temp(n_t).rjust(4)
                        
                        report += f"{icon} <code>{city_part} {day_part}° | {night_part}°</code>\n"
                        summary_text += f"{item['name']}: {d_t}/{n_t}C. "
            except:
                report += f"❌ {item['name']}: помилка\n"

    try:
        prompt = f"Ти птахівник. Завтра морози: {summary_text}. Дай розгорнуту пораду українською на 800 символів."
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        advice = f"\n📝 <b>ПОРАДИ ПТАХІВНИКАМ:</b>\n\n{response.text}"
    except:
        advice = "\n\n⚠️ Порада від ШІ зараз готується. Перевірте обігрів при морозах!"

    return report + advice + "\n\n<b>Вдалого господарювання!</b>"

@aiocron.crontab('0 19 * * *')
async def daily_job():
    text = await get_weather_forecast()
    await bot.send_message(-1001761937362, text, parse_mode=ParseMode.HTML)

@dp.message()
async def manual(message: types.Message):
    if message.from_user.id == 708323174:
        text = await get_weather_forecast()
        try:
            await message.answer(text, parse_mode=ParseMode.HTML)
        except:
            await message.answer(text)

async def main():
    print("🚀 ЕТАЛОН v11 (ТОЧНИЙ ПРОГНОЗ) ЗАПУЩЕНИЙ")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())












