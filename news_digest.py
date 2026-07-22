import asyncio
import logging
from datetime import datetime, timedelta
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

TOPICS = [
    {
        "label": "Птахівництво України",
        "emoji": "🇺🇦",
        "query": "птахівництво Україна новини цього тижня"
    },
    {
        "label": "Світові тренди галузі",
        "emoji": "🌍",
        "query": "poultry industry news this week"
    },
    {
        "label": "Законодавство та держпідтримка",
        "emoji": "📋",
        "query": "агросектор птахівництво закон підтримка Україна новини цього тижня"
    },
]


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


async def search_and_summarize(topic):
    """
    Крок 1: Gemini + Google Search — шукає новини без обмежень
    Крок 2: Gemini без Search — стискає результат до 2 речень
    """
    label = topic["label"]
    query = topic["query"]

    # ── Крок 1: чистий пошук ──────────────────────────────────────────
    search_prompt = f"Знайди останні новини та події за запитом: {query}"

    raw_result = await gemini_call(search_prompt, use_search=True)

    if not raw_result:
        logger.warning(f"⚠️ '{label}': пошук не повернув результатів")
        return None

    logger.info(f"🔍 '{label}': знайдено {len(raw_result)} симв.")

    # ── Крок 2: стиснення без пошуку ──────────────────────────────────
    await asyncio.sleep(3)  # невелика пауза між запитами

    summarize_prompt = f"""Ось результати пошуку новин на тему "{label}":

{raw_result}

Виділи 2 найсвіжіші та найважливіші факти і напиши їх українською у вигляді 2 коротких речень.
Тільки конкретні події, цифри, назви — без загальних фраз і висновків.
Якщо в тексті немає свіжих новин цього тижня — напиши: "Без суттєвих новин цього тижня."
Тільки 2 речення, більше нічого."""

    summary = await gemini_call(summarize_prompt, use_search=False)

    if not summary:
        return None

    # Прибираємо markdown на всяк випадок
    summary = summary.replace('**', '').replace('*', '').replace('#', '')
    summary = re.sub(r'^\s*[-•]\s*', '', summary, flags=re.MULTILINE)
    summary = summary.strip()

    logger.info(f"✅ '{label}': підсумок {len(summary)} симв.")
    return summary


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
