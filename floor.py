import os
import re
import asyncio
import uuid
import logging

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    InlineQueryHandler,
    ContextTypes,
)
from dotenv import load_dotenv

# ─── Configuration & Logging ────────────────────────────────────────────────────

load_dotenv()
BOT_TOKEN         = os.getenv("BOT_TOKEN")
CHROME_BINARY     = os.getenv("CHROME_BINARY",     "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

# URLs for listings
SALE_LIST_URL = "https://fragment.com/numbers?filter=sale"
SOLD_LIST_URL = "https://fragment.com/numbers?sort=ending&filter=sold"

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Selenium Helper Functions ─────────────────────────────────────────────────

def create_driver() -> webdriver.Chrome:
    """Initialize and return a headless Chrome WebDriver."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.binary_location = CHROME_BINARY

    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def get_first_number_detail_url(listing_url: str) -> str:
    """
    Open the listing URL, find the first +888 number link, and return its href.
    Raises if not found.
    """
    driver = create_driver()
    wait = WebDriverWait(driver, 15)
    try:
        driver.get(listing_url)
        link = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//a[contains(@href,"/number/888")]'))
        )
        href = link.get_attribute("href")
        logger.info("Found detail URL: %s", href)
        return href
    finally:
        driver.quit()

def scrape_price_from_detail(detail_url: str) -> (str, float):
    """
    Visit the detail page URL, locate the USD price string (with '~'),
    extract both the raw text and numeric value.
    Returns (raw_text, numeric_value).
    """
    driver = create_driver()
    wait = WebDriverWait(driver, 15)
    try:
        driver.get(detail_url)
        # Locate the element containing both '~' and '$'
        price_elem = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, '//*[contains(text(),"~") and contains(text(),"$")]')
            )
        )
        raw_text = price_elem.text.replace("\n", " ").strip()
        logger.info("Scraped raw price text: %s", raw_text)

        # Extract numeric part
        match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", raw_text)
        if match:
            numeric = float(match.group(1).replace(",", ""))
        else:
            numeric = 0.0
        return raw_text, numeric
    finally:
        driver.quit()

def fetch_floor_and_sold_prices():
    """
    Orchestrates scraping:
      1. Get detail URL for the first sale listing
      2. Scrape its USD price
      3. Get detail URL for the first sold listing
      4. Scrape its USD price
    Returns:
      (sale_raw, sale_val, sold_raw, sold_val)
    """
    # Sale
    sale_detail_url = get_first_number_detail_url(SALE_LIST_URL)
    sale_raw, sale_val = scrape_price_from_detail(sale_detail_url)

    # Sold
    sold_detail_url = get_first_number_detail_url(SOLD_LIST_URL)
    sold_raw, sold_val = scrape_price_from_detail(sold_detail_url)

    return sale_raw, sale_val, sold_raw, sold_val

# ─── Bot Command Handlers ──────────────────────────────────────────────────────

async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /floor command: show current price and percent change vs last sold."""
    info_msg = await update.message.reply_text("🔍 Fetching floor and sold prices…")
    try:
        # Fetch prices
        sale_raw, sale_val, sold_raw, sold_val = fetch_floor_and_sold_prices()

        # Compute difference and percentage
        diff = sale_val - sold_val
        pct = (diff / sold_val * 100) if sold_val else 0.0
        action = "Fall by" if diff < 0 else "Rise by"

        # Build message
        text_lines = [
            f"Current price of +888 number: ({sale_raw})",
            f"{action} {pct:+.2f}% ({diff:+.2f} $)"
        ]
        message_text = "\n".join(text_lines)

        # Edit reply
        await info_msg.edit_text(message_text)
    except Exception as e:
        logger.error("Error in /floor: %s", e)
        await info_msg.edit_text(f"❌ Error: `{e}`")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline queries: offer English, Chinese, Russian versions."""
    try:
        sale_raw, sale_val, sold_raw, sold_val = fetch_floor_and_sold_prices()

        diff = sale_val - sold_val
        pct = (diff / sold_val * 100) if sold_val else 0.0

        action_en = "Fall by" if diff < 0 else "Rise by"
        action_cn = "跌幅"  if diff < 0 else "涨幅"
        action_ru = "Падение" if diff < 0 else "Рост"

        # English
        eng = f"Current price of +888 number: ({sale_raw})"
        eng += f"\n{action_en} {pct:+.2f}% ({diff:+.2f} $)"

        # Chinese
        chi = f"+888号码的当前价格：({sale_raw})"
        chi += f"\n{action_cn}：{pct:+.2f}% ({diff:+.2f} $)"

        # Russian
        rus = f"Текущая цена номера +888: ({sale_raw})"
        rus += f"\n{action_ru}: {pct:+.2f}% ({diff:+.2f} $)"

        # Build 3 inline results
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
    except Exception as e:
        logger.error("Error in inline_query: %s", e)
        await update.inline_query.answer([], cache_time=0)

# ─── Main Entrypoint ────────────────────────────────────────────────────────────

def main():
    """Start the Telegram bot."""
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("floor", floor_cmd))
    app.add_handler(InlineQueryHandler(inline_query))

    # Ensure clean polling
    asyncio.get_event_loop().run_until_complete(
        app.bot.delete_webhook(drop_pending_updates=True)
    )

    logger.info("Bot started in command & inline mode.")
    app.run_polling()

if __name__ == "__main__":
    main()
