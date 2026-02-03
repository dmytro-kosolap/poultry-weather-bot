import asyncio
import aiohttp
import aiocron
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from openai import OpenAI
import sys

# === ТВОЇ ДАНІ ===
TOKEN = "8049414176:AAGDwkRxqHU3q9GdZPleq3c4-V2Aep3nipw"
WEATHER_KEY = "d51d1391f46e9ac8d58cf6a1b908ac66"
DEEPSEEK_KEY = "sk-922836d3a6b94ab9a43ce0b9934b5d4d"

# Налаштування з таймаутом, щоб бот не висів вічно
client = OpenAI(
    api_key=DEEPSEEK_KEY.strip(), 
    base_url="https://api.deepseek.com",
    timeout=20.0 
)

bot = Bot(token=TOKEN)
dp = Dispatcher()

async def get_weather_forecast():
    cities = {"Київ": "Kyiv", "Одеса": "Odesa", "Львів": "Lviv", "Харків": "Kharkiv", "Чернігів": "Chernihiv"}
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    report = f"📅 **ПРОГНОЗ НА ЗАВТРА ({tomorrow})**\n\n"
    summary_text = ""

    async with aiohttp.ClientSession() as session:
        for name, eng in cities.items():
            url = f"http://api.openweathermap.org/data/2.5/forecast?q={eng}&appid={WEATHER_KEY}&units=metric&lang=uk"
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        d_t, n_t = "Н/Д", "Н/Д"
                        for entry in data['list']:
                            if tomorrow in entry['dt_txt']:
                                if "12:00:00" in entry['dt_txt']: d_t = round(entry['main']['temp'])
                                if "00:00:00" in entry['dt_txt']: n_t = round(entry['main']['temp'])
                        report += f"📍 **{name}**: День {d_t}° | Ніч {n_t}°\n"
                        summary_text += f"{name}: {d_t}/{n_t}. "
            except Exception as e:
                report += f"❌ {name}: помилка мережі\n"

    # --- ДІАГНОСТИКА DEEPSEEK ---
    print(f"DEBUG: Надсилаю запит до DeepSeek з ключем: {DEEPSEEK_KEY[:5]}***")
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ти птахівник. Дай пораду на 500 символів."},
                {"role": "user", "content": f"Погода: {summary_text}"}
            ]
        )
        advice = f"\n📝 **ПОРАДА:**\n\n{response.choices[0].message.content}"
        print("DEBUG: Відповідь від DeepSeek отримана успішно!")
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        print(f"DEBUG ERROR: {error_type} - {error_msg}")
        advice = f"\n\n❌ **ДІАГНОСТИКА ШІ:**\nТип: {error_type}\nДеталі: {error_msg[:100]}"

    return report + advice

@dp.message()
async def manual(message: types.Message):
    if message.from_user.id == 708323174:
        print(f"DEBUG: Отримано команду від адміна {message.from_user.id}")
        msg = await message.answer("🧪 Запуск діагностики DeepSeek...")
        text = await get_weather_forecast()
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)

async def main():
    print("🚀 ДІАГНОСТИЧНИЙ РЕЖИМ ЗАПУЩЕНО")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())










