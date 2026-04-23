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

# Тільки два напрямки
RSS_FEEDS = [
    {
        "label": "Птахівництво України",
        "emoji": "🇺🇦",
        "url": "https://news.google.com/rss/search?q=птахівництво+Україна&hl=uk&gl=UA&ceid=UA:uk"
    },
    {
        "label": "Світові тренди галузі",
        "emoji": "🌍",
        "url": "https://news.google.com/rss/search?q=poultry+industry+world+2026&hl=en&gl=US&ceid=US:en"
    },
]

MAX_NEWS_PER_TOPIC = 10  # беремо більше новин


async def fetch_rss(session, feed):
    """Завантажує RSS і повертає список заголовків"""
    items = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get(feed["url"], headers=headers, timeout=15) as resp:
            if resp.status == 200:
                text = await resp.text()

                # CDATA формат
                titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', text)

                # Звичайний формат
                if not titles:
                    titles = re.findall(r'<title>(.*?)</title>', text)
                    titles = titles[1:]  # пропускаємо назву каналу

                for title in titles[:MAX_NEWS_PER_TOPIC]:
                    clean = title.split(' - ')[0].strip()
                    clean = clean.replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")
                    if clean:
                        items.append(clean)

                logger.info(f"✅ RSS '{feed['label']}': {len(items)} новин")
    except Exception as e:
        logger.warning(f"❌ RSS '{feed['label']}': {e}")
    return items


async def summarize_topic_with_gemini(label, items):
    """Gemini коротко коментує кожну новину окремо"""
    if not items:
        return None
    try:
        news_list = "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))

        prompt = f"""Ти — експерт з птахівництва та агроринку.
Тобі надано список новин по темі "{label}".

{news_list}

Для кожної новини напиши ОДНЕ коротке речення — про що ця новина і чому це важливо для птахівника.
Формат відповіді — нумерований список, рівно стільки пунктів скільки новин.
Без вступів, без підсумків, без зайвих слів.
Відповідай українською мовою."""

        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt
        )

        text = resp.text.strip().replace('**', '')
        logger.info(f"✅ Gemini '{label}': {len(text)} симв.")
        return text

    except Exception as e:
        logger.error(f"❌ Gemini '{label}': {e}")
        return None


async def build_news_digest():
    """Збирає повний тижневий дайджест новин"""
    now = datetime.now(pytz.timezone('Europe/Kiev'))
    date_str = now.strftime("%d.%m.%Y")

    async with aiohttp.ClientSession() as session:
        news_by_topic = {}
        for feed in RSS_FEEDS:
            items = await fetch_rss(session, feed)
            news_by_topic[feed["label"]] = items

    # Заголовок
    message = f"🗞 <b>Тижневий дайджест птахівника</b>\n"
    message += f"📅 <b>{date_str}</b>\n"
    message += "―" * 14 + "\n"

    for feed in RSS_FEEDS:
        label = feed["label"]
        emoji = feed["emoji"]
        items = news_by_topic.get(label, [])

        message += f"\n{emoji} <b>{label}:</b>\n"

        if not items:
            message += "Новин не знайдено.\n"
            continue

        # Отримуємо коментарі від Gemini
        summary = await summarize_topic_with_gemini(label, items)

        if summary:
            # Парсимо нумерований список від Gemini
            lines = summary.split('\n')
            gemini_comments = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Прибираємо нумерацію "1. " "2. " тощо
                clean = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                if clean:
                    gemini_comments.append(clean)

            # Виводимо заголовок новини + коментар Gemini
            for i, title in enumerate(items):
                comment = gemini_comments[i] if i < len(gemini_comments) else ""
                message += f"\n📰 <b>{title}</b>\n"
                if comment:
                    message += f"↳ {comment}\n"
        else:
            # Якщо Gemini не відповів — просто список заголовків
            for title in items:
                message += f"📰 {title}\n"

    # Підвал
    message += "\n" + "―" * 14 + "\n"
    message += "📰 <b>Джерела:</b> "
    message += '<a href="https://agravery.com/uk/posts/category/show?slug=ptakhivnytstvo">Agravery</a> • '
    message += '<a href="https://latifundist.com">Latifundist</a> • '
    message += '<a href="https://news.google.com/search?q=птахівництво+Україна&hl=uk">Google News</a>'
    message += "\n\n<b>Вдалих вихідних! 🐔</b>"

    logger.info(f"✅ Дайджест новин сформовано: {len(message)} симв.")
    return message
