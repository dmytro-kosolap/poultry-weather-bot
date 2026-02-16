import os
import aiohttp
import asyncio
import logging
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)

async def get_usd_uah_rate(session, api_key):
    try:
        url = "https://www.alphavantage.co/query"
        params = {"function": "CURRENCY_EXCHANGE_RATE", "from_currency": "USD", "to_currency": "UAH", "apikey": api_key}
        async with session.get(url, params=params, timeout=15) as response:
            if response.status == 200:
                data = await response.json()
                rate_str = data.get("Realtime Currency Exchange Rate", {}).get("5. Exchange Rate")
                if rate_str:
                    return float(rate_str)
    except Exception as e:
        logger.warning(f"Не вдалося отримати курс USD/UAH: {e}")
    return None

async def get_usd_uah_rate_fallback(session):
    try:
        async with session.get("https://open.er-api.com/v6/latest/USD", timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                return float(data["rates"]["UAH"])
    except Exception as e:
        logger.warning(f"Резервний курс недоступний: {e}")
    return None

async def get_grain_context():
    api_key = os.getenv("ALPHA_VANTAGE_KEY")
    if not api_key:
        return "<b>🌾 Зерновий ринок:</b>"
    commodities = [
        {"name": "🌾 Пшениця", "function": "CORN"},
        {"name": "🌽 Кукурудза", "function": "WHEAT"},
    ]
    results = []
    async with aiohttp.ClientSession() as session:
        uah_rate = await get_usd_uah_rate(session, api_key)
        if uah_rate is None:
            await asyncio.sleep(1.2)
            uah_rate = await get_usd_uah_rate_fallback(session)
        if uah_rate:
            rate_note = f"💱 Курс: 1 USD = {uah_rate:.1f} грн\n\n"
        else:
            uah_rate = 41.5
            rate_note = f"💱 Курс (орієнтовний): 1 USD = {uah_rate:.1f} грн\n\n"
        for item in commodities:
            try:
                await asyncio.sleep(1.2)
                params = {"function": item["function"], "interval": "daily", "apikey": api_key}
                async with session.get("https://www.alphavantage.co/query", params=params, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "data" in data and data["data"]:
                            price_usd = float(data["data"][0]["value"])
                            price_uah = price_usd * uah_rate
                            change_text = ""
                            if len(data["data"]) > 1:
                                try:
                                    prev = float(data["data"][1]["value"])
                                    change = ((price_usd - prev) / prev) * 100
                                    emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                                    change_text = f"{emoji} {change:+.1f}%"
                                except Exception:
                                    pass
                            results.append(f"{item['name']}: ~${price_usd:.0f}/т  <b>{price_uah:,.0f} грн/т</b>  {change_text}")
                        else:
                            results.append(f"{item['name']}: недоступно")
                    else:
                        results.append(f"{item['name']}: помилка")
            except Exception as e:
                results.append(f"{item['name']}: сервіс недоступний")
    if results and not all(any(k in r for k in ("недоступ", "помилка", "сервіс")) for r in results):
        return "📊 <b>Ціни на зерно (біржа CME):</b>\n\n" + rate_note + "\n".join(results)
    return "<b>🌾 Зерновий ринок:</b>\n• <a href='https://www.cmegroup.com/markets/agriculture/grains/wheat.quotes.html'>Пшениця ZW=F</a>\n• <a href='https://www.cmegroup.com/markets/agriculture/grains/corn.quotes.html'>Кукурудза ZC=F</a>"
