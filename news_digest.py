cat > ~/poultry-weather-bot/news_digest.py << 'ENDOFFILE'
import asyncio
import logging
from datetime import datetime
import pytz
from google import genai
from google.genai import types
import os
import re
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY)

GEMINI_RETRY = 3
GEMINI_DELAY = 15


async def gemini_call(prompt, use_search=False):
    for attempt in range(GEMINI_RETRY):
        try:
            config = None
            if use_search:
                config = types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config=config
            )
            return response.text.strip()
        except Exception as e:
            if ('429' in str(e) or '503' in str(e)) and attempt < GEMINI_RETRY - 1:
                logger.warning(f"Gemini {str(e)[:3]} чекаємо {GEMINI_DELAY}с")
                await asyncio.sleep(GEMINI_DELAY)
            else:
                logger.error(f"Gemini: {e}")
                return None
    return None


async def get_ukraine_poultry_news():
    raw = await gemini_call(
        "Знайди останні новини про птахівництво в Україні за цей тиждень",
        use_search=True
    )
    if not raw:
        return None
    logger.info(f"Пошук повернув {len(raw)} симв.")
    await asyncio.sleep(3)
    summary = await gemini_call(
        f"""Ось новини про птахівництво України:\n\n{raw}\n\nВиділи 2 найцікавіші факти цього тижня і напиши їх українською у вигляді 2 коротких речень. Тільки конкретні події, цифри, назви компаній — без загальних фраз і висновків. Якщо свіжих новин немає — напиши: "Без суттєвих новин цього тижня." Рівно 2 речення, не більше.""",
        use_search=False
    )
    if not summary:
        return None
    summary = summary.replace('**', '').replace('*', '').replace('#', '')
    summary = re.sub(r'^\s*[-•]\s*', '', summary, flags=re.MULTILINE)
    return summary.strip()


async def build_news_digest():
    now = datetime.now(pytz.timezone('Europe/Kiev'))
    date_str = now.strftime("%d.%m.%Y")
    message = f"🗞 <b>Тижневий дайджест птахівника</b>\n"
    message += f"📅 <b>{date_str}</b>\n"
    message += "―" * 14 + "\n\n"
    message += "🇺🇦 <b>Птахівництво України:</b>\n"
    news = await get_ukraine_poultry_news()
    if news:
        message += news + "\n"
    else:
        message += "Без суттєвих новин цього тижня.\n"
    message += "\n" + "―" * 14 + "\n"
    message += "🔍 <b>Джерело:</b> Gemini AI + Google Search"
    message += "\n\n<b>Вдалих вихідних! 🐔</b>"
    logger.info(f"Дайджест сформовано: {len(message)} симв.")
    return message
ENDOFFILE
echo "Готово!" && systemctl restart poultry-bot
