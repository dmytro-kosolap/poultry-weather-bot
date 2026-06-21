import logging
import aiohttp
import yfinance as yf
import json
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

WHEAT_BUSHELS_PER_TON = 36.74
CORN_BUSHELS_PER_TON = 39.37
RATES_FILE = "rates_history.json"
FUEL_FILE = "fuel_history.json"
POULTRY_FILE = "poultry_prices_history.json"

# ── Автоматичний вибір ф'ючерсного контракту ──────────────────────────
# CME торгує зерном по контрактах з місяцями постачання, позначеними літерами:
#   H=березень  K=травень  N=липень  U=вересень  Z=грудень
# Цей набір однаковий для пшениці (ZW) і кукурудзи (ZC) на CBOT.
# Щоб уникнути "мертвих" контрактів з низькою ліквідністю, переходимо
# на наступний контракт за ~25 днів до початку його місяця постачання.

CONTRACT_MONTHS = [
    (3, "H"), (5, "K"), (7, "N"), (9, "U"), (12, "Z")
]
ROLLOVER_DAYS_BEFORE = 25  # за скільки днів до 1-го числа місяця контракту переходимо на нього


def get_active_contract_code(today=None):
    """
    Повертає код контракту (наприклад 'N26') для поточної дати —
    найближчий контракт, до початку місяця якого лишається
    більше ROLLOVER_DAYS_BEFORE днів.
    """
    if today is None:
        today = datetime.now()

    candidates = []
    # Будуємо список контрактів на 2 роки вперед щоб точно перекрити поточну дату
    for year_offset in (0, 1):
        year = today.year + year_offset
        for month, letter in CONTRACT_MONTHS:
            delivery_start = datetime(year, month, 1)
            rollover_date = delivery_start - timedelta(days=ROLLOVER_DAYS_BEFORE)
            candidates.append((rollover_date, delivery_start, letter, year))

    candidates.sort(key=lambda x: x[1])  # сортуємо за датою постачання

    # Шукаємо перший контракт, чия дата роловеру ще не настала
    for rollover_date, delivery_start, letter, year in candidates:
        if today < rollover_date:
            yy = str(year)[-2:]
            return f"{letter}{yy}"

    # fallback — якщо щось пішло не так, беремо останній у списку
    rollover_date, delivery_start, letter, year = candidates[-1]
    yy = str(year)[-2:]
    return f"{letter}{yy}"


def get_grain_tickers():
    """Формує тикери пшениці і кукурудзи на основі поточної дати"""
    code = get_active_contract_code()
    wheat_ticker = f"ZW{code}.CBT"
    corn_ticker = f"ZC{code}.CBT"
    return wheat_ticker, corn_ticker


# Конкретні сторінки товарів на Novus — щоденні ціни
NOVUS_PRODUCTS = {
    "chicken_fillet": {
        "url": "https://novus.zakaz.ua/uk/products/file-epikur--novus02879312000000/",
        "label": "🍗 Куряче філе (Novus/Епікур)",
        "unit": "грн/кг",
        "key": "chicken_fillet"
    },
    "turkey_fillet": {
        "url": "https://novus.zakaz.ua/uk/products/file-maistri-smaku--novus02856510000000/",
        "label": "🦃 Філе індички (Novus)",
        "unit": "грн/кг",
        "key": "turkey_fillet"
    },
    "eggs_10": {
        "url": "https://novus.zakaz.ua/uk/products/iaitse-novus--04820147580694/",
        "label": "🥚 Яйця курячі С0 10шт (Novus)",
        "unit": "грн/10шт",
        "key": "eggs_10"
    },
}


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
        logger.warning(f"Не вдалось зберегти ціни продуктів: {e}")


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


async def get_novus_price(session, product_key):
    """Парсить ціну конкретного товару зі сторінки Novus"""
    product = NOVUS_PRODUCTS[product_key]
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        async with session.get(product["url"], headers=headers, timeout=15) as resp:
            if resp.status == 200:
                text = await resp.text()
                soup = BeautifulSoup(text, 'html.parser')

                price = None

                for tag in soup.find_all(['h6', 'h5', 'h4']):
                    text_val = tag.get_text(strip=True)
                    match = re.search(r'(\d+[\.,]\d+)\s*[₴грн]', text_val)
                    if match:
                        price = float(match.group(1).replace(',', '.'))
                        if 10 < price < 5000:
                            logger.info(f"✅ {product['label']}: {price} {product['unit']} (h-tag)")
                            return price

                matches = re.findall(r'(\d{2,4}[\.,]\d{2})\s*₴', text)
                prices = []
                for m in matches:
                    val = float(m.replace(',', '.'))
                    if 10 < val < 5000:
                        prices.append(val)

                if prices:
                    price = prices[0]
                    logger.info(f"✅ {product['label']}: {price} {product['unit']} (regex)")
                    return price

    except Exception as e:
        logger.warning(f"❌ Помилка парсингу {product['label']}: {e}")
    return None


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

