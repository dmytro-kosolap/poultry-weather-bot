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
from bs4 import BeautifulSoup
from googlenewsdecoder import new_decoderv1, decoderv3
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


def mentions_past_year(title, current_year=None):
    """Перевіряє, чи заголовок згадує МИНУЛИЙ рік (2024, 2025...) —
    ознака річного підсумку/ретроспективи, а не новини поточного тижня.
    Публікація може бути свіжою (пройшла фільтр pubDate), але сам текст
    описує старі дані — таке варто відсувати нижче в списку."""
    if current_year is None:
        current_year = datetime.now().year
    years = re.findall(r'\b(19\d{2}|20\d{2})\b', title)
    return any(int(y) < current_year for y in years)


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


# ── Завантаження реального тексту статті (щоб розгорнути новину без вигадок) ──

def _sync_resolve_google_news_url(google_link):
    """Пробуємо два незалежні методи декодування по черзі — вони реверс-інжинірять
    внутрішній API Google, тож якщо один метод зламається через зміни на боці Google,
    є запасний варіант."""
    try:
        result = new_decoderv1(google_link, interval=1)
        if result and result.get("status"):
            url = result.get("decoded_url") or result.get("url")
            if url:
                return url
    except Exception as e:
        logger.warning(f"new_decoderv1 не спрацював: {e}")

    try:
        result = decoderv3(google_link)
        if result and result.get("status"):
            url = result.get("url") or result.get("decoded_url")
            if url:
                return url
    except Exception as e:
        logger.warning(f"decoderv3 не спрацював: {e}")

    return None


async def resolve_article_url(google_link):
    """Посилання з Google News RSS — це зашифрований редірект
    (news.google.com/rss/articles/...), а не пряма адреса статті.
    Декодуємо його в реальний URL видання."""
    try:
        url = await asyncio.to_thread(_sync_resolve_google_news_url, google_link)
        if url:
            return url
        logger.warning(f"Не вдалось декодувати посилання Google News: {google_link[:100]}")
    except Exception as e:
        logger.warning(f"Помилка декодування посилання Google News: {e}")
    return None


async def fetch_article_text(session, google_link, max_chars=3000):
    real_url = await resolve_article_url(google_link)
    if not real_url:
        return None

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with session.get(real_url, headers=headers, timeout=15, allow_redirects=True) as resp:
            if resp.status != 200:
                logger.warning(f"Стаття {real_url}: HTTP {resp.status}")
                return None
            html = await resp.text(errors="ignore")
    except Exception as e:
        logger.warning(f"Не вдалось завантажити статтю ({real_url}): {e}")
        return None

    try:
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            tag.decompose()
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all('p')]
        text = "\n".join(p for p in paragraphs if len(p) > 40)
        if not text:
            return None
        return text[:max_chars]
    except Exception as e:
        logger.warning(f"Помилка парсингу статті ({real_url}): {e}")
        return None


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

    # Спочатку сортуємо за свіжістю дати публікації, а потім піднімаємо наверх
    # новини про поточні події й опускаємо річні підсумки/ретроспективи
    # (стаття може бути опублікована щойно, але описувати дані за минулий рік).
    all_items.sort(key=lambda x: x["published"], reverse=True)
    all_items.sort(key=lambda x: mentions_past_year(x["title"]))  # False(0) -> перед True(1)

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
    listing = "\n".join(f"{i+1}. [{it['published']}] {it['title']}" for i, it in enumerate(top_pool))
    current_year = datetime.now().year

    # --- Крок 1: Gemini обирає 2 найкращі новини зі списку заголовків ---
    select_prompt = f"""Ось список заголовків новин про птахівництво України за останній тиждень (з датами публікації):

{listing}

Обери РІВНО 2 найцікавіші і найконкретніші новини (з цифрами, назвами компаній, конкретними подіями).
Пріоритет — реальні події {current_year} року (відкриття/будівництво, угоди, ціни, експорт).
Уникай річних підсумків/ретроспектив за минулі роки, якщо є новини про поточні події.

Дай відповідь ЛИШЕ у форматі двох номерів зі списку через кому, наприклад: 3,7
Без жодного іншого тексту."""

    selection = await gemini_call(select_prompt, use_search=False)
    chosen_items = []
    if selection:
        nums = re.findall(r'\d+', selection)
        for n in nums[:2]:
            idx = int(n) - 1
            if 0 <= idx < len(top_pool):
                chosen_items.append(top_pool[idx])

    if not chosen_items:
        chosen_items = top_pool[:2]

    # --- Крок 2: тягнемо реальний текст обраних статей ---
    article_texts = []
    async with aiohttp.ClientSession() as session:
        for it in chosen_items:
            text = await fetch_article_text(session, it["link"])
            article_texts.append(text)
            await asyncio.sleep(1)  # ввічлива пауза між запитами до сайтів-джерел

    sections = []
    for it, text in zip(chosen_items, article_texts):
        if text:
            sections.append(
                f"Заголовок: {it['title']} (опубліковано {it['published']})\nТекст статті:\n{text}"
            )
        else:
            sections.append(
                f"Заголовок: {it['title']} (опубліковано {it['published']})\n"
                f"(повний текст статті недоступний — використовуй лише заголовок, не додавай зайвих деталей)"
            )
    joined = "\n\n---\n\n".join(sections)

    # --- Крок 3: розгортаємо кожну новину на 2-3 речення на основі реального тексту ---
    write_prompt = f"""Ось {len(chosen_items)} новини про птахівництво України з текстами статей:

{joined}

Для КОЖНОЇ новини напиши окремий абзац з 2-3 речень українською мовою.
Використовуй лише конкретні факти, цифри, назви компаній — те, що дійсно є в тексті статті
(або тільки в заголовку, якщо текст статті недоступний — тоді пиши коротше, 1 речення, без вигадок).
Нічого не додавай понад надану інформацію.
Онумеруй абзаци (1. ... 2. ...). Без вступних фраз, без висновків, без загальних фраз."""

    summary = await gemini_call(write_prompt, use_search=False)
    if not summary:
        return None, [], history

    summary = summary.replace('**', '').replace('*', '').replace('#', '')
    return summary.strip(), chosen_items, history


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
