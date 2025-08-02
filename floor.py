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
SALE_LIST_URL     = "https://fragment.com/numbers?filter=sale"
SOLD_LIST_URL     = "https://fragment.com/numbers?sort=ending&filter=sold"

def scrape_detail(url: str):
    """
    Open the detail page at `url` and return (ton_raw, usd_raw, usd_val).
    """
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = CHROME_BINARY

    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=opts)
    wait = WebDriverWait(driver, 15)
    try:
        driver.get(url)

        # 1) TON: first element containing "TON" (case-insensitive)
        ton_elem = wait.until(EC.presence_of_element_located((
            By.XPATH, '//*[contains(translate(text(),"TON","ton"),"ton")]'
        )))
        ton_raw = ton_elem.text.strip()  # e.g. "740 TON"

        # 2) USD: scan all "$" elements and pick the one with "~"
        usd_raw = "N/A"
        for el in driver.find_elements(By.XPATH, '//*[contains(text(),"$")]'):
            txt = el.text.replace("\n"," ").strip()
            if "~" in txt:
                usd_raw = txt
                break

        # extract numeric USD value
        m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", usd_raw)
        usd_val = float(m.group(1).replace(",","")) if m else 0.0

        return ton_raw, usd_raw, usd_val

    finally:
        driver.quit()

def fetch_prices():
    """
    Click into the first +888 on sale & sold listings, scrape detail pages.
    Returns:
      sale_ton_raw, sale_usd_raw, sale_usd_val,
      sold_usd_val
    """
    # 1) Get first sale detail URL
    opts = Options()
    opts.add_argument("--headless"); opts.add_argument("--no-sandbox"); opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = CHROME_BINARY
    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)
    wait = WebDriverWait(driver, 15)
    try:
        driver.get(SALE_LIST_URL)
        sale_link = wait.until(EC.presence_of_element_located((
            By.XPATH, '//a[contains(@href,"/number/888")]'
        )))
        sale_url = sale_link.get_attribute("href")
    finally:
        driver.quit()

    # 2) Scrape sale detail
    sale_ton_raw, sale_usd_raw, sale_usd_val = scrape_detail(sale_url)

    # 3) Get first sold detail URL
    driver2 = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)
    wait2 = WebDriverWait(driver2, 15)
    try:
        driver2.get(SOLD_LIST_URL)
        sold_link = wait2.until(EC.presence_of_element_located((
            By.XPATH, '//a[contains(@href,"/number/888")]'
        )))
        sold_url = sold_link.get_attribute("href")
    finally:
        driver2.quit()

    # 4) Scrape sold detail (we only need USD for diff)
    _, _, sold_usd_val = scrape_detail(sold_url)

    return sale_ton_raw, sale_usd_raw, sale_usd_val, sold_usd_val

async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching price…")
    try:
        sale_ton_raw, sale_usd_raw, sale_usd, sold_usd = fetch_prices()

        diff = sale_usd - sold_usd
        pct = (diff / sold_usd * 100) if sold_usd else 0.0
        action = "Fall by" if diff < 0 else "Rise by"

        text = (
            f"Current price of +888 number: {sale_ton_raw} ({sale_usd_raw})\n"
            f"{action} {pct:+.2f}% ({diff:+.2f} $)"
        )
        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sale_ton_raw, sale_usd_raw, sale_usd, sold_usd = fetch_prices()

        diff = sale_usd - sold_usd
        pct = (diff / sold_usd * 100) if sold_usd else 0.0
        action_en = "Fall by" if diff < 0 else "Rise by"
        action_cn = "跌幅"  if diff < 0 else "涨幅"
        action_ru = "Падение" if diff < 0 else "Рост"

        eng = (
            f"Current price of +888 number: {sale_ton_raw} ({sale_usd_raw})\n"
            f"{action_en} {pct:+.2f}% ({diff:+.2f} $)"
        )
        chi = (
            f"+888号码的当前价格：{sale_ton_raw} ({sale_usd_raw})\n"
            f"{action_cn}：{pct:+.2f}% ({diff:+.2f} $)"
        )
        rus = (
            f"Текущая цена номера +888: {sale_ton_raw} ({sale_usd_raw})\n"
            f"{action_ru}: {pct:+.2f}% ({diff:+.2f} $)"
        )

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
