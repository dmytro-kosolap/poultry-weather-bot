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
    """Один виклик Gemini з або без Google Search"""
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
                logger.warning(f"⚠️ Gemini {str(e)[:3]} — чекаємо {GEMINI_DELAY}с (спроба {attempt+1}/{GEMINI_RETRY})")
                await asyncio.sleep(GEMINI_DELAY)
            else:
                logger.error(f"❌ Gemini: {e}")
                return None
    return None


async def get_ukraine_poultry_news():
    """
    Крок 1: чистий пошук без обмежень
    Крок 2: стиснення до 2 речень
    """

    # Крок 1 — пошук
    raw = await gemini_call(
        "Знайди останні новини про птахівництво в Україні за цей тиждень",
        use_search=True
    )

    if not raw:
        return None

    logger.info(f"🔍 Пошук повернув {len(raw)} симв.")

    # Крок 2 — стиснення
    await asyncio.sleep(3)

    summary = await gemini_call(
        f"""Ось новини про птахівництво України:

{raw}

Виділи 2 найцікавіші факти цього тижня і напиши їх українською у вигляді 2 коротких речень.
Тільки конкретні події, цифри, назви компаній — без загальних фраз і висновків.
Якщо свіжих новин немає — напиши: "Без суттєвих новин цього тижня."
Рівно 2 речення, не більше.""",
        use_search=False
    )

    if not summary:
        return None

    # Прибираємо markdown
    summary = summary.replace('**', '').replace('*', '').replace('#', '')
    summary = re.sub(r'^\s*[-•]\s*', '', summary, flags=re.MULTILINE)
    summary = summary.strip()

    logger.info(f"✅ Підсумок: {len(summary)} симв.")
    return summary


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

    logger.info(f"✅ Дайджест новин сформовано: {len(message)} симв.")
    return message
