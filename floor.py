import os
import re
import requests
import asyncio
import uuid
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    InlineQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN         = os.getenv("BOT_TOKEN")
CHROME_BINARY     = os.getenv("CHROME_BINARY",     "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

def fetch_usd_price() -> str:
    """Scrape fragment.com for the USD price string (e.g. '~ $2,643')."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = CHROME_BINARY

    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 15)
    try:
        driver.get("https://fragment.com/numbers?filter=sale")
        link = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        detail_url = link.get_attribute("href")

        driver.get(detail_url)
        wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"$")]')
        ))

        for el in driver.find_elements(By.XPATH, '//*[contains(text(),"$")]'):
            text = el.text.replace("\n", " ").strip()
            if "~" in text:
                return text
        return "N/A"
    finally:
        driver.quit()

def convert_currency(amount: float, to: str) -> float:
    """Attempt /latest first (with debug), then fall back to /convert, else return 0.0."""
    # 1) Try /latest
    try:
        url = "https://api.exchangerate.host/latest"
        params = {"base": "USD", "symbols": to}
        print(f"[DEBUG] Fetching latest rate USD→{to} from {url} with {params}")
        r = requests.get(url, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        rate = data.get("rates", {}).get(to, 0.0)
        print(f"[DEBUG] /latest response: {data}")
        if rate and rate > 0:
            return amount * rate
        print(f"[DEBUG] /latest rate was zero or missing, falling back.")
    except Exception as e:
        print(f"[ERROR] /latest failed: {e}")

    # 2) Fallback to /convert
    try:
        url2 = "https://api.exchangerate.host/convert"
        params2 = {"from": "USD", "to": to, "amount": amount}
        print(f"[DEBUG] Fetching converted amount via {url2} with {params2}")
        r2 = requests.get(url2, params=params2, timeout=5)
        r2.raise_for_status()
        data2 = r2.json()
        print(f"[DEBUG] /convert response: {data2}")
        return data2.get("result", 0.0)
    except Exception as e2:
        print(f"[ERROR] /convert failed: {e2}")

    return 0.0

async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching price…")
    try:
        usd_raw = fetch_usd_price()
        await msg.edit_text(f"price 💵 : {usd_raw}")
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`", parse_mode=ParseMode.MARKDOWN)

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        usd_raw = fetch_usd_price()
        m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", usd_raw)
        amt = float(m.group(1).replace(",", "")) if m else 0.0

        # Real-time conversions
        cny_val = convert_currency(amt, "CNY")
        rub_val = convert_currency(amt, "RUB")

        # Format or show N/A
        cny_text = f"价格：{cny_val:,.2f} 元" if cny_val else "价格：N/A"
        rub_text = f"Цена в российских рублях: {rub_val:,.2f} ₽" if rub_val else "Цена в российских рублях: N/A"

        results = [
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title="USD Price",
                description=usd_raw,
                input_message_content=InputTextMessageContent(f"price 💵 : {usd_raw}")
            ),
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title="人民币价格",
                description=cny_text,
                input_message_content=InputTextMessageContent(cny_text)
            ),
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title="Российские рубли",
                description=rub_text,
                input_message_content=InputTextMessageContent(rub_text)
            ),
        ]

        await update.inline_query.answer(results, cache_time=0)
    except Exception as e:
        print(f"[ERROR] inline_query failed: {e}")
        await update.inline_query.answer([], cache_time=0)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("floor", floor_cmd))
    app.add_handler(InlineQueryHandler(inline_query))

    # clean start
    asyncio.get_event_loop().run_until_complete(
        app.bot.delete_webhook(drop_pending_updates=True)
    )
    print("Bot started (polling)…")
    app.run_polling()
