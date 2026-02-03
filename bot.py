import asyncio
import aiohttp
import aiocron
from aiogram import Bot, Dispatcher, types
import google.generativeai as genai

# === ТВОЇ ДАНІ (Еталонні) ===
TOKEN = "8049414176:AAGDwkRxqHU3q9GdZPleq3c4-V2Aep3nipw"
WEATHER_KEY = "d51d1391f46e9ac8d58cf6a1b908ac66"
GEMINI_KEY = "AIzaSyAVUWNX8E6nVeu3i7mOM7Qk9IKekFduxkk" # Твій ключ Gemini
ADMIN_ID = 708323174
GROUP_ID = -1001761937362

# Налаштування Gemini (з чисткою пробілів)
genai.configure(api_key=GEMINI_KEY.strip())
model = genai.GenerativeModel('gemini-1.5-flash')

bot = Bot(token=TOKEN)
dp = Dispatcher()

async def get_full_report():
    cities = {"Київ": "Kyiv", "Одеса": "Odesa", "Львів": "Lviv", "Харків": "Kharkiv", "Чернігів": "Chernihiv"}
    report = "📊 ПОКАЗНИКИ ТЕМПЕРАТУРИ:\n\n"
    summary_for_ai = ""

    async with aiohttp.ClientSession() as session:
        for name, eng in cities.items():
            url = f"http://api.openweathermap.org/data/2.5/weather?q={eng}&appid={WEATHER_KEY}&units=metric&lang=uk"
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        temp = round(data['main']['temp'])
                        report += f"✅ {name}: {temp}°C\n"
                        summary_for_ai += f"{name}: {temp}°C; "
                    else:
                        report += f"❌ {name}: помилка\n"
            except:
                report += f"❌ {name}: офлайн\n"

    # Додаємо пораду ШІ
    try:
        prompt = f"Погода: {summary_for_ai}. Напиши розгорнуту пораду птахівнику (800 символів) про корм та тепло."
        response = model.generate_content(prompt)
        advice = f"\n\n📝 **ПОРАДА ПТАХІВНИКУ:**\n\n{response.text}"
    except:
        advice = "\n\nПорада: Слідкуйте за обігрівом пташників."

    return report + advice

# Автоматика на 19:00
@aiocron.crontab('0 19 * * *')
async def scheduled_post():
    res = await get_full_report()
    await bot.send_message(GROUP_ID, res, parse_mode="Markdown")

@dp.message()
async def handle(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        res = await get_full_report()
        await message.answer(res, parse_mode="Markdown")

async def main():
    print("🔥 ЕТАЛОН ЗАПУЩЕНО! РОЗСИЛКА О 19:00.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())
EOF

