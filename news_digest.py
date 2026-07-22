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


def truncate_to_sentences(text, max_sentences=2):
    """Обрізає текст до максимальної кількості речень"""
    # Розбиваємо по крапці/знаку оклику/питання
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s for s in sentences if s.strip()]
    return ' '.join(sentences[:max_sentences])


async def search_and_summarize(topic, week_start, week_end):
    """Gemini шукає через Google Search тільки свіжі новини за поточний тиждень"""
    label = topic["label"]
    query = topic["query"]

    for attempt in range(GEMINI_RETRY):
        try:
            prompt = f"""Пошук: "{query}"

Знайди події або новини які сталися з {week_start} по {week_end}.
ВАЖЛИВО: враховуй ТІЛЬКИ події цього тижня, не раніше {week_start}.
Якщо подія сталась раніше — не згадуй її.

Напиши 2 речення українською з конкретними фактами: цифри, назви компаній, що саме відбулось.
Якщо свіжих новин за цей тиждень немає — напиши тільки: "Без суттєвих новин цього тижня."
Тільки текст, без форматування, без списків, без висновків."""

            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )

            text = response.text.strip()
            # Прибираємо markdown
            text = text.replace('**', '').replace('*', '').replace('##', '').replace('#', '')
            text = re.sub(r'^\s*[-•]\s*', '', text, flags=re.MULTILINE)
            text = text.strip()

            # Жорстко обрізаємо до 2 речень
            if text != "Без суттєвих новин цього тижня.":
                text = truncate_to_sentences(text, max_sentences=2)

            logger.info(f"✅ Gemini Search '{label}': {len(text)} симв.")
            return text

        except Exception as e:
            if ('429' in str(e) or '503' in str(e)) and attempt < GEMINI_RETRY - 1:
                logger.warning(f"⚠️ Gemini {str(e)[:3]} — чекаємо {GEMINI_DELAY}с (спроба {attempt+1}/{GEMINI_RETRY})")
                await asyncio.sleep(GEMINI_DELAY)
            else:
                logger.error(f"❌ Gemini Search '{label}': {e}")
                return None

    return None


async def build_news_digest():
    now = datetime.now(pytz.timezone('Europe/Kiev'))
    date_str = now.strftime("%d.%m.%Y")

    # Визначаємо діапазон поточного тижня (пн-пт)
    week_start = (now - timedelta(days=now.weekday())).strftime("%d.%m.%Y")
    week_end = now.strftime("%d.%m.%Y")

    message = f"🗞 <b>Тижневий дайджест птахівника</b>\n"
    message += f"📅 <b>{date_str}</b>\n"
    message += "―" * 14 + "\n"

    for i, topic in enumerate(TOPICS):
        label = topic["label"]
        emoji = topic["emoji"]

        message += f"\n{emoji} <b>{label}:</b>\n"

        if i > 0:
            await asyncio.sleep(8)

        summary = await search_and_summarize(topic, week_start, week_end)

        if summary:
            message += summary + "\n"
        else:
            message += "Без суттєвих новин цього тижня.\n"

    message += "\n" + "―" * 14 + "\n"
    message += "🔍 <b>Джерело:</b> Gemini AI + Google Search"
    message += "\n\n<b>Вдалих вихідних! 🐔</b>"

    logger.info(f"✅ Дайджест новин сформовано: {len(message)} симв.")
    return message
