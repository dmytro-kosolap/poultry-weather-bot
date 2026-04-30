import asyncio
import aiohttp
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
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

MAX_FETCH = 10
GEMINI_RETRY = 3       # кількість спроб
GEMINI_DELAY = 15      # секунд між спробами


def parse_pub_date(date_str):
    try:
        dt = parsedate_to_datetime(date_str)
        kyiv = pytz.timezone('Europe/Kiev')
        dt_kyiv = dt.astimezone(kyiv)
        return dt_kyiv.strftime("%d.%m.%Y")
    except Exception:
        return ""


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

                    date_match = re.search(r'<pubDate>(.*?)</pubDate>', block)
                    pub_date = parse_pub_date(date_match.group(1).strip()) if date_match else ""

                    # Фільтруємо сміття — надто короткі або рекламні заголовки
                    if len(title) < 20:
                        continue
                    spam_keywords = ['report', 'market size', 'bn market', 'cagr', 'forecast report']
                    if any(kw in title.lower() for kw in spam_keywords):
                        continue

                    if title:
                        items.append((title, pub_date))

                logger.info(f"✅ RSS '{feed['label']}': {len(items)} новин після фільтрації")
    except Exception as e:
        logger.warning(f"❌ RSS '{feed['label']}': {e}")
    return items


async def gemini_request(prompt):
    """Запит до Gemini з retry при 429"""
    for attempt in range(GEMINI_RETRY):
        try:
            resp = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt
            )
            return resp.text.strip().replace('**', '')
        except Exception as e:
            if '429' in str(e) and attempt < GEMINI_RETRY - 1:
                logger.warning(f"⚠️ Gemini 429 — чекаємо {GEMINI_DELAY}с (спроба {attempt+1}/{GEMINI_RETRY})")
                await asyncio.sleep(GEMINI_DELAY)
            else:
                raise e
    return None


async def select_and_comment(label, items, pick):
    if not items:
        return []
    try:
        news_list = "\n".join(f"{i+1}. {title}" for i, (title, _) in enumerate(items))

        prompt = f"""Ти — експерт з птахівництва та агроринку України.
Тобі надано список новин по темі "{label}":

{news_list}

Завдання:
1. Вибери {pick} найбільш важливі та релевантні новини для українського птахівника
2. Для кожної вибраної новини:
   - Напиши покращений заголовок українською — додай деталі якщо знаєш (назви компаній, регіони, цифри)
   - Напиши одне коротке речення — суть для птахівника

Формат відповіді (суворо):
НОВИНА: [покращений заголовок українською]
КОМЕНТАР: [одне речення суті]

Повтори блок {pick} рази. Без вступів, без підсумків."""

        text = await gemini_request(prompt)
        if not text:
            return [(items[i][0], "", items[i][1]) for i in range(min(pick, len(items)))]

        logger.info(f"✅ Gemini '{label}': відповідь отримано")

        result = []
        blocks = re.split(r'\n(?=НОВИНА:)', text)
        for block in blocks:
            title_match = re.search(r'НОВИНА:\s*(.+)', block)
            comment_match = re.search(r'КОМЕНТАР:\s*(.+)', block)
            if title_match and comment_match:
                gemini_title = title_match.group(1).strip()
                comment = comment_match.group(1).strip()

                # Знаходимо дату — шукаємо збіг з оригінальним заголовком
                pub_date = ""
                for orig_title, orig_date in items:
                    if orig_title[:40].lower() in gemini_title[:60].lower() or \
                       gemini_title[:40].lower() in orig_title[:60].lower():
                        pub_date = orig_date
                        break

                result.append((gemini_title, comment, pub_date))

        if not result:
            logger.warning(f"⚠️ Не вдалось розпарсити відповідь Gemini для '{label}'")
            return [(items[i][0], "", items[i][1]) for i in range(min(pick, len(items)))]

        return result[:pick]

    except Exception as e:
        logger.error(f"❌ Gemini '{label}': {e}")
        return [(items[i][0], "", items[i][1]) for i in range(min(pick, len(items)))]


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

        # Затримка між запитами до Gemini щоб уникнути 429
        await asyncio.sleep(5)

        selected = await select_and_comment(label, items, pick)

        for title, comment, pub_date in selected:
            if len(title) > 120:
                title = title[:117] + "..."
            date_tag = f" <i>({pub_date})</i>" if pub_date else ""
            message += f"\n📰 <b>{title}</b>{date_tag}\n"
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
