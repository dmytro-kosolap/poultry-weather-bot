import os
import asyncio
import requests
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from dotenv import load_dotenv
import google.generativeai as genai
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone  # Додали для точного часу

# 1. Налаштування
load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

ADMIN_ID = 708323174
GROUP_ID = -1001761937362
RECIPIENTS = [ADMIN_ID, GROUP_ID]

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

# ВАЖЛИВО: Тепер планувальник знає, що ми в Україні
kyiv_tz = timezone("Europe/Kyiv")
scheduler = AsyncIOScheduler(timezone=kyiv_tz)

REGIONS = {
    "Центр (Київ)": "Kyiv",
    "Південь (Одеса)": "Odesa",
    "Захід (Львів)": "Lviv",
    "Схід (Харків)": "Kharkiv",
    "Північ (Чернігів)": "Chernihiv"
}

# 2. Функції (Погода + Поради) - залишаються без змін, як у твоєму файлі
def get_weather(city):
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={os.getenv('WEATHER_API_KEY')}&units=metric&lang=uk"
    r = requests.get(url).json()
    if r.get("cod") != "200": return "Н/Д"
    target = r["list"][8] # прогноз на +24г
    temp = round(target["main"]["temp"])
    desc = target["weather"][0]["description"]
    return f"{temp}°C, {desc}"

async def get_poultry_advice():
    prompt = "Дай коротку професійну пораду на завтра українському птахівнику (про воду, тепло, підстилку або корм). До 300 символів."
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except:
        return "Слідкуйте за чистотою води та температурою у пташнику."

async def send_daily_report(chat_id):
    weather_data = [f"📍 <b>{label}:</b> {get_weather(city)}" for label, city in REGIONS.items()]
    advice = await get_poultry_advice()
    
    report = (
        f"🐣 <b>ЩОДЕННИЙ ЗВІТ ПТАХІВНИКА</b>\n\n"
        f"🌡 <b>Прогноз на завтра:</b>\n" + "\n".join(weather_data) + "\n\n"
        f"--- 📝 <b>ПОРАДИ</b> ---\n{advice}\n\n"
        f"🍀 <i>Вдалого господарювання!</i>\n"
        f"🔗 <a href='https://kormikorm.com.ua'>kormikorm.com.ua</a>"
    )
    try:
        await bot.send_message(chat_id, report, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        print(f"Помилка: {e}")

# 3. Планувальник та Команди
async def scheduled_broadcast():
    for cid in RECIPIENTS:
        await send_daily_report(cid)
        await asyncio.sleep(1)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("✅ Бот активний. Розсилка щодня о 19:00.")

@dp.message(Command("weather"))
async def weather_manual(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await send_daily_report(message.chat.id)

async def main():
    # Налаштовуємо розсилку РІВНО на 19:00 за Києвом
    scheduler.add_job(scheduled_broadcast, 'cron', hour=19, minute=0)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())