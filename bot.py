import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types

# ЧИСТІ ДАНІ
TOKEN = "8049414176:AAGXfxG611y9L2p4wNX1VrhZQlXxH_YGiog"
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
                        report += f"❌ {name}: помилка {resp.status}\n"
            except:
                report += f"❌ {name}: сервер офлайн\n"
    return report

@dp.message()
async def send_report(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        data = await get_weather()
        await message.answer(data)

async def main():
    print("Бот запущений. Напиши йому БУДЬ-ЯКЕ слово в Телеграм.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
