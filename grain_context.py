import logging
import aiohttp
import yfinance as yf
import json
import os
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

WHEAT_BUSHELS_PER_TON = 36.74
CORN_BUSHELS_PER_TON = 39.37
RATES_FILE = "rates_history.json"
FUEL_FILE = "fuel_history.json"
POULTRY_FILE = "poultry_history.json"

# ─── Збереження/завантаження історії ───────────────────────────────────────

def load_prev_rates():
    try:
        with open(RATES_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_rates(rates):
    try:
        with open(RATES_FILE, 'w') as f:
            json.dump(rates, f)
    except Exception as e:
        logger.warning(f"Не вдалось зберегти курси: {e}")

def load_prev_fuel():
    try:
        with open(FUEL_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_fuel(fuel):
    try:
        with open(FUEL_FILE, 'w') as f:
            json.dump(fuel, f)
    except Exception as e:
        logger.warning(f"Не вдалось зберегти ціни палива: {e}")

def load_prev_poultry():
    try:
        with open(POULTRY_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_poultry(data):
    try:
        with open(POULTRY_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Не вдалось зберегти ціни птиці/яєць: {e}")

# ─── НБУ ───────────────────────────────────────────────────────────────────

async def get_nbu_rates(session):
    rates = {}
    try:
        url = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                for item in data:
                    if item["cc"] in ("USD", "EUR", "PLN"):
                        rates[item["cc"]] = item["rate"]
    except Exception as e:
        logger.warning(f"НБУ API недоступний: {e}")
    return rates

# ─── Паливо ────────────────────────────────────────────────────────────────

async def get_fuel_prices(session):
    fuel = {}
    try:
        url = "https://index.minfin.com.ua/ua/markets/fuel/tm/ukrnafta/"
        headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                table = soup.find('table')
                if table:
                    for row in table.find_all('tr'):
                        cols = row.find_all('td')
                        if len(cols) >= 3:
                            name = cols[0].get_text(strip=True)
                            price_text = cols[2].get_text(strip=True).replace(',', '.')
                            try:
                                price = float(price_text)
                                if "А-95 преміум" in name:
                                    pass
                                elif "А-95" in name:
                                    fuel["A95"] = price
                                elif "А-92" in name:
                                    fuel["A92"] = price
                                elif "Дизельне" in name:
                                    fuel["ДП"] = price
                                elif "Газ" in name:
                                    fuel["ГАЗ"] = price
                            except:
                                pass
    except Exception as e:
        logger.warning(f"Помилка отримання цін палива: {e}")
    return fuel

# ─── Ціни на птицю і яйця через АТБ ───────────────────────────────────────

async def _search_atb(session: aiohttp.ClientSession, query: str, max_pages: int = 3) -> list[dict]:
    """
    Шукає товари через АТБ API і повертає список {name, price}.
    АТБ не блокує запити — відкритий каталог.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.atbmarket.com/",
    }
    results = []
    for page in range(1, max_pages + 1):
        url = (
            f"https://www.atbmarket.com/api/catalog/products"
            f"?search={query}&page={page}&limit=20"
        )
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    break
                data = await resp.json(content_type=None)
                # АТБ повертає {"items": [...]} або {"data": {"items": [...]}}
                items = (
                    data.get("items") or
                    data.get("data", {}).get("items") or
                    []
                )
                if not items:
                    break
                for item in items:
                    name = item.get("title") or item.get("name") or ""
                    price = item.get("price") or item.get("current_price") or 0
                    try:
                        price = float(str(price).replace(",", ".").replace(" ", ""))
                    except:
                        continue
                    if price > 0:
                        results.append({"name": name, "price": price})
        except Exception as e:
            logger.warning(f"АТБ пошук '{query}' стор.{page}: {e}")
            break
    return results


def _avg_price(items: list[dict], keywords: list[str], exclude: list[str],
               min_p: float, max_p: float) -> float | None:
    """
    Фільтрує товари за ключовими словами і повертає середню ціну.
    keywords — всі мають бути в назві (AND).
    exclude  — жоден не має бути в назві.
    """
    prices = []
    for item in items:
        name_lower = item["name"].lower()
        if all(kw in name_lower for kw in keywords) and \
           not any(ex in name_lower for ex in exclude):
            p = item["price"]
            if min_p <= p <= max_p:
                prices.append(p)
                logger.debug(f"  → '{item['name']}': {p} грн")
    if not prices:
        return None
    return round(sum(prices) / len(prices), 2)


async def get_poultry_prices(session: aiohttp.ClientSession) -> dict:
    """
    Повертає словник:
      chicken_fillet  — куряче філе, грн/кг
      turkey_fillet   — філе індички, грн/кг
      eggs_10         — яйця С1/С0 10 шт, грн/упак
    Джерело: АТБ (щоденні реальні ціни магазину).
    """
    result = {}

    # ── 1. Куряче філе ──────────────────────────────────────────────
    items_chicken = await _search_atb(session, "філе куряче")
    price = _avg_price(
        items_chicken,
        keywords=["філе", "кур"],
        exclude=["індич", "качин", "качк", "перепел", "рулет", "котлет",
                 "фарш", "марин", "копч", "заморож"],
        min_p=60, max_p=350
    )
    if price:
        result["chicken_fillet"] = price
        logger.info(f"✅ Куряче філе (АТБ): {price} грн/кг")
    else:
        logger.warning("⚠️ Куряче філе (АТБ): не знайдено")

    # ── 2. Філе індички ─────────────────────────────────────────────
    items_turkey = await _search_atb(session, "філе індичка")
    price_t = _avg_price(
        items_turkey,
        keywords=["філе", "індич"],
        exclude=["фарш", "рулет", "котлет", "марин", "копч", "заморож"],
        min_p=80, max_p=500
    )
    if price_t:
        result["turkey_fillet"] = price_t
        logger.info(f"✅ Філе індички (АТБ): {price_t} грн/кг")
    else:
        logger.warning("⚠️ Філе індички (АТБ): не знайдено")

    # ── 3. Яйця (10 шт) ────────────────────────────────────────────
    items_eggs = await _search_atb(session, "яйця курячі 10")
    price_e = _avg_price(
        items_eggs,
        keywords=["яйц"],
        exclude=["перепел", "шоколад", "паска", "декор"],
        min_p=30, max_p=200
    )
    if price_e:
        result["eggs_10"] = price_e
        logger.info(f"✅ Яйця 10 шт (АТБ): {price_e} грн")
    else:
        logger.warning("⚠️ Яйця 10 шт (АТБ): не знайдено")

    # ── Fallback: Minfin якщо АТБ не дав результатів ───────────────
    if not result:
        logger.info("🔄 АТБ не відповів — пробуємо Minfin як fallback...")
        result = await _get_poultry_minfin_fallback(session)

    return result


async def _get_poultry_minfin_fallback(session: aiohttp.ClientSession) -> dict:
    """
    Резервний варіант — Minfin щоденний моніторинг по супермаркетах.
    Дані там оновлюються частіше ніж загальна статистика.
    """
    result = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # Куряче філе
    try:
        url = "https://index.minfin.com.ua/ua/markets/wares/prods/meat-food/meat/chicken/"
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                soup = BeautifulSoup(await resp.text(), 'html.parser')
                prices = []
                for row in soup.find_all('tr'):
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        name = cols[0].get_text(strip=True).lower()
                        if 'філе' in name and 'індич' not in name:
                            # Перебираємо всі колонки з ціною (можуть бути по магазинах)
                            for col in cols[1:]:
                                val = col.get_text(strip=True).replace(',', '.') \
                                         .replace('\xa0', '').replace(' ', '')
                                try:
                                    p = float(val)
                                    if 60 < p < 350:
                                        prices.append(p)
                                except:
                                    pass
                if prices:
                    result["chicken_fillet"] = round(sum(prices) / len(prices), 2)
                    logger.info(f"✅ Куряче філе (Minfin fallback): {result['chicken_fillet']} грн/кг")
    except Exception as e:
        logger.warning(f"Minfin куряче філе: {e}")

    # Яйця
    try:
        url = "https://index.minfin.com.ua/ua/markets/wares/prods/eggs/eggs/chicken/"
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                soup = BeautifulSoup(await resp.text(), 'html.parser')
                prices = []
                for row in soup.find_all('tr'):
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        name = cols[0].get_text(strip=True).lower()
                        if 'яйц' in name and '10' in name:
                            for col in cols[1:]:
                                val = col.get_text(strip=True).replace(',', '.') \
                                         .replace('\xa0', '').replace(' ', '')
                                try:
                                    p = float(val)
                                    if 25 < p < 200:
                                        prices.append(p)
                                except:
                                    pass
                if prices:
                    result["eggs_10"] = round(sum(prices) / len(prices), 2)
                    logger.info(f"✅ Яйця 10 шт (Minfin fallback): {result['eggs_10']} грн")
    except Exception as e:
        logger.warning(f"Minfin яйця: {e}")

    return result

# ─── Зміни ціни (emoji) ────────────────────────────────────────────────────

def rate_change_emoji(curr, prev):
    if prev is None:
        return ""
    diff = curr - prev
    pct = (diff / prev) * 100
    if diff > 0.01:
        return f" 📈 +{diff:.2f} грн (+{pct:.2f}%)"
    elif diff < -0.01:
        return f" 📉 {diff:.2f} грн ({pct:.2f}%)"
    else:
        return " ➡️"

def fuel_change_emoji(curr, prev):
    if prev is None:
        return ""
    diff = curr - prev
    if diff > 0.01:
        return f" 📈 +{diff:.2f} грн"
    elif diff < -0.01:
        return f" 📉 {diff:.2f} грн"
    else:
        return " ➡️"

def price_change_emoji(curr, prev, threshold=0.05):
    """Універсальна функція зміни ціни для м'яса та яєць."""
    if prev is None:
        return ""
    diff = curr - prev
    if diff > threshold:
        return f" 📈 +{diff:.2f} грн"
    elif diff < -threshold:
        return f" 📉 {diff:.2f} грн"
    else:
        return " ➡️"

# ─── Зерно (CME) ───────────────────────────────────────────────────────────

def get_grain_prices():
    results = []
    try:
        wheat = yf.Ticker("ZW=F")
        wh = wheat.history(period="5d")
        if len(wh) >= 2:
            price_now = wh["Close"].iloc[-1]
            price_prev = wh["Close"].iloc[-2]
            price_usd = (price_now / 100) * WHEAT_BUSHELS_PER_TON
            change = ((price_now - price_prev) / price_prev) * 100
            emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            results.append(("🌾 Пшениця", price_usd, change, emoji))
        elif len(wh) == 1:
            price_usd = (wh["Close"].iloc[-1] / 100) * WHEAT_BUSHELS_PER_TON
            results.append(("🌾 Пшениця", price_usd, None, ""))
    except Exception as e:
        logger.error(f"Помилка отримання пшениці: {e}")

    try:
        corn = yf.Ticker("ZC=F")
        co = corn.history(period="5d")
        if len(co) >= 2:
            price_now = co["Close"].iloc[-1]
            price_prev = co["Close"].iloc[-2]
            price_usd = (price_now / 100) * CORN_BUSHELS_PER_TON
            change = ((price_now - price_prev) / price_prev) * 100
            emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            results.append(("🌽 Кукурудза", price_usd, change, emoji))
        elif len(co) == 1:
            price_usd = (co["Close"].iloc[-1] / 100) * CORN_BUSHELS_PER_TON
            results.append(("🌽 Кукурудза", price_usd, None, ""))
    except Exception as e:
        logger.error(f"Помилка отримання кукурудзи: {e}")

    return results

# ─── Головна функція ───────────────────────────────────────────────────────

async def get_grain_context():
    async with aiohttp.ClientSession() as session:

        # --- Курси НБУ ---
        rates = await get_nbu_rates(session)
        prev_rates = load_prev_rates()

        if rates:
            usd_rate = rates.get("USD", 41.5)
            eur = rates.get("EUR")
            pln = rates.get("PLN")

            usd_change = rate_change_emoji(usd_rate, prev_rates.get("USD"))
            eur_change = rate_change_emoji(eur, prev_rates.get("EUR")) if eur else ""
            pln_change = rate_change_emoji(pln, prev_rates.get("PLN")) if pln else ""

            currency_lines = [f"🇺🇸 USD: {usd_rate:.2f} грн{usd_change}"]
            if eur:
                currency_lines.append(f"🇪🇺 EUR: {eur:.2f} грн{eur_change}")
            if pln:
                currency_lines.append(f"🇵🇱 PLN: {pln:.2f} грн{pln_change}")

            currency_block = "💰 <b>Курси НБУ:</b>\n" + "\n".join(currency_lines)
            save_rates({"USD": usd_rate, "EUR": eur, "PLN": pln})
        else:
            usd_rate = 41.5
            currency_block = f"💰 <b>Курс (орієнтовний):</b>\n🇺🇸 USD: {usd_rate:.2f} грн"

        # --- Паливо ---
        fuel = await get_fuel_prices(session)
        prev_fuel = load_prev_fuel()
        if fuel:
            fuel_lines = []
            icons = {"A95": "🔵", "A92": "🟢", "ДП": "🟡", "ГАЗ": "🟠"}
            names = {"A95": "А-95", "A92": "А-92", "ДП": "Дизель", "ГАЗ": "Автогаз"}
            for key in ["A95", "A92", "ДП", "ГАЗ"]:
                if key in fuel:
                    change = fuel_change_emoji(fuel[key], prev_fuel.get(key))
                    fuel_lines.append(f"{icons[key]} {names[key]}: {fuel[key]:.2f} грн{change}")
            fuel_block = "⛽ <b>Паливо (УкрНафта):</b>\n" + "\n".join(fuel_lines)
            save_fuel(fuel)
        else:
            fuel_block = "⛽ <b>Паливо:</b> дані недоступні"

        # --- Зерно ---
        grain_prices = get_grain_prices()
        if grain_prices:
            lines = []
            for name, price_usd, change, emoji in grain_prices:
                price_uah = price_usd * usd_rate
                if change is not None:
                    lines.append(
                        f"{name}: ~${price_usd:.0f}/т  "
                        f"<b>{price_uah:,.0f} грн/т</b> {emoji} {change:+.1f}%"
                    )
                else:
                    lines.append(f"{name}: ~${price_usd:.0f}/т  <b>{price_uah:,.0f} грн/т</b>")
            grain_block = "📊 <b>Зерно (CME, $/т):</b>\n" + "\n".join(lines)
        else:
            grain_block = (
                "<b>🌾 Зерновий ринок:</b>\n"
                "• <a href='https://www.cmegroup.com/markets/agriculture/grains/wheat.quotes.html'>Пшениця ZW=F</a>\n"
                "• <a href='https://www.cmegroup.com/markets/agriculture/grains/corn.quotes.html'>Кукурудза ZC=F</a>"
            )

        # --- Ціни на птицю і яйця (АТБ) ---
        poultry = await get_poultry_prices(session)
        prev_poultry = load_prev_poultry()
        poultry_lines = []

        cf = poultry.get("chicken_fillet")
        if cf:
            ch = price_change_emoji(cf, prev_poultry.get("chicken_fillet"))
            poultry_lines.append(f"🍗 Куряче філе: <b>{cf:.2f} грн/кг</b>{ch}")

        tf = poultry.get("turkey_fillet")
        if tf:
            ch = price_change_emoji(tf, prev_poultry.get("turkey_fillet"))
            poultry_lines.append(f"🦃 Філе індички: <b>{tf:.2f} грн/кг</b>{ch}")

        eg = poultry.get("eggs_10")
        if eg:
            ch = price_change_emoji(eg, prev_poultry.get("eggs_10"), threshold=0.10)
            poultry_lines.append(f"🥚 Яйця С1 (10 шт): <b>{eg:.2f} грн</b>{ch}")

        if poultry_lines:
            poultry_block = "🐔 <b>Ціни на птицю і яйця (АТБ):</b>\n" + "\n".join(poultry_lines)
            save_poultry(poultry)
        else:
            poultry_block = "🐔 <b>Ціни на птицю і яйця:</b> дані недоступні"
            logger.warning("⚠️ Не вдалось отримати ціни на птицю/яйця")

        return (
            currency_block + "\n\n" +
            fuel_block + "\n\n" +
            grain_block + "\n\n" +
            poultry_block
        )
