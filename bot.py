import asyncio
import aiohttp
import aiocron
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import google.generativeai as genai

# --- ТВОЇ ДАНІ ---
TOKEN = "ТВІЙ_ТОКЕН"
WEATHER_KEY = "d51d1391f46e9ac8d58cf6a1b908ac66"
GEMINI_KEY = "ТВІЙ_GEMINI_KEY"
ADMIN_ID = 708323174
GROUP_ID = -1001761937362

# Налаштування Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

bot = Bot(token=TOKEN)
dp = Dispatcher()

async def get_weather_and_advice():
    cities = {"Київ": "Kyiv", "Одеса": "Odesa", "Львів": "Lviv", "Харків": "Kharkiv", "Чернігів": "Chernihiv"}
    report = "📊 **ПОКАЗНИКИ ТЕМПЕРАТУРИ:**\n\n"
    summary_text = ""

    async with aiohttp.ClientSession() as session:
        for name, eng in cities.items():
            url = f"http://api.openweathermap.org/data/2.5/weather?q={eng}&appid={WEATHER_KEY}&units=metric&lang=uk"
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        temp = round(data['main']['temp'])
                        report += f"✅ {name}: {temp}°C\n"
                        summary_text += f"{name} {temp} градусів; "
            except:
                report += f"❌ {name}: помилка\n"

    # Додаємо пораду від Gemini
    prompt = f"Температура в Україні: {summary_text}. Напиши розгорнуту пораду птахівнику на 800 символів про обігрів та корм."
    try:
        response = model.generate_content(prompt)
        advice = response.text
    except:
        advice = "Помилка зв'язку з ШІ. Перевірте воду та тепло у пташнику."

    final_message = f"{report}\n📝 **ПОРАДА ПТАХІВНИКУ:**\n\n{advice}"
    return final_message

# --- РОЗКЛАД: Щодня о 19:00 ---
@aiocron.crontab('0 19 * * *')
async def scheduled_post():
    text = await get_weather_and_advice()
    await bot.send_message(GROUP_ID, text, parse_mode="Markdown")

# --- РУЧНИЙ ЗАПИТ ---
@dp.message(Command("weather"))
async def manual_weather(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        msg = await message.answer("🔄 Збираю дані...")
        text = await get_weather_and_advice()
        await msg.edit_text(text, parse_mode="Markdown")

async def main():
    print("🚀 Бот запущений! Чекаю на 19:00 або команду /weather")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

