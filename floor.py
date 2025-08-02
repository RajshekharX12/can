import warnings
from requests.exceptions import RequestsDependencyWarning
warnings.filterwarnings("ignore", category=RequestsDependencyWarning)

import os
import requests
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

load_dotenv()

BOT_TOKEN         = os.getenv("BOT_TOKEN")
CHROME_BINARY     = os.getenv("CHROME_BINARY",     "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

SALE_URL  = "https://fragment.com/numbers?filter=sale"
SOLD_URL  = "https://fragment.com/numbers?sort=ending&filter=sold"
COINGECKO = "https://api.coingecko.com/api/v3/simple/price"

def fetch_prices():
    """
    Returns:
      sale_ton_val (float), sold_ton_val (float)
    by clicking into the first +888 entry on sale and sold pages.
    """
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = CHROME_BINARY

    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)
    wait = WebDriverWait(driver, 15)
    try:
        # 1) Sale page → click first listed number → scrape TON
        driver.get(SALE_URL)
        sale_link = wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        driver.get(sale_link.get_attribute("href"))
        ton_elem = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//div[contains(text(),"TON")]')
        ))
        sale_ton_val = float(ton_elem.text.split()[0].replace(",", ""))

        # 2) Sold page → click first sold number → scrape TON
        driver.get(SOLD_URL)
        sold_link = wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        driver.get(sold_link.get_attribute("href"))
        ton_elem2 = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//div[contains(text(),"TON")]')
        ))
        sold_ton_val = float(ton_elem2.text.split()[0].replace(",", ""))

        return sale_ton_val, sold_ton_val
    finally:
        driver.quit()

def get_ton_usd_rate() -> float:
    """Fetch current TON→USDT rate from CoinGecko (USDT≈USD)."""
    try:
        r = requests.get(
            COINGECKO,
            params={"ids": "toncoin", "vs_currencies": "usdt"},
            timeout=5
        )
        r.raise_for_status()
        return float(r.json()["toncoin"]["usdt"])
    except:
        return 0.0

async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching floor price…")
    try:
        sale_ton, sold_ton = fetch_prices()
        rate = get_ton_usd_rate()

        sale_usd = sale_ton * rate
        sold_usd = sold_ton * rate

        diff_usd = sale_usd - sold_usd
        pct = (diff_usd / sold_usd * 100) if sold_usd else 0.0
        action = "Fall by" if diff_usd < 0 else "Rise by"

        text = f"Current price of +888 number: ~ ${sale_usd:,.0f}"
        if sold_usd:
            text += f"\n{action} {pct:+.2f}% ({diff_usd:+.2f} $)"
        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sale_ton, sold_ton = fetch_prices()
        rate = get_ton_usd_rate()

        sale_usd = sale_ton * rate
        sold_usd = sold_ton * rate
        diff_usd = sale_usd - sold_usd
        pct = (diff_usd / sold_usd * 100) if sold_usd else 0.0

        action_en = "Fall by" if diff_usd < 0 else "Rise by"
        action_cn = "跌幅"  if diff_usd < 0 else "涨幅"
        action_ru = "Падение" if diff_usd < 0 else "Рост"

        eng = f"Current price of +888 number: ~ ${sale_usd:,.0f}"
        if sold_usd:
            eng += f"\n{action_en} {pct:+.2f}% ({diff_usd:+.2f} $)"

        chi = f"+888号码的当前价格：~ ${sale_usd:,.0f}"
        if sold_usd:
            chi += f"\n{action_cn}：{pct:+.2f}% ({diff_usd:+.2f} $)"

        rus = f"Текущая цена номера +888: ~ ${sale_usd:,.0f}"
        if sold_usd:
            rus += f"\n{action_ru}: {pct:+.2f}% ({diff_usd:+.2f} $)"

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

    # ensure clean start
    asyncio.get_event_loop().run_until_complete(
        app.bot.delete_webhook(drop_pending_updates=True)
    )
    app.run_polling()

