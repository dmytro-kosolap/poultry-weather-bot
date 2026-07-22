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

TOPICS = [
    {
        "label": "Птахівництво України",
        "emoji": "🇺🇦",
        "query": "птахівництво Україна новини 2026 експорт курятина яйця фабрика"
    },
    {
        "label": "Світові тренди галузі",
        "emoji": "🌍",
        "query": "poultry industry world news 2026 production export prices"
    },
    {
        "label": "Законодавство та держпідтримка",
        "emoji": "📋",
        "query": "птахівництво агросектор закон субсидія держпідтримка Україна 2026"
    },
]


async def search_and_summarize(topic):
    """Gemini шукає через Google Search і робить короткий огляд"""
    label = topic["label"]
    query = topic["query"]

    for attempt in range(GEMINI_RETRY):
        try:
            prompt = f"""Зроби пошук за запитом: "{query}"

Знайди конкретні факти та новини за останні 7 днів.
Напиши РІВНО 2 речення українською — не більше і не менше.
Тільки конкретика: цифри, назви компаній, регіони, події. 
Без загальних фраз, без висновків, без порад птахівникам.
Якщо свіжих новин немає — напиши: "Без суттєвих новин цього тижня."
Тільки суцільний текст без форматування, без списків."""

            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )

            text = response.text.strip()
            text = text.replace('**', '').replace('*', '').replace('##', '').replace('#', '')
            # Прибираємо маркери списків
            import re
            text = re.sub(r'^\s*[-•]\s*', '', text, flags=re.MULTILINE)
            text = text.strip()

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
