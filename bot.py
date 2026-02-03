import asyncio
import aiohttp
import aiocron
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from openai import OpenAI

# === ТВОЇ ДАНІ (Переконайся, що ключі вірні) ===
TOKEN = "8049414176:AAGDwkRxqHU3q9GdZPleq3c4-V2Aep3nipw"
WEATHER_KEY = "d51d1391f46e9ac8d58cf6a1b908ac66"
DEEPSEEK_KEY = "sk-922836d3a6b94ab9a43ce0b9934b5d4d" # Твій ключ з platform.deepseek.com

# Налаштування DeepSeek
client = OpenAI(
    api_key=DEEPSEEK_KEY.strip(), 
    base_url="https://api.deepseek.com"
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
                                    desc = entry['weather'][0]['description']
                                if "00:00:00" in entry['dt_txt']:
                                    n_t = round(entry['main']['temp'])
                        
                        icon = "☁️"
                        for k, v in ICONS.items():
                            if k in desc.lower(): icon = v; break
                        
                        report += f"{icon} <b>{name}</b>: День {d_t}° | Ніч {n_t}°\n"
                        summary_for_ai += f"{name}: день {d_t}, ніч {n_t}, {desc}. "
            except:
                report += f"❌ {name}: помилка мережі\n"

    # --- БЛОК DEEPSEEK ---
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ти професійний український технолог-птахівник. Дай розгорнуті поради (1000 символів) щодо годівлі, вентиляції та води при вказаній погоді. Використовуй лише простий текст без спеціальних символів розмітки."},
                {"role": "user", "content": f"Склади поради на основі погоди: {summary_for_ai}"}
            ]
        )
        advice = f"\n📝 <b>ПОРАДИ ПТАХІВНИКАМ:</b>\n\n{response.choices[0].message.content}"
    except Exception as e:
        advice = f"\n\n❌ Помилка DeepSeek: Слідкуйте за обігрівом та водою!"

    return report + advice

# Автоматика на 19:00 (використовуємо HTML для надійності)
@aiocron.crontab('0 19 * * *')
async def scheduled_post():
    res = await get_weather_forecast()
    await bot.send_message(-1001761937362, res, parse_mode=ParseMode.HTML)

# Ручна перевірка адміном
@dp.message()
async def handle_message(message: types.Message):
    if message.from_user.id == 708323174:
        status_msg = await message.answer("⏳ DeepSeek готує експертний звіт...")
        full_report = await get_weather_forecast()
        try:
            # Намагаємось відправити з HTML оформленням
            await status_msg.edit_text(full_report, parse_mode=ParseMode.HTML)
        except:
            # Якщо HTML ламається через символи від ШІ, шлемо чистим текстом
            await status_msg.edit_text(full_report)

async def main():
    print("🚀 ЕТАЛОН НА DEEPSEEK ЗАПУЩЕНО! РОЗСИЛКА О 19:00.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())



