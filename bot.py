import asyncio
import aiohttp
import aiocron
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from openai import OpenAI

# === ТВОЇ ДАНІ ===
TOKEN = "8049414176:AAGDwkRxqHU3q9GdZPleq3c4-V2Aep3nipw"
WEATHER_KEY = "d51d1391f46e9ac8d58cf6a1b908ac66"
DEEPSEEK_KEY = "sk-922836d3a6b94ab9a43ce0b9934b5d4d"

# Налаштування клієнта з жорстким таймаутом (15 сек)
client = OpenAI(
    api_key=DEEPSEEK_KEY.strip(), 
    base_url="https://api.deepseek.com",
    timeout=15.0
)

bot = Bot(token=TOKEN)
dp = Dispatcher()

ICONS = {"ясно": "☀️", "хмарно": "☁️", "хмарність": "⛅", "дощ": "🌧", "сніг": "❄️", "туман": "🌫", "злива": "🌦"}

async def get_weather_forecast():
    cities = {"Київ": "Kyiv", "Одеса": "Odesa", "Львів": "Lviv", "Харків": "Kharkiv", "Чернігів": "Chernihiv"}
    tomorrow_dt = datetime.now() + timedelta(days=1)
    tomorrow_str = tomorrow_dt.strftime("%Y-%m-%d")
    
    report = f"📅 <b>ПРОГНОЗ НА ЗАВТРА ({tomorrow_str})</b>\n\n"
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
                            if tomorrow_str in entry['dt_txt']:
                                if "12:00:00" in entry['dt_txt']:
                                    d_t = round(entry['main']['temp'])
                                    desc = entry['weather'][0].get('description', 'хмарно')
                                if "00:00:00" in entry['dt_txt']:
                                    n_t = round(entry['main']['temp'])
                        
                        icon = "☁️"
                        for k, v in ICONS.items():
                            if k in desc.lower(): icon = v; break
                        
                        report += f"{icon} <b>{name}</b>: День {d_t}° | Ніч {n_t}°\n"
                        summary_for_ai += f"{name}: {d_t}/{n_t}C, {desc}. "
            except:
                report += f"❌ {name}: помилка мережі\n"

    # --- БЛОК DEEPSEEK ---
    try:
        # Використовуємо спрощений промпт, щоб уникнути помилок кодування
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ти птахівник. Напиши розгорнуту пораду українською на 800 символів. Не використовуй символи * або _."},
                {"role": "user", "content": f"Погода завтра: {summary_for_ai}"}
            ]
        )
        content = response.choices[0].message.content
        advice = f"\n📝 <b>ПОРАДИ ПТАХІВНИКАМ:</b>\n\n{content}"
    except Exception as e:
        # Якщо впало — ми побачимо причину в терміналі
        print(f"ERROR DeepSeek: {e}")
        advice = f"\n\n⚠️ Порада від ШІ зараз недоступна. Технічна помилка: {str(e)[:50]}"

    return report + advice

@aiocron.crontab('0 19 * * *')
async def scheduled_post():
    res = await get_weather_forecast()
    await bot.send_message(-1001761937362, res, parse_mode=ParseMode.HTML)

@dp.message()
async def handle_message(message: types.Message):
    if message.from_user.id == 708323174:
        status_msg = await message.answer("🕒 Зв'язуюсь із DeepSeek, зачекайте...")
        full_report = await get_weather_forecast()
        try:
            await status_msg.edit_text(full_report, parse_mode=ParseMode.HTML)
        except:
            await status_msg.edit_text(full_report)

async def main():
    print("🚀 ЕТАЛОН v4 АКТИВОВАНО. Чекаю повідомлення...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())




