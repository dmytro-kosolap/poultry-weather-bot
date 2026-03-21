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
        "url": "https://news.google.com/rss/search?q=poultry+industry+trends&hl=uk&gl=UA&ceid=UA:uk"
    },
    {
        "label": "Законодавство та держпідтримка",
        "url": "https://news.google.com/rss/search?q=птахівництво+закон+субсидія+держпідтримка+Україна&hl=uk&gl=UA&ceid=UA:uk"
    },
    {
        "label": "Хвороби та спалахи",
        "url": "https://news.google.com/rss/search?q=пташиний+грип+хвороба+птиці+спалах&hl=uk&gl=UA&ceid=UA:uk"
    },
]

MAX_NEWS_PER_TOPIC = 5  # скільки новин беремо з кожного RSS


async def fetch_rss(session, feed):
    """Завантажує RSS і повертає список заголовків + посилань"""
    items = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get(feed["url"], headers=headers, timeout=15) as resp:
            if resp.status == 200:
                text = await resp.text()
                # Простий парсинг XML без бібліотек
                import re
                titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', text)
                links = re.findall(r'<link>(https?://[^<]+)</link>', text)

                # Якщо CDATA не знайдено — спробуємо без нього
                if not titles:
                    titles = re.findall(r'<title>(.*?)</title>', text)
                    # Пропускаємо перший — це назва каналу
                    titles = titles[1:]

                for i, title in enumerate(titles[:MAX_NEWS_PER_TOPIC]):
                    link = links[i] if i < len(links) else ""
                    # Прибираємо назву джерела після " - "
                    clean_title = title.split(' - ')[0].strip()
                    items.append({"title": clean_title, "link": link})

                logger.info(f"✅ RSS '{feed['label']}': {len(items)} новин")
    except Exception as e:
        logger.warning(f"❌ RSS '{feed['label']}': {e}")
    return items


async def generate_digest_with_gemini(news_by_topic):
    """Передає новини в Gemini і отримує структурований дайджест"""
    try:
        # Формуємо блок новин для промпту
        news_text = ""
        for topic, items in news_by_topic.items():
            if items:
                news_text += f"\n### {topic}:\n"
                for item in items:
                    news_text += f"- {item['title']}\n"

        if not news_text.strip():
            return None

        prompt = f"""Ти — експерт з птахівництва в Україні. 
Проаналізуй ці новини за тиждень і склади короткий дайджест українською мовою.

{news_text}

Вимоги:
- Для кожного розділу напиши 2-4 речення — головне, що варто знати птахівнику
- Якщо новин по темі немає або вони нерелевантні — пропусти розділ
- Виділи найважливіше для практики господарства
- Без зайвих вступів, одразу по суті
- Без форматування (без *, без #, без markdown)
- Кожен розділ починай з назви розділу з великої літери і двокрапки

Розділи для аналізу:
1. Птахівництво України
2. Світові тренди галузі  
3. Законодавство та держпідтримка
4. Хвороби та спалахи"""

        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt
        )

        text = resp.text.strip()
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
        # Збираємо новини по всіх темах
        news_by_topic = {}
        for feed in RSS_FEEDS:
            items = await fetch_rss(session, feed)
            news_by_topic[feed["label"]] = items

    # Генеруємо огляд через Gemini
    digest_text = await generate_digest_with_gemini(news_by_topic)

    # Формуємо повідомлення
    message = f"🗞 <b>Тижневий дайджест птахівника</b>\n"
    message += f"📅 <b>{week_str}</b>\n"
    message += "─" * 28 + "\n\n"

    if digest_text:
        # Розбиваємо по розділах і форматуємо
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
            # Перевіряємо чи це заголовок розділу
            matched = False
            for section_name, emoji in sections.items():
                if line.lower().startswith(section_name.lower()):
                    formatted.append(f"{emoji} <b>{line}</b>")
                    matched = True
                    break
            if not matched:
                formatted.append(line)

        message += "\n".join(formatted)
    else:
        message += "⚠️ Не вдалось отримати новини цього тижня."

    # Додаємо посилання на джерела
    message += "\n\n─" * 14 + "\n"
    message += "📰 <b>Джерела:</b>\n"
    message += '• <a href="https://agravery.com/uk/posts/category/show?slug=ptakhivnytstvo">Agravery</a>\n'
    message += '• <a href="https://latifundist.com/rating/top100">Latifundist</a>\n'
    message += '• <a href="https://news.google.com/search?q=птахівництво+Україна&hl=uk">Google News</a>'

    message += "\n\n<b>Гарного тижня! 🐔</b>"

    logger.info(f"✅ Дайджест новин сформовано: {len(message)} симв.")
    return message
