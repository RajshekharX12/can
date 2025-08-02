import os
import re
import asyncio
import uuid
import requests

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ApplicationBuilder, CommandHandler, InlineQueryHandler, ContextTypes
from dotenv import load_dotenv

# ─── Configuration ────────────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN         = os.getenv("BOT_TOKEN")
CHROME_BINARY     = os.getenv("CHROME_BINARY",     "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
SALE_LIST_URL     = "https://fragment.com/numbers?filter=sale"

# ─── Fetch Functions ───────────────────────────────────────────────────────────
def create_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = CHROME_BINARY
    return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)

def fetch_current_price():
    """
    Scrape the first +888 sale detail page for the USD floor price.
    Returns (raw_text, numeric_usd).
    """
    driver = create_driver()
    wait = WebDriverWait(driver, 10)
    try:
        driver.get(SALE_LIST_URL)
        link = wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        driver.get(link.get_attribute("href"))

        elem = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"~") and contains(text(),"$")]')
        ))
        raw = elem.text.replace("\n"," ").strip()           # e.g. "~ $2,589"
        m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", raw)
        val = float(m.group(1).replace(",","")) if m else 0.0
        return raw, val
    finally:
        driver.quit()

def fetch_fx_rates():
    """
    Use exchangerate.host /convert to get USD→CNY and USD→RUB rates.
    Returns (rate_cny, rate_rub).
    """
    try:
        r1 = requests.get(
            "https://api.exchangerate.host/convert",
            params={"from":"USD","to":"CNY","amount":1},
            timeout=5
        )
        r1.raise_for_status()
        rate_cny = r1.json().get("result", 0.0)

        r2 = requests.get(
            "https://api.exchangerate.host/convert",
            params={"from":"USD","to":"RUB","amount":1},
            timeout=5
        )
        r2.raise_for_status()
        rate_rub = r2.json().get("result", 0.0)

        return rate_cny, rate_rub
    except:
        return 0.0, 0.0

# ─── Bot Handlers ──────────────────────────────────────────────────────────────
async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching price…")
    raw, usd = fetch_current_price()
    rate_cny, rate_rub = fetch_fx_rates()

    cny = usd * rate_cny
    rub = usd * rate_rub

    # guard zero-rate
    cny_text = f"≈ {cny:,.2f} 元" if rate_cny else "≈ N/A"
    rub_text = f"≈ {rub:,.2f} ₽" if rate_rub else "≈ N/A"

    text = (
        f"Current price of +888 number: ({raw})\n"
        f"{cny_text}\n"
        f"{rub_text}"
    )
    await msg.edit_text(text)

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw, usd = fetch_current_price()
    rate_cny, rate_rub = fetch_fx_rates()

    cny = usd * rate_cny
    rub = usd * rate_rub

    cny_text = f"≈ {cny:,.2f} 元" if rate_cny else "≈ N/A"
    rub_text = f"≈ {rub:,.2f} ₽" if rate_rub else "≈ N/A"

    eng = f"Current price of +888 number: ({raw})\n{cny_text}  {rub_text}"
    chi = f"+888号码的当前价格：({raw})\n{cny_text}  {rub_text}"
    rus = f"Текущая цена номера +888: ({raw})\n{rub_text}  {cny_text}"

    results = [
        InlineQueryResultArticle(
            id=uuid.uuid4().hex,
            title="🇺🇸 English",
            description=eng,
            input_message_content=InputTextMessageContent(eng),
        ),
        InlineQueryResultArticle(
            id=uuid.uuid4().hex,
            title="🇨🇳 中文",
            description=chi,
            input_message_content=InputTextMessageContent(chi),
        ),
        InlineQueryResultArticle(
            id=uuid.uuid4().hex,
            title="🇷🇺 Русский",
            description=rus,
            input_message_content=InputTextMessageContent(rus),
        ),
    ]
    await update.inline_query.answer(results, cache_time=0)

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("floor", floor_cmd))
    app.add_handler(InlineQueryHandler(inline_query))
    asyncio.get_event_loop().run_until_complete(
        app.bot.delete_webhook(drop_pending_updates=True)
    )
    app.run_polling()
