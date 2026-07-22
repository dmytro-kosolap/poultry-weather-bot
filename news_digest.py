import asyncio
import logging
from datetime import datetime
import pytz
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY)

GEMINI_RETRY = 3
GEMINI_DELAY = 15

# Теми для пошуку
TOPICS = [
    {
        "label": "Птахівництво України",
        "emoji": "🇺🇦",
        "query": "птахівництво Україна новини за останній тиждень 2026"
    },
    {
        "label": "Світові тренди галузі",
        "emoji": "🌍",
        "query": "poultry industry world news this week 2026"
    },
    {
        "label": "Законодавство та держпідтримка",
        "emoji": "📋",
        "query": "агросектор птахівництво закон субсидія держпідтримка Україна 2026 останні новини"
    },
]


async def search_and_summarize(topic):
    """Gemini сам шукає новини через Google Search і робить огляд"""
    label = topic["label"]
    query = topic["query"]

    for attempt in range(GEMINI_RETRY):
        try:
            prompt = f"""Ти — експерт з птахівництва та агроринку України.
Знайди та проаналізуй актуальні новини за темою "{label}" за останні 7 днів.

Запит для пошуку: {query}

Напиши зв'язний огляд з 3-4 речень українською мовою:
- Конкретні факти, цифри, назви компаній або регіонів якщо є
- Що це означає для українського птахівника
- Без вступів типу "За цей тиждень..." або "Згідно з пошуком..."
- Без форматування (без *, без #, без списків)
- Якщо актуальних новин немає — напиши: "Без суттєвих новин цього тижня."
- Тільки суцільний текст"""

            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )

            text = response.text.strip()
            # Прибираємо markdown форматування
            text = text.replace('**', '').replace('*', '').replace('##', '').replace('#', '')
            text = text.strip()

            logger.info(f"✅ Gemini Search '{label}': {len(text)} симв.")
            return text

        except Exception as e:
            if '429' in str(e) and attempt < GEMINI_RETRY - 1:
                logger.warning(f"⚠️ Gemini 429 — чекаємо {GEMINI_DELAY}с (спроба {attempt+1}/{GEMINI_RETRY})")
                await asyncio.sleep(GEMINI_DELAY)
            elif '503' in str(e) and attempt < GEMINI_RETRY - 1:
                logger.warning(f"⚠️ Gemini 503 — чекаємо {GEMINI_DELAY}с (спроба {attempt+1}/{GEMINI_RETRY})")
                await asyncio.sleep(GEMINI_DELAY)
            else:
                logger.error(f"❌ Gemini Search '{label}': {e}")
                return None

    return None


async def build_news_digest():
    now = datetime.now(pytz.timezone('Europe/Kiev'))
    date_str = now.strftime("%d.%m.%Y")

    message = f"🗞 <b>Тижневий дайджест птахівника</b>\n"
    message += f"📅 <b>{date_str}</b>\n"
    message += "―" * 14 + "\n"

    for i, topic in enumerate(TOPICS):
        label = topic["label"]
        emoji = topic["emoji"]

        message += f"\n{emoji} <b>{label}:</b>\n"

        # Затримка між запитами щоб уникнути 429
        if i > 0:
            await asyncio.sleep(8)

        summary = await search_and_summarize(topic)

        if summary:
            message += summary + "\n"
        else:
            message += "Без суттєвих новин цього тижня.\n"

    message += "\n" + "―" * 14 + "\n"
    message += "🔍 <b>Джерело:</b> Gemini AI + Google Search"
    message += "\n\n<b>Вдалих вихідних! 🐔</b>"

    logger.info(f"✅ Дайджест новин сформовано: {len(message)} симв.")
    return message