def price_change_emoji(curr, prev):
    if prev is None:
        return ""
    diff = curr - prev
    if diff > 0.05:
        return f" 📈 +{diff:.2f} грн"
    elif diff < -0.05:
        return f" 📉 {diff:.2f} грн"
    else:
        return " ➡️"


def get_grain_prices():
    """
    Отримує ціни на пшеницю і кукурудзу з АВТОМАТИЧНО вибраного
    активного ф'ючерсного контракту (не continuous ZC=F/ZW=F),
    щоб уникнути фантомних стрибків при роловері.
    Контракт оновлюється сам — нічого вручну міняти не треба.
    """
    results = []
    MAX_REASONABLE_CHANGE = 8.0  # % — захист від аномальних стрибків

    wheat_ticker, corn_ticker = get_grain_tickers()
    logger.info(f"📋 Активні контракти: пшениця={wheat_ticker}, кукурудза={corn_ticker}")

    try:
        wheat = yf.Ticker(wheat_ticker)
        wh = wheat.history(period="5d")
        if len(wh) >= 2:
            price_now = wh["Close"].iloc[-1]
            price_prev = wh["Close"].iloc[-2]
            price_usd = (price_now / 100) * WHEAT_BUSHELS_PER_TON
            change = ((price_now - price_prev) / price_prev) * 100

            if abs(change) > MAX_REASONABLE_CHANGE:
                logger.warning(f"⚠️ Пшениця: аномальна зміна {change:.1f}% — можливо проблема з контрактом {wheat_ticker}")
                results.append(("🌾 Пшениця", price_usd, None, ""))
            else:
                emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                results.append(("🌾 Пшениця", price_usd, change, emoji))
        elif len(wh) == 1:
            price_usd = (wh["Close"].iloc[-1] / 100) * WHEAT_BUSHELS_PER_TON
            results.append(("🌾 Пшениця", price_usd, None, ""))
        else:
            logger.warning(f"⚠️ Пшениця: контракт {wheat_ticker} не повернув даних")
    except Exception as e:
        logger.error(f"Помилка отримання пшениці ({wheat_ticker}): {e}")

    try:
        corn = yf.Ticker(corn_ticker)
        co = corn.history(period="5d")
        if len(co) >= 2:
            price_now = co["Close"].iloc[-1]
            price_prev = co["Close"].iloc[-2]
            price_usd = (price_now / 100) * CORN_BUSHELS_PER_TON
            change = ((price_now - price_prev) / price_prev) * 100

            if abs(change) > MAX_REASONABLE_CHANGE:
                logger.warning(f"⚠️ Кукурудза: аномальна зміна {change:.1f}% — можливо проблема з контрактом {corn_ticker}")
                results.append(("🌽 Кукурудза", price_usd, None, ""))
            else:
                emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                results.append(("🌽 Кукурудза", price_usd, change, emoji))
        elif len(co) == 1:
            price_usd = (co["Close"].iloc[-1] / 100) * CORN_BUSHELS_PER_TON
            results.append(("🌽 Кукурудза", price_usd, None, ""))
        else:
            logger.warning(f"⚠️ Кукурудза: контракт {corn_ticker} не повернув даних")
    except Exception as e:
        logger.error(f"Помилка отримання кукурудзи ({corn_ticker}): {e}")

    return results


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
                    lines.append(f"{name}: ~${price_usd:.0f}/т  <b>{price_uah:,.0f} грн/т</b> {emoji} {change:+.1f}%")
                else:
                    lines.append(f"{name}: ~${price_usd:.0f}/т  <b>{price_uah:,.0f} грн/т</b>")
            grain_block = "📊 <b>Зерно (CME, $/т):</b>\n" + "\n".join(lines)
        else:
            grain_block = "<b>🌾 Зерновий ринок:</b>\n• <a href='https://www.cmegroup.com/markets/agriculture/grains/wheat.quotes.html'>Пшениця</a>\n• <a href='https://www.cmegroup.com/markets/agriculture/grains/corn.quotes.html'>Кукурудза</a>"

        # --- Ціни на продукцію птахівництва (Novus) ---
        prev_poultry = load_prev_poultry()
        new_poultry = {}
        poultry_lines = []

        for key in ["chicken_fillet", "turkey_fillet", "eggs_10"]:
            product = NOVUS_PRODUCTS[key]
            price = await get_novus_price(session, key)
            if price:
                new_poultry[key] = price
                change = price_change_emoji(price, prev_poultry.get(key))
                poultry_lines.append(f"{product['label']}: <b>{price:.2f} {product['unit']}</b>{change}")
            else:
                poultry_lines.append(f"{product['label']}: дані недоступні")

        if new_poultry:
            save_poultry(new_poultry)

        poultry_block = "🐔 <b>Ціни (Novus):</b>\n" + "\n".join(poultry_lines)

        return (
            currency_block + "\n\n" +
            fuel_block + "\n\n" +
            grain_block + "\n\n" +
            poultry_block
        )
