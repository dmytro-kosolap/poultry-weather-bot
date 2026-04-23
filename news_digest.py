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

RSS_FEEDS = [
    {
        "label": "Птахівництво України",
        "emoji": "🇺🇦",
        "url": "https://news.google.com/rss/search?q=птахівництво+Україна&hl=uk&gl=UA&ceid=UA:uk",
        "pick": 2,
    },
    {
        "label": "Світові тренди галузі",
        "emoji": "🌍",
        "url": "https://news.google.com/rss/search?q=poultry+industry+world+2026&hl=en&gl=US&ceid=US:en",
        "pick": 1,
    },
]

MAX_FETCH = 10  # скільки тягнемо з RSS для вибору


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

                for title in titles[:MAX_FETCH]:
                    clean = title.split(' - ')[0].strip()
                    clean = clean.replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")
                    if clean:
                        items.append(clean)

                logger.info(f"✅ RSS '{feed['label']}': {len(items)} новин отримано")
    except Exception as e:
        logger.warning(f"❌ RSS '{feed['label']}': {e}")
    return items


async def select_and_comment(label, items, pick):
    """Gemini відбирає N найрелевантніших новин і коментує кожну"""
    if not items:
        return []
    try:
        news_list = "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))

        prompt = f"""Ти — експерт з птахівництва та агроринку України.
Тобі надано список новин по темі "{label}":

{news_list}

Завдання:
1. Вибери {pick} найбільш важливі та релевантні новини для українського птахівника
2. Для кожної вибраної новини напиши: номер оригінальної новини та одне коротке речення — суть для птахівника

Формат відповіді (суворо):
НОВИНА: [точний заголовок новини]
КОМЕНТАР: [одне речення суті]

Повтори блок {pick} рази. Без вступів, без підсумків. Українською мовою."""

        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt
        )

        text = resp.text.strip().replace('**', '')
        logger.info(f"✅ Gemini '{label}': вибрано {pick} новини")

        # Парсимо відповідь
        result = []
        blocks = re.split(r'\n(?=НОВИНА:)', text)
        for block in blocks:
            title_match = re.search(r'НОВИНА:\s*(.+)', block)
            comment_match = re.search(r'КОМЕНТАР:\s*(.+)', block)
            if title_match and comment_match:
                title = title_match.group(1).strip()
                comment = comment_match.group(1).strip()
                result.append((title, comment))

        # Якщо парсинг не вийшов — повертаємо перші N оригінальних
        if not result:
            logger.warning(f"⚠️ Не вдалось розпарсити відповідь Gemini для '{label}'")
            return [(items[i], "") for i in range(min(pick, len(items)))]

        return result[:pick]

    except Exception as e:
        logger.error(f"❌ Gemini '{label}': {e}")
        return [(items[i], "") for i in range(min(pick, len(items)))]


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
        pick = feed["pick"]
        items = news_by_topic.get(label, [])

        message += f"\n{emoji} <b>{label}:</b>\n"

        if not items:
            message += "Новин не знайдено.\n"
            continue

        selected = await select_and_comment(label, items, pick)

        for title, comment in selected:
            if len(title) > 120:
                title = title[:117] + "..."
            message += f"\n📰 <b>{title}</b>\n"
            if comment:
                message += f"↳ {comment}\n"

    message += "\n" + "―" * 14 + "\n"
    message += "📰 <b>Джерела:</b> "
    message += '<a href="https://agravery.com/uk/posts/category/show?slug=ptakhivnytstvo">Agravery</a> • '
    message += '<a href="https://latifundist.com">Latifundist</a> • '
    message += '<a href="https://news.google.com/search?q=птахівництво+Україна&hl=uk">Google News</a>'
    message += "\n\n<b>Вдалих вихідних! 🐔</b>"

    logger.info(f"✅ Дайджест новин сформовано: {len(message)} симв.")
    return message
