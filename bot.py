import os
import asyncio
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Ініціалізація
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

ADMIN_ID = 708323174
WEATHER_API_KEY = "654e58f000300185e490586e3097c21e"

def get_weather_data():
    """Отримує чисті дані погоди без допомоги ШІ"""
    cities = {
        "Центр (Київ)": "Kyiv",
        "Південь (Одеса)": "Odesa",
        "Захід (Львів)": "Lviv",
        "Схід (Харків)": "Kharkiv",
        "Північ (Чернігів)": "Chernihiv"
    }
    results = {}
    for region, city in cities.items():
        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=uk"
            res = requests.get(url, timeout=10).json()
            temp = round(res['main']['temp'])
            desc = res['weather'][0]['description']
            results[region] = f"{temp}°C ({desc})"
        except:
            results[region] = "?°C (дані відсутні)"
    return results

@dp.message(Command("weather"))
@dp.message(lambda message: message.text == "🌤 Прогноз погоди")
async def send_weather(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    # 1. Спочатку отримуємо реальні цифри
    weather_info = get_weather_data()
    
    # 2. Формуємо базу повідомлення
    text = "📅 Метеозведення для птахівників\n\n"
    for region, info in weather_info.items():
        text += f"📍 {region}: {info}\n"
    
    text += "\n--- 📝 ПОРАДА ВІД ШІ --- \n"

    # 3. Намагаємося отримати пораду від ШІ
    try:
        prompt = f"На основі цієї погоди в Україні: {weather_info}, дай коротку професійну пораду птахівнику на завтра."
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        text += response.text
    except Exception as e:
        text += "У зв'язку з погодними умовами рекомендуємо посилити раціон та стежити за підстилкою. (ШІ тимчасово недоступний)"

    await message.answer(text + "\n\n🔗 kormikorm.com.ua")

async def main():
    print("Бот запущений (Цифри тепер працюють автономно!)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
