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

SALE_LIST_URL = "https://fragment.com/numbers?filter=sale"

# ─── Web Scraping ──────────────────────────────────────────────────────────────
def create_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = CHROME_BINARY
    return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)

def fetch_current_price():
    """
    Scrape the first +888 sale detail page and return:
      raw_text (e.g. "~ $2,589"), numeric USD value
    """
    driver = create_driver()
    wait = WebDriverWait(driver, 10)
    try:
        # load listing and click the first +888 link
        driver.get(SALE_LIST_URL)
        link = wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        driver.get(link.get_attribute("href"))

        # scrape the "~ $X,XXX" element
        elem = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"~") and contains(text(),"$")]')
        ))
        raw = elem.text.replace("\n"," ").strip()
        m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", raw)
        val = float(m.group(1).replace(",","")) if m else 0.0
        return raw, val
    finally:
        driver.quit()

# ─── FX Rates ─────────────────────────────────────────────────────────────────
def fetch_fx_rates():
    """
    Fetch USD→CNY and USD→RUB rates from exchangerate.host.
    Returns (rate_cny, rate_rub).
    """
    try:
        r = requests.get("https://api.exchangerate.host/latest",
                         params={"base":"USD","symbols":"CNY,RUB"}, timeout=5)
        r.raise_for_status()
        rates = r.json().get("rates", {})
        return rates.get("CNY", 0.0), rates.get("RUB", 0.0)
    except:
        return 0.0, 0.0

# ─── Bot Handlers ──────────────────────────────────────────────────────────────
async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching current price…")
    raw, usd = fetch_current_price()
    rate_cny, rate_rub = fetch_fx_rates()
    cny = usd * rate_cny
    rub = usd * rate_rub

    text = (
        f"Current price of +888 number: ({raw})\n"
        f"≈ {cny:,.2f} CNY\n"
        f"≈ {rub:,.2f} RUB"
    )
    await msg.edit_text(text)

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw, usd = fetch_current_price()
    rate_cny, rate_rub = fetch_fx_rates()
    cny = usd * rate_cny
    rub = usd * rate_rub

    eng = f"Current price of +888 number: ({raw})\n≈ {cny:,.2f} CNY ≈ {rub:,.2f} RUB"
    chi = f"+888号码的当前价格：({raw})\n≈ {cny:,.2f} 元 ≈ {rub:,.2f} ₽"
    rus = f"Текущая цена номера +888: ({raw})\n≈ {rub:,.2f} ₽ ≈ {cny:,.2f} 元"

    results = [
        InlineQueryResultArticle(
            id=uuid.uuid4().hex, title="🇺🇸 English",
            description=eng, input_message_content=InputTextMessageContent(eng)
        ),
        InlineQueryResultArticle(
            id=uuid.uuid4().hex, title="🇨🇳 中文",
            description=chi, input_message_content=InputTextMessageContent(chi)
        ),
        InlineQueryResultArticle(
            id=uuid.uuid4().hex, title="🇷🇺 Русский",
            description=rus, input_message_content=InputTextMessageContent(rus)
        ),
    ]
    await update.inline_query.answer(results, cache_time=0)

# ─── Main Entrypoint ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("floor", floor_cmd))
    app.add_handler(InlineQueryHandler(inline_query))
    asyncio.get_event_loop().run_until_complete(
        app.bot.delete_webhook(drop_pending_updates=True)
    )
    app.run_polling()
