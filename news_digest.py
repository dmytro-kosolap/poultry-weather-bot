import asyncio
import aiohttp
import logging
from datetime import datetime
import pytz
from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY)

# Google News RSS feeds
RSS_FEEDS = [
    {
        "label": "Птахівництво України",
        "url": "https://news.google.com/rss/search?q=птахівництво+Україна&hl=uk&gl=UA&ceid=UA:uk"
    },
    {
        "label": "Світові тренди галузі",
        "url": "https://news.google.com/rss/search?q=poultry+industry+world+2026&hl=en&gl=US&ceid=US:en"
    },
    {
        "label": "Законодавство та держпідтримка",
        "url": "https://news.google.com/rss/search?q=агросектор+субсидія+закон+держпідтримка+Україна+2026&hl=uk&gl=UA&ceid=UA:uk"
    },
    {
        "label": "Хвороби та спалахи",
        "url": "https://news.google.com/rss/search?q=пташиний+грип+спалах+птиця+2026&hl=uk&gl=UA&ceid=UA:uk"
    },
]

MAX_NEWS_PER_TOPIC = 5


async def fetch_rss(session, feed):
    """Завантажує RSS і повертає список заголовків"""
    items = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get(feed["url"], headers=headers, timeout=15) as resp:
            if resp.status == 200:
                text = await resp.text()
                import re

                # Спробуємо CDATA формат
                titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', text)

                # Якщо не знайшло — звичайний формат
                if not titles:
                    titles = re.findall(r'<title>(.*?)</title>', text)
                    titles = titles[1:]  # пропускаємо назву каналу

                for title in titles[:MAX_NEWS_PER_TOPIC]:
                    clean_title = title.split(' - ')[0].strip()
                    # Декодуємо HTML entities
                    clean_title = clean_title.replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")
                    if clean_title:
                        items.append(clean_title)

                logger.info(f"✅ RSS '{feed['label']}': {len(items)} новин")
    except Exception as e:
        logger.warning(f"❌ RSS '{feed['label']}': {e}")
    return items


async def generate_digest_with_gemini(news_by_topic):
    """Передає новини в Gemini і отримує структурований дайджест"""
    try:
        news_text = ""
        for topic, items in news_by_topic.items():
            if items:
                news_text += f"\n### {topic}:\n"
                for item in items:
                    news_text += f"- {item}\n"

        if not news_text.strip():
            return None

        prompt = f"""Ти — експерт з птахівництва в Україні.
Проаналізуй ці новини за тиждень і склади короткий дайджест українською мовою.

{news_text}

Вимоги:
- Для кожного розділу напиши 2-4 речення — головне, що варто знати птахівнику
- Якщо новин по темі немає або вони нерелевантні — так і напиши: "Без суттєвих новин цього тижня."
- Виділи найважливіше для практики господарства
- Без зайвих вступів, одразу по суті
- Без будь-якого форматування (без *, без #, без markdown, без дефісів на початку)
- Кожен розділ починай ЛИШЕ з назви розділу і двокрапки, наприклад: "Птахівництво України:"

Розділи:
1. Птахівництво України
2. Світові тренди галузі
3. Законодавство та держпідтримка
4. Хвороби та спалахи"""

        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt
        )

        text = resp.text.strip()
        # Прибираємо markdown форматування яке Gemini іноді додає
        text = text.replace('**', '')
        logger.info(f"✅ Gemini дайджест: {len(text)} симв.")
        return text

    except Exception as e:
        logger.error(f"❌ Gemini дайджест: {e}")
        return None


async def build_news_digest():
    """Збирає повний тижневий дайджест новин"""
    now = datetime.now(pytz.timezone('Europe/Kiev'))
    week_str = now.strftime("%d.%m.%Y")

    async with aiohttp.ClientSession() as session:
        news_by_topic = {}
        for feed in RSS_FEEDS:
            items = await fetch_rss(session, feed)
            news_by_topic[feed["label"]] = items

    digest_text = await generate_digest_with_gemini(news_by_topic)

    # Заголовок
    message = f"🗞 <b>Тижневий дайджест птахівника</b>\n"
    message += f"📅 <b>{week_str}</b>\n"
    message += "―" * 14 + "\n\n"

    if digest_text:
        sections = {
            "Птахівництво України": "🇺🇦",
            "Світові тренди галузі": "🌍",
            "Законодавство та держпідтримка": "📋",
            "Хвороби та спалахи": "⚠️",
        }

        lines = digest_text.split('\n')
        formatted = []
        for line in lines:
            line = line.strip()
            if not line:
                formatted.append("")
                continue
            matched = False
            for section_name, emoji in sections.items():
                if line.lower().startswith(section_name.lower()):
                    # Додаємо порожній рядок перед розділом (крім першого)
                    if formatted:
                        formatted.append("")
                    formatted.append(f"{emoji} <b>{line}</b>")
                    matched = True
                    break
            if not matched:
                formatted.append(line)

        message += "\n".join(formatted)
    else:
        message += "⚠️ Не вдалось отримати новини цього тижня."

    # Підвал з джерелами
    message += "\n\n" + "―" * 14 + "\n"
    message += "📰 <b>Джерела:</b> "
    message += '<a href="https://agravery.com/uk/posts/category/show?slug=ptakhivnytstvo">Agravery</a> • '
    message += '<a href="https://latifundist.com">Latifundist</a> • '
    message += '<a href="https://news.google.com/search?q=птахівництво+Україна&hl=uk">Google News</a>'
    message += "\n\n<b>Вдалих вихідних! 🐔</b>"

    logger.info(f"✅ Дайджест новин сформовано: {len(message)} симв.")
    return message
