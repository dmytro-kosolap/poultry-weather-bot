import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types

# === НАЛАШТУВАННЯ ===
TOKEN = "8049414176:AAGDwkRxqHU3q9GdZPleq3c4-V2Aep3nipw"
WEATHER_KEY = "d51d1391f46e9ac8d58cf6a1b908ac66"
ADMIN_ID = 708323174

bot = Bot(token=TOKEN)
dp = Dispatcher()

async def get_weather():
    cities = {"Київ": "Kyiv", "Одеса": "Odesa", "Львів": "Lviv", "Харків": "Kharkiv", "Чернігів": "Chernihiv"}
    report = "📊 ПОКАЗНИКИ ТЕМПЕРАТУРИ:\n\n"
    async with aiohttp.ClientSession() as session:
        for name, eng in cities.items():
            url = f"http://api.openweathermap.org/data/2.5/weather?q={eng}&appid={WEATHER_KEY}&units=metric&lang=uk"
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        temp = round(data['main']['temp'])
                        report += f"✅ {name}: {temp}°C\n"
                    else:
                        report += f"❌ {name}: помилка\n"
            except:
                report += f"❌ {name}: офлайн\n"
    return report

@dp.message()
async def handle(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        res = await get_weather()
        await message.answer(res)

async def main():
    print("🔥 БОТ ЖИВИЙ! ПИШИ ЙОМУ В ТЕЛЕГРАМ!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
EOF

