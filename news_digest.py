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

MAX_NEWS_PER_TOPIC = 5
MAX_TG_LENGTH = 4000  # Telegram ліміт 4096, беремо з запасом

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


async def fetch_rss(session, feed):
    items = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get(feed["url"], headers=headers, timeout=15) as resp:
            if resp.status == 200:
                text = await resp.text()

                titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', text)
                if not titles:
                    titles = re.findall(r'<title>(.*?)</title>', text)
                    titles = titles[1:]

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
    if not items:
        return None
    try:
        news_list = "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))

        prompt = f"""Ти — експерт з птахівництва та агроринку.
Тобі надано список новин по темі "{label}".

{news_list}

Для кожної новини напиши ОДНЕ дуже коротке речення (до 10 слів) — суть для птахівника.
Формат: нумерований список, рівно стільки пунктів скільки новин.
Без вступів, без підсумків. Українською мовою."""

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

    for feed in RSS_FEEDS:
        label = feed["label"]
        emoji = feed["emoji"]
        items = news_by_topic.get(label, [])

        block = f"\n{emoji} <b>{label}:</b>\n"

        if not items:
            block += "Новин не знайдено.\n"
            message += block
            continue

        summary = await summarize_topic_with_gemini(label, items)

        gemini_comments = []
        if summary:
            lines = summary.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                clean = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                if clean:
                    gemini_comments.append(clean)

        for i, title in enumerate(items):
            comment = gemini_comments[i] if i < len(gemini_comments) else ""
            # Обрізаємо заголовок якщо дуже довгий
            if len(title) > 100:
                title = title[:97] + "..."
            block += f"\n📰 <b>{title}</b>\n"
            if comment:
                block += f"↳ {comment}\n"

        # Перевіряємо чи не перевищимо ліміт
        if len(message) + len(block) < MAX_TG_LENGTH:
            message += block
        else:
            logger.warning(f"⚠️ Пропускаємо блок '{label}' — перевищення ліміту")

    message += "\n" + "―" * 14 + "\n"
    message += "📰 <b>Джерела:</b> "
    message += '<a href="https://agravery.com/uk/posts/category/show?slug=ptakhivnytstvo">Agravery</a> • '
    message += '<a href="https://latifundist.com">Latifundist</a> • '
    message += '<a href="https://news.google.com/search?q=птахівництво+Україна&hl=uk">Google News</a>'
    message += "\n\n<b>Вдалих вихідних! 🐔</b>"

    logger.info(f"✅ Дайджест новин сформовано: {len(message)} симв.")
    return message
