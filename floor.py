import os
import re
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
import uuid

load_dotenv()
BOT_TOKEN         = os.getenv("BOT_TOKEN")
CHROME_BINARY     = os.getenv("CHROME_BINARY",     "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

async def fetch_usd_price() -> str:
    """Launch headless Chromium, click first /number/888… link,
       scrape USD price (~ $X,XXX) and return it."""
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = CHROME_BINARY

    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=opts)
    wait = WebDriverWait(driver, 15)

    try:
        driver.get("https://fragment.com/numbers?filter=sale")
        a = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        detail_url = a.get_attribute("href")

        driver.get(detail_url)
        wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"$")]')
        ))

        # scan all $-elements, pick the one with "~"
        usd = "N/A"
        for el in driver.find_elements(By.XPATH, '//*[contains(text(),"$")]'):
            t = el.text.replace("\n"," ").strip()
            if "~" in t:
                usd = t
                break

        return usd
    finally:
        driver.quit()

async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching price…")
    try:
        usd = await fetch_usd_price()
        await msg.edit_text(f"price 💵 : {usd}")
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`", parse_mode=ParseMode.MARKDOWN)

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_id = update.inline_query.id
    try:
        usd = await fetch_usd_price()
        content = InputTextMessageContent(f"price 💵 : {usd}")
        result = InlineQueryResultArticle(
            id=uuid.uuid4().hex,
            title="Floor Price",
            description=usd,
            input_message_content=content
        )
        await update.inline_query.answer([result], cache_time=10)
    except Exception:
        # on error, return no results
        await update.inline_query.answer([], cache_time=10)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("floor", floor_cmd))
    app.add_handler(InlineQueryHandler(inline_query))
    print("Bot started in both command & inline mode…")
    app.run_polling()
