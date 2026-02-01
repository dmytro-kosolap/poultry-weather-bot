import os
import asyncio
import requests
import html
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from dotenv import load_dotenv
import google.generativeai as genai
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# 1. Налаштування
load_dotenv()

# Налаштування Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('models/gemini-2.5-flash')

# Твої ID
ADMIN_ID = 708323174
GROUP_ID = -1001761937362

# Список для автоматичної розсилки
RECIPIENTS = [ADMIN_ID, GROUP_ID]

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

REGIONS = {
    "Центр (Київ)": "Kyiv",
    "Південь (Одеса)": "Odesa",
    "Захід (Львів)": "Lviv",
    "Схід (Харків)": "Kharkiv",
    "Північ (Чернігів)": "Chernihiv"
}

# 2. Функція отримання прогнозу на 24 години
def get_forecast(city):
    api_key = os.getenv("WEATHER_API_KEY")
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={api_key}&units=metric&lang=ua"
    try:
        r = requests.get(url).json()
        if r.get("cod") != "200": return None
        
        # Аналізуємо найближчі 8 блоків (24 години)
        next_24h = r['list'][:8]
        temps = [item['main']['temp'] for item in next_24h]
        
        return {
            "min": round(min(temps), 1),
            "max": round(max(temps), 1),
            "desc": next_24h[0]['weather'][0]['description'].capitalize(),
            "hum": next_24h[0]['main']['humidity']
        }
    except: return None

# 3. Генерація та відправка звіту
async def send_daily_report(chat_id):
    # Дата на завтра
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
    
    weather_summary = ""
    table_rows = []

    for name, city in REGIONS.items():
        w = get_forecast(city)
        if w:
            table_rows.append(f"📍 <b>{name}</b>: {w['min']}°...{w['max']}°C (<i>{w['desc']}</i>)")
            weather_summary += f"{name}: вночі {w['min']}, вдень {w['max']}, {w['desc']}. "

    prompt = (
        f"Ти головний технолог 'Птахівництва України'. Прогноз на завтра ({tomorrow}): {weather_summary}. "
        "Напиши професійну пораду фермерам (60-90 слів). "
        "Пиши про воду, тепло , підстилку та корм в залежності від погоди."
    )

    try:
        res = model.generate_content(prompt)
        advice = html.escape(res.text.strip())
    except:
        advice = "Забезпечте оптимальний температурний режим та доступ до незамерзаючої води."

    report = (
        f"📅 <b>Метеозведення для птахівників</b>\n"
        f"<b>Прогноз на завтра: {tomorrow}</b>\n\n"
        f"{chr(10).join(table_rows)}\n\n"
        f"--- 📝 <b>ПОРАДИ ПТАХІВНИКАМ</b> ---\n"
        f"{advice}\n\n"
        f"🍀 <i>Вдалого господарювання!</i>\n"
        f"🔗 <a href='https://kormikorm.com.ua'>kormikorm.com.ua</a>"
    )
    
    try:
        await bot.send_message(chat_id, report, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        print(f"Помилка відправки у чат {chat_id}: {e}")

# 4. Функція для планувальника
async def scheduled_broadcast():
    for cid in RECIPIENTS:
        await send_daily_report(cid)
        await asyncio.sleep(1) # пауза для безпеки Telegram

# 5. Команди
@dp.message(Command("weather"))
async def weather_manual(message: types.Message):
    # Дозволяємо ручний запуск тільки тобі (в особисті чи в групі)
    if message.from_user.id == ADMIN_ID:
        await send_daily_report(message.chat.id)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🐣 Бот працює! Авто-звіт прийде о 19:00 тобі та у групу.")

# 6. Запуск
async def main():
    # Запуск розсилки о 19:00
    scheduler.add_job(scheduled_broadcast, 'cron', hour=19, minute=0)
    scheduler.start()
    
    print(f"🚀 Бот запущений. Адмін: {ADMIN_ID}, Група: {GROUP_ID}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())