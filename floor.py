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

# Load environment
load_dotenv()
BOT_TOKEN         = os.getenv("BOT_TOKEN")
CHROME_BINARY     = os.getenv("CHROME_BINARY",     "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

SALE_URL = "https://fragment.com/numbers?filter=sale"
SOLD_URL = "https://fragment.com/numbers?sort=ending&filter=sold"

def fetch_usd_prices():
    """
    Clicks into the first for-sale and first sold +888 detail pages,
    scrapes the USD price from each, and returns (current_usd, sold_usd).
    """
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.binary_location = CHROME_BINARY

    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)
    wait = WebDriverWait(driver, 15)
    try:
        # -- Current --
        driver.get(SALE_URL)
        sale_link = wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        driver.get(sale_link.get_attribute("href"))
        sale_price = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//*[contains(text(),'~') and contains(text(),'$')]")
        )).text
        m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", sale_price)
        current_usd = float(m.group(1).replace(",", "")) if m else 0.0

        # -- Last Sold --
        driver.get(SOLD_URL)
        sold_link = wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        driver.get(sold_link.get_attribute("href"))
        sold_price = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//*[contains(text(),'~') and contains(text(),'$')]")
        )).text
        m2 = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", sold_price)
        sold_usd = float(m2.group(1).replace(",", "")) if m2 else 0.0

        return current_usd, sold_usd

    finally:
        driver.quit()

async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching floor price…")
    try:
        current_usd, sold_usd = fetch_usd_prices()
        # compute difference
        diff = current_usd - sold_usd
        pct = (diff / sold_usd * 100) if sold_usd else 0.0
        action = "Fall by" if diff < 0 else "Rise by"

        # build output
        text = f"Current price of +888 number: ~ ${current_usd:,.0f}"
        if sold_usd:
            text += f"\n{action} {pct:+.2f}% ({diff:+.2f} $)"

        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        current_usd, sold_usd = fetch_usd_prices()
        diff = current_usd - sold_usd
        pct = (diff / sold_usd * 100) if sold_usd else 0.0

        action_en = "Fall by" if diff < 0 else "Rise by"
        action_cn = "跌幅"  if diff < 0 else "涨幅"
        action_ru = "Падение" if diff < 0 else "Рост"

        eng = f"Current price of +888 number: ~ ${current_usd:,.0f}"
        if sold_usd:
            eng += f"\n{action_en} {pct:+.2f}% ({diff:+.2f} $)"

        chi = f"+888号码的当前价格：~ ${current_usd:,.0f}"
        if sold_usd:
            chi += f"\n{action_cn}：{pct:+.2f}% ({diff:+.2f} $)"

        rus = f"Текущая цена номера +888: ~ ${current_usd:,.0f}"
        if sold_usd:
            rus += f"\n{action_ru}: {pct:+.2f}% ({diff:+.2f} $)"

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

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("floor", floor_cmd))
    app.add_handler(InlineQueryHandler(inline_query))

    # clean start
    asyncio.get_event_loop().run_until_complete(
        app.bot.delete_webhook(drop_pending_updates=True)
    )
    app.run_polling()
