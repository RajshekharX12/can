import warnings
from requests.exceptions import RequestsDependencyWarning
warnings.filterwarnings("ignore", category=RequestsDependencyWarning)

import os
import re
import asyncio
import uuid
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ApplicationBuilder, CommandHandler, InlineQueryHandler, ContextTypes
from dotenv import load_dotenv

# ─── Config ────────────────────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN         = os.getenv("BOT_TOKEN")
CHROME_BINARY     = os.getenv("CHROME_BINARY",     "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

SALE_URL = "https://fragment.com/numbers?filter=sale"
SOLD_URL = "https://fragment.com/numbers?sort=ending&filter=sold"

# ─── Scraping ──────────────────────────────────────────────────────────────────
def fetch_listing_prices():
    """
    Scrape the first row of the SALE and SOLD listings for both TON & USD.
    Returns:
        sale_ton: float
        sale_usd: float
        sold_ton: float
        sold_usd: float
    """
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = CHROME_BINARY

    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)
    wait = WebDriverWait(driver, 15)
    try:
        # --- SALE LISTING ---
        driver.get(SALE_URL)
        # TON cell (first)
        sale_ton_cell = wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR,
            "div.table-cell-value.tm-value.icon-before.icon-ton"
        )))
        sale_ton = float(sale_ton_cell.text.replace(",", "").split()[0])
        # USD cell (first) - uses icon-before icon-usd
        sale_usd_cell = driver.find_element(By.CSS_SELECTOR,
            "div.table-cell-value.tm-value.icon-before.icon-dollar"
        )
        # text like "$2,593"
        sale_usd = float(sale_usd_cell.text.replace("$","").replace(",",""))

        # --- SOLD LISTING ---
        driver.get(SOLD_URL)
        sold_ton_cell = wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR,
            "div.table-cell-value.tm-value.icon-before.icon-ton"
        )))
        sold_ton = float(sold_ton_cell.text.replace(",", "").split()[0])
        sold_usd_cell = driver.find_element(By.CSS_SELECTOR,
            "div.table-cell-value.tm-value.icon-before.icon-dollar"
        )
        sold_usd = float(sold_usd_cell.text.replace("$","").replace(",",""))

        return sale_ton, sale_usd, sold_ton, sold_usd

    finally:
        driver.quit()

# ─── Bot Handlers ─────────────────────────────────────────────────────────────
async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching floor price…")
    try:
        sale_ton, sale_usd, sold_ton, sold_usd = fetch_listing_prices()

        diff_usd = sale_usd - sold_usd
        pct = (diff_usd / sold_usd * 100) if sold_usd else 0.0
        action = "Fall by" if diff_usd < 0 else "Rise by"

        text = (
            f"Current price of +888 number: {sale_ton:.0f} TON (~ ${sale_usd:,.0f})\n"
            f"{action} {pct:+.2f}% ({diff_usd:+.2f} $)"
        )
        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sale_ton, sale_usd, sold_ton, sold_usd = fetch_listing_prices()

        diff_usd = sale_usd - sold_usd
        pct = (diff_usd / sold_usd * 100) if sold_usd else 0.0

        action_en = "Fall by" if diff_usd < 0 else "Rise by"
        action_cn = "跌幅"  if diff_usd < 0 else "涨幅"
        action_ru = "Падение" if diff_usd < 0 else "Рост"

        eng = (
            f"Current price of +888 number: {sale_ton:.0f} TON (~ ${sale_usd:,.0f})\n"
            f"{action_en} {pct:+.2f}% ({diff_usd:+.2f} $)"
        )
        chi = (
            f"+888号码的当前价格：{sale_ton:.0f} TON (~ ${sale_usd:,.0f})\n"
            f"{action_cn}：{pct:+.2f}% ({diff_usd:+.2f} $)"
        )
        rus = (
            f"Текущая цена номера +888: {sale_ton:.0f} TON (~ ${sale_usd:,.0f})\n"
            f"{action_ru}: {pct:+.2f}% ({diff_usd:+.2f} $)"
        )

        results = [
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title="🇺🇸 English",
                description=eng,
                input_message_content=InputTextMessageContent(eng)
            ),
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title="🇨🇳 中文",
                description=chi,
                input_message_content=InputTextMessageContent(chi)
            ),
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title="🇷🇺 Русский",
                description=rus,
                input_message_content=InputTextMessageContent(rus)
            ),
        ]
        await update.inline_query.answer(results, cache_time=0)
    except:
        await update.inline_query.answer([], cache_time=0)

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("floor", floor_cmd))
    app.add_handler(InlineQueryHandler(inline_query))

    # clean start
    asyncio.get_event_loop().run_until_complete(
        app.bot.delete_webhook(drop_pending_updates=True)
    )
    app.run_polling()
