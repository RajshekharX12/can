import os
import re
import requests
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

def fetch_usd_price() -> str:
    """Scrape fragment.com and return the USD price string, e.g. '~ $2,643'."""
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = CHROME_BINARY

    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=opts)
    wait = WebDriverWait(driver, 15)
    try:
        # Load floor list and click first +888 link
        driver.get("https://fragment.com/numbers?filter=sale")
        link = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        detail_url = link.get_attribute("href")

        # Go to detail page and wait for any $ text
        driver.get(detail_url)
        wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"$")]')
        ))

        # Find the one containing "~"
        for el in driver.find_elements(By.XPATH, '//*[contains(text(),"$")]'):
            txt = el.text.replace("\n", " ").strip()
            if "~" in txt:
                return txt
        return "N/A"
    finally:
        driver.quit()

def convert_currency(amount: float, to: str) -> float:
    """Fetch real-time USD→<to> rate from /latest and convert."""
    r = requests.get(
        "https://api.exchangerate.host/latest",
        params={"base": "USD", "symbols": to},
        timeout=5
    )
    r.raise_for_status()
    rate = r.json().get("rates", {}).get(to, 0.0)
    return amount * rate

async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching price…")
    try:
        usd_raw = fetch_usd_price()  # e.g. "~ $2,643"
        await msg.edit_text(f"price 💵 : {usd_raw}")
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`", parse_mode=ParseMode.MARKDOWN)

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        usd_raw = fetch_usd_price()  # "~ $2,643"
        m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", usd_raw)
        amt = float(m.group(1).replace(",", "")) if m else 0.0

        # Real-time conversions
        cny = convert_currency(amt, "CNY")
        rub = convert_currency(amt, "RUB")

        results = []

        # USD result
        results.append(InlineQueryResultArticle(
            id=uuid.uuid4().hex,
            title="USD Price",
            description=usd_raw,
            input_message_content=InputTextMessageContent(
                f"price 💵 : {usd_raw}"
            )
        ))

        # CNY result
        cny_text = f"价格：{cny:,.2f} 元"
        results.append(InlineQueryResultArticle(
            id=uuid.uuid4().hex,
            title="人民币价格",
            description=cny_text,
            input_message_content=InputTextMessageContent(cny_text)
        ))

        # RUB result
        rub_text = f"Цена в российских рублях: {rub:,.2f} ₽"
        results.append(InlineQueryResultArticle(
            id=uuid.uuid4().hex,
            title="Российские рубли",
            description=rub_text,
            input_message_content=InputTextMessageContent(rub_text)
        ))

        # cache_time=0 → always fresh inline results
        await update.inline_query.answer(results, cache_time=0)
    except Exception:
        await update.inline_query.answer([], cache_time=0)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("floor", floor_cmd))
    app.add_handler(InlineQueryHandler(inline_query))
    print("Bot started in command & inline mode…")
    app.run_polling()
