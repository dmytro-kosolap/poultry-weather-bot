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
                        if len(cols) >= 2:
                            name = cols[0].get_text(strip=True)
                            price_text = cols[1].get_text(strip=True).replace(',', '.')
                            try:
                                price = float(price_text)
                                if "А-95 преміум" in name:
                                    pass  # пропускаємо преміум
                                elif "А-95" in name:
                                    fuel["A95"] = price
                                elif "А-92" in name:
                                    fuel["A92"] = price
                                elif "Дизельне" in name:
                                    fuel["ДП"] = price
                            except:
                                pass
    except Exception as e:
        logger.warning(f"Помилка отримання цін палива: {e}")
    return fuel

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

async def get_grain_context():
    async with aiohttp.ClientSession() as session:
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

        # Паливо
        fuel = await get_fuel_prices(session)
        prev_fuel = load_prev_fuel()
        if fuel:
            fuel_lines = []
            icons = {"A95": "🔵", "A92": "🟢", "ДП": "🟡"}
            names = {"A95": "А-95", "A92": "А-92", "ДП": "Дизель"}
            for key in ["A95", "A92", "ДП"]:
                if key in fuel:
                    change = fuel_change_emoji(fuel[key], prev_fuel.get(key))
                    fuel_lines.append(f"{icons[key]} {names[key]}: {fuel[key]:.2f} грн{change}")
            fuel_block = "⛽ <b>Паливо (УкрНафта):</b>\n" + "\n".join(fuel_lines)
            save_fuel(fuel)
        else:
            fuel_block = "⛽ <b>Паливо:</b> дані недоступні"

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
            grain_block = "<b>🌾 Зерновий ринок:</b>\n• <a href='https://www.cmegroup.com/markets/agriculture/grains/wheat.quotes.html'>Пшениця ZW=F</a>\n• <a href='https://www.cmegroup.com/markets/agriculture/grains/corn.quotes.html'>Кукурудза ZC=F</a>"

        return currency_block + "\n\n" + fuel_block + "\n\n" + grain_block
