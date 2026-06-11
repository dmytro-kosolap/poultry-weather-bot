import asyncio
import aiohttp
import logging
import re
from datetime import datetime
import pytz
from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY)

GEMINI_RETRY = 3
GEMINI_DELAY = 15

RSS_FEEDS = [
    {
        "label": "Птахівництво України",
        "emoji": "🇺🇦",
        "url": "https://news.google.com/rss/search?q=птахівництво+Україна&hl=uk&gl=UA&ceid=UA:uk",
    },
    {
        "label": "Світові тренди галузі",
        "emoji": "🌍",
        "url": "https://news.google.com/rss/search?q=poultry+industry+world+2026&hl=en&gl=US&ceid=US:en",
    },
    {
        "label": "Законодавство та держпідтримка",
        "emoji": "📋",
        "url": "https://news.google.com/rss/search?q=агросектор+субсидія+закон+держпідтримка+Україна+2026&hl=uk&gl=UA&ceid=UA:uk",
    },
]

MAX_FETCH = 8


async def fetch_rss(session, feed):
    items = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get(feed["url"], headers=headers, timeout=15) as resp:
            if resp.status == 200:
                text = await resp.text()

                item_blocks = re.findall(r'<item>(.*?)</item>', text, re.DOTALL)

                for block in item_blocks[:MAX_FETCH]:
                    title_match = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', block)
                    if not title_match:
                        title_match = re.search(r'<title>(.*?)</title>', block)
                    title = title_match.group(1).strip() if title_match else ""
                    title = title.split(' - ')[0].strip()
                    title = title.replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")

                    # Фільтруємо сміття
                    if len(title) < 20:
                        continue
                    spam_keywords = ['bn market', 'cagr', 'forecast report', 'market size', 'market research']
                    if any(kw in title.lower() for kw in spam_keywords):
                        continue

                    if title:
                        items.append(title)

                logger.info(f"✅ RSS '{feed['label']}': {len(items)} новин")
    except Exception as e:
        logger.warning(f"❌ RSS '{feed['label']}': {e}")
    return items


async def gemini_request(prompt):
    """Запит до Gemini з retry при 429"""
    for attempt in range(GEMINI_RETRY):
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt
            )
            return resp.text.strip().replace('**', '').replace('*', '')
        except Exception as e:
            if '429' in str(e) and attempt < GEMINI_RETRY - 1:
                logger.warning(f"⚠️ Gemini 429 — чекаємо {GEMINI_DELAY}с (спроба {attempt+1}/{GEMINI_RETRY})")
                await asyncio.sleep(GEMINI_DELAY)
            else:
                raise e
    return None


async def summarize_topic(label, items):
    """Gemini пише зв'язний огляд по темі — 3-4 речення"""
    if not items:
        return None
    try:
        news_list = "\n".join(f"- {title}" for title in items)

        prompt = f"""Ти — експерт з птахівництва та агроринку України.
Тобі надано заголовки новин по темі "{label}" за цей тиждень:

{news_list}

Напиши зв'язний огляд з 3-4 речень українською мовою:
- Що відбувається по цій темі
- Що це означає для українського птахівника
- Якщо є конкретні цифри або факти — згадай їх

Вимоги:
- Суцільний текст без списків, без заголовків, без форматування
- Без зайвих вступів типу "За цей тиждень..." або "Згідно з новинами..."
- Якщо новини нерелевантні або порожні — напиши: "Без суттєвих новин цього тижня."
- Тільки текст"""

        text = await gemini_request(prompt)
        logger.info(f"✅ Gemini '{label}': {len(text)} симв.")
        return text

    except Exception as e:
        logger.error(f"❌ Gemini '{label}': {e}")
        return None


async def build_news_digest():
    now = datetime.now(pytz.timezone('Europe/Kiev'))
    date_str = now.strftime("%d.%m.%Y")

    async with aiohttp.ClientSession() as session:
        news_by_topic = {}
        for feed in RSS_FEEDS:
            items = await fetch_rss(session, feed)
            news_by_topic[feed["label"]] = items

    message = f"🗞 <b>Тижневий дайджест птахівника</b>\n"
    message += f"📅 <b>{date_str}</b>\n"
    message += "―" * 14 + "\n"

    for i, feed in enumerate(RSS_FEEDS):
        label = feed["label"]
        emoji = feed["emoji"]
        items = news_by_topic.get(label, [])

        message += f"\n{emoji} <b>{label}:</b>\n"

        if not items:
            message += "Без суттєвих новин цього тижня.\n"
            continue

        # Затримка між запитами до Gemini
        if i > 0:
            await asyncio.sleep(5)

        summary = await summarize_topic(label, items)

        if summary:
            message += summary + "\n"
        else:
            message += "Без суттєвих новин цього тижня.\n"

    message += "\n" + "―" * 14 + "\n"
    message += "📰 <b>Джерела:</b> "
    message += '<a href="https://agravery.com/uk/posts/category/show?slug=ptakhivnytstvo">Agravery</a> • '
    message += '<a href="https://latifundist.com">Latifundist</a> • '
    message += '<a href="https://news.google.com/search?q=птахівництво+Україна&hl=uk">Google News</a>'
    message += "\n\n<b>Вдалих вихідних! 🐔</b>"

    logger.info(f"✅ Дайджест новин сформовано: {len(message)} симв.")
    return message
