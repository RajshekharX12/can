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

load_dotenv()  # loads BOT_TOKEN, optional overrides

BOT_TOKEN         = os.getenv("BOT_TOKEN")
CHROME_BINARY     = os.getenv("CHROME_BINARY",     "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

def fetch_usd_price() -> str:
    """Scrape fragment.com and return the USD price string, e.g. '~ $2,643'."""
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
        # 1) Load floor list and click first +888 item
        driver.get("https://fragment.com/numbers?filter=sale")
        link = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        detail_url = link.get_attribute("href")

        # 2) Go to detail page
        driver.get(detail_url)
        wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"$")]')
        ))

        # 3) Scan for the element containing "~ $"
        for el in driver.find_elements(By.XPATH, '//*[contains(text(),"$")]'):
            txt = el.text.replace("\n", " ").strip()
            if "~" in txt:
                return txt
        return "N/A"
    finally:
        driver.quit()

def convert_currency(amount: float, to: str) -> float:
    """Try /latest first; if rate==0, fall back to /convert."""
    # 1) latest rates
    try:
        resp = requests.get(
            "https://api.exchangerate.host/latest",
            params={"base": "USD", "symbols": to},
            timeout=5
        )
        resp.raise_for_status()
        rate = resp.json().get("rates", {}).get(to, 0.0)
        if rate > 0:
            return amount * rate
    except Exception:
        pass

    # 2) fallback convert endpoint
    try:
        resp = requests.get(
            "https://api.exchangerate.host/convert",
            params={"from": "USD", "to": to, "amount": amount},
            timeout=5
        )
        resp.raise_for_status()
        return resp.json().get("result", 0.0)
    except Exception:
        return 0.0

async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching price…")
    try:
        usd_raw = fetch_usd_price()  # e.g. "~ $2,643"
        await msg.edit_text(f"price 💵 : {usd_raw}")
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`", parse_mode=ParseMode.MARKDOWN)

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        usd_raw = fetch_usd_price()
        match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", usd_raw)
        amt = float(match.group(1).replace(",", "")) if match else 0.0

        # real-time conversions
        cny = convert_currency(amt, "CNY")
        rub = convert_currency(amt, "RUB")

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
                description=f"价格：{cny:,.2f} 元",
                input_message_content=InputTextMessageContent(f"价格：{cny:,.2f} 元")
            ),
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title="Российские рубли",
                description=f"Цена в российских рублях: {rub:,.2f} ₽",
                input_message_content=InputTextMessageContent(f"Цена в российских рублях: {rub:,.2f} ₽")
            ),
        ]

        # cache_time=0 → always fetch fresh on each inline
        await update.inline_query.answer(results, cache_time=0)
    except Exception:
        await update.inline_query.answer([], cache_time=0)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("floor", floor_cmd))
    app.add_handler(InlineQueryHandler(inline_query))

    # ensure no webhook + flush pending updates
    asyncio.get_event_loop().run_until_complete(
        app.bot.delete_webhook(drop_pending_updates=True)
    )

    print("Bot started (polling)…")
    app.run_polling()
