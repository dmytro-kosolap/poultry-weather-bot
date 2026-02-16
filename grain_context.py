import os
import aiohttp
import asyncio
import logging
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)

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

async def get_grain_context():
    api_key = os.getenv("ALPHA_VANTAGE_KEY")
    async with aiohttp.ClientSession() as session:
        rates = await get_nbu_rates(session)
        if rates:
            usd_rate = rates.get("USD", 41.5)
            eur = rates.get("EUR")
            pln = rates.get("PLN")
            currency_lines = [f"🇺🇸 USD: {usd_rate:.2f} грн"]
            if eur:
                currency_lines.append(f"🇪🇺 EUR: {eur:.2f} грн")
            if pln:
                currency_lines.append(f"🇵🇱 PLN: {pln:.2f} грн")
            currency_block = "💰 <b>Курси НБУ:</b>\n" + "\n".join(currency_lines)
        else:
            usd_rate = 41.5
            currency_block = f"💰 <b>Курс (орієнтовний):</b>\n🇺🇸 USD: {usd_rate:.2f} грн"
        if not api_key:
            return currency_block + "\n\n<b>🌾 Зерновий ринок:</b>\n• <a href='https://www.cmegroup.com/markets/agriculture/grains/wheat.quotes.html'>Пшениця ZW=F</a>\n• <a href='https://www.cmegroup.com/markets/agriculture/grains/corn.quotes.html'>Кукурудза ZC=F</a>"
        commodities = [
            {"name": "🌾 Пшениця", "function": "CORN"},
            {"name": "🌽 Кукурудза", "function": "WHEAT"},
        ]
        results = []
        for item in commodities:
            try:
                await asyncio.sleep(1.2)
                params = {"function": item["function"], "interval": "daily", "apikey": api_key}
                async with session.get("https://www.alphavantage.co/query", params=params, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "data" in data and data["data"]:
                            price_usd = float(data["data"][0]["value"])
                            price_uah = price_usd * usd_rate
                            change_text = ""
                            if len(data["data"]) > 1:
                                try:
                                    prev = float(data["data"][1]["value"])
                                    change = ((price_usd - prev) / prev) * 100
                                    emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                                    change_text = f" {emoji} {change:+.1f}%"
                                except Exception:
                                    pass
                            results.append(f"{item['name']}: ~${price_usd:.0f}/т  <b>{price_uah:,.0f} грн/т</b>{change_text}")
                        else:
                            results.append(f"{item['name']}: недоступно")
                    else:
                        results.append(f"{item['name']}: помилка")
            except Exception as e:
                logger.error(f"Помилка отримання {item['name']}: {e}")
                results.append(f"{item['name']}: сервіс недоступний")
        if results and not all(any(k in r for k in ("недоступ", "помилка", "сервіс")) for r in results):
            grain_block = "📊 <b>Зерно (CME, $/т):</b>\n" + "\n".join(results)
        else:
            grain_block = "<b>🌾 Зерновий ринок:</b>\n• <a href='https://www.cmegroup.com/markets/agriculture/grains/wheat.quotes.html'>Пшениця ZW=F</a>\n• <a href='https://www.cmegroup.com/markets/agriculture/grains/corn.quotes.html'>Кукурудза ZC=F</a>"
        return currency_block + "\n\n" + grain_block
