import os, asyncio, requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from google import genai
from dotenv import load_dotenv

load_dotenv()
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

ADMIN_ID = 708323174
WEATHER_KEY = "654e58f000300185e490586e3097c21e"

def get_real_weather():
    cities = {"Київ": "Kyiv", "Одеса": "Odesa", "Львів": "Lviv", "Харків": "Kharkiv", "Чернігів": "Chernihiv"}
    res_text = ""
    for name, eng in cities.items():
        try:
            r = requests.get(f"http://api.openweathermap.org/data/2.5/weather?q={eng}&appid={WEATHER_KEY}&units=metric&lang=uk").json()
            temp = round(r['main']['temp'])
            res_text += f"📍 {name}: {temp}°C\n"
        except:
            res_text += f"📍 {name}: помилка даних\n"
    return res_text

@dp.message(Command("weather"))
async def send_weather(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    # Спочатку виводимо цифри (це працює завжди!)
    weather_data = get_real_weather()
    final_text = f"📅 Метеозведення на сьогодні:\n\n{weather_data}"
    
    # Спробуємо додати ШІ, якщо вийде
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents="Дай одну пораду птахівнику на сьогодні")
        final_text += f"\n💡 Порада: {response.text}"
    except:
        final_text += "\n💡 Порада: Стежте за температурою в пташнику (ШІ відпочиває)."
    
    await message.answer(final_text + "\n\n🔗 kormikorm.com.ua")

async def main():
    print("Бот запущений. Цифри тепер незалежні від ШІ!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
