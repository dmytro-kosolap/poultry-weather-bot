import asyncio
import logging
import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytz
import aiohttp
import feedparser
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY)

GEMINI_RETRY = 3
GEMINI_DELAY = 15

# --- Налаштування пошуку свіжих новин ---
NEWS_HISTORY_FILE = "news_history.json"
HISTORY_KEEP_DAYS = 35          # скільки днів зберігаємо історію вже показаних новин
FRESH_WINDOW_DAYS = 7           # шукаємо новини за останні N днів

RSS_QUERIES = [
    "птахівництво Україна",
    "виробництво яєць Україна",
    "курятина ціни Україна",
    "МХП птахівництво",
]


async def gemini_call(prompt, use_search=False):
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
                logger.warning(f"Gemini {str(e)[:3]} чекаємо {GEMINI_DELAY}с")
                await asyncio.sleep(GEMINI_DELAY)
            else:
                logger.error(f"Gemini: {e}")
                return None
    return None


# ── Історія вже показаних новин (щоб не повторювати ту саму новину тижнями) ──

def load_news_history():
    try:
        with open(NEWS_HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(days=HISTORY_KEEP_DAYS)).strftime("%Y-%m-%d")
    return [item for item in data if item.get("date", "0000-00-00") >= cutoff]


def save_news_history(history):
    try:
        with open(NEWS_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Не вдалось зберегти історію новин: {e}")


def normalize_title(title):
    t = title.lower()
    t = re.sub(r'[^\w\sа-яіїєґ]', '', t, flags=re.UNICODE)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def is_duplicate(title, history, threshold=0.6):
    """Порівнює заголовок з уже показаними за словесним перекриттям —
    рятує від тієї ж новини (Avesterra, МХП тощо) кілька тижнів поспіль."""
    words = set(normalize_title(title).split())
    if not words:
        return False
    for old in history:
        old_words = set(normalize_title(old.get("title", "")).split())
        if not old_words:
            continue
        overlap = len(words & old_words) / max(len(words), len(old_words))
        if overlap >= threshold:
            return True
    return False


# ── Отримання реальних, датованих заголовків через Google News RSS ──

async def fetch_google_news_rss(session, query, days=FRESH_WINDOW_DAYS):
    url = f"https://news.google.com/rss/search?q={quote(query)}+when:{days}d&hl=uk&gl=UA&ceid=UA:uk"
    try:
        async with session.get(url, timeout=15) as resp:
            if resp.status != 200:
                logger.warning(f"Google News RSS '{query}': HTTP {resp.status}")
                return []
            raw = await resp.text()
    except Exception as e:
        logger.warning(f"Google News RSS помилка ('{query}'): {e}")
        return []

    feed = feedparser.parse(raw)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items = []

    for entry in feed.entries:
        pub = None
        if getattr(entry, "published_parsed", None):
            pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

        # Пропускаємо усе, що старше вікна свіжості — головний захист від
        # застарілих новин, які раніше вигадував/повторював Gemini.
        if pub and pub < cutoff:
            continue

        raw_title = entry.title
        clean_title = re.sub(r'\s+-\s+[^-]+$', '', raw_title)  # прибираємо назву джерела в кінці

        items.append({
            "title": clean_title,
            "link": entry.link,
            "published": pub.strftime("%Y-%m-%d") if pub else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        })

    return items


async def collect_fresh_news():
    history = load_news_history()
    seen_norm = set()
    all_items = []

    async with aiohttp.ClientSession() as session:
        for q in RSS_QUERIES:
            items = await fetch_google_news_rss(session, q)
            for it in items:
                key = normalize_title(it["title"])
                if not key or key in seen_norm:
                    continue
                seen_norm.add(key)
                all_items.append(it)
            await asyncio.sleep(1)  # ввічлива пауза між запитами до Google News

    all_items.sort(key=lambda x: x["published"], reverse=True)

    fresh = [it for it in all_items if not is_duplicate(it["title"], history)]
    logger.info(f"Знайдено {len(all_items)} заголовків, {len(fresh)} нових (без повторів з історії)")
    return fresh, all_items, history


async def get_ukraine_poultry_news():
    fresh, all_items, history = await collect_fresh_news()

    # Якщо все відфільтрувалось як "вже було" — краще взяти найсвіжіше з усього
    # списку, ніж лишити людей зовсім без дайджесту.
    pool = fresh if fresh else all_items
    if not pool:
        return None, [], history

    top_pool = pool[:15]
    listing = "\n".join(f"- [{it['published']}] {it['title']}" for it in top_pool)

    prompt = f"""Ось реальний список заголовків новин про птахівництво України за останній тиждень (з датами публікації):

{listing}

Вибери 2 НАЙЦІКАВІШІ і найконкретніші новини (з цифрами, назвами компаній, конкретними подіями) СУВОРО з цього списку.
Заборонено вигадувати факти або новини, яких немає у списку вище.
Напиши їх українською мовою у вигляді 2 коротких речень — тільки конкретні факти, без загальних фраз і висновків.
Якщо серед заголовків немає жодної достатньо конкретної новини — напиши рівно: "Без суттєвих новин цього тижня."
Рівно 2 речення, не більше."""

    summary = await gemini_call(prompt, use_search=False)
    if not summary:
        return None, [], history

    summary = summary.replace('**', '').replace('*', '').replace('#', '')
    summary = re.sub(r'^\s*[-•]\s*', '', summary, flags=re.MULTILINE)
    return summary.strip(), top_pool[:6], history


async def build_news_digest():
    now = datetime.now(pytz.timezone('Europe/Kiev'))
    date_str = now.strftime("%d.%m.%Y")

    message = "🗞 <b>Тижневий дайджест птахівника</b>\n"
    message += f"📅 <b>{date_str}</b>\n"
    message += "―" * 14 + "\n\n"
    message += "🇺🇦 <b>Птахівництво України:</b>\n"

    news, used_items, history = await get_ukraine_poultry_news()

    if news:
        message += news + "\n"
    else:
        message += "Без суттєвих новин цього тижня.\n"

    # Оновлюємо історію показаних новин, щоб наступного тижня не повторювались
    if used_items:
        today_str = now.strftime("%Y-%m-%d")
        new_history = history + [
            {"title": it["title"], "date": it.get("published", today_str)} for it in used_items
        ]
        save_news_history(new_history)

    message += "\n" + "―" * 14 + "\n"
    message += "🔍 <b>Джерело:</b> Google News + Gemini AI (тільки перевірені за датою заголовки)"
    message += "\n\n<b>Вдалих вихідних! 🐔</b>"

    logger.info(f"Дайджест сформовано: {len(message)} симв.")
    return message
