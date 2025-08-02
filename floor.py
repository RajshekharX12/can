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
from dotenv import load_dotenv
from telegram.constants import ParseMode

load_dotenv()  # loads BOT_TOKEN, optional overrides

BOT_TOKEN         = os.getenv("BOT_TOKEN")
CHROME_BINARY     = os.getenv("CHROME_BINARY",     "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

def fetch_usd_price() -> str:
    """Scrape fragment.com and return USD price string, e.g. '~ $2,643'."""
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.binary_location = CHROME_BINARY

    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=opts)
    wait = WebDriverWait(driver, 15)
    try:
        driver.get("https://fragment.com/numbers?filter=sale")
        link = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        detail_url = link.get_attribute("href")

        driver.get(detail_url)
        wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"$")]')
        ))

        for el in driver.find_elements(By.XPATH, '//*[contains(text(),"$")]'):
            txt = el.text.replace("\n", " ").strip()
            if "~" in txt:
                return txt
        return "N/A"
    finally:
        driver.quit()

def convert_currency(amount: float, to: str) -> float:
    """
    Fetch real-time USD→<to> rate from open.er-api.com and convert.
    """
    try:
        resp = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=5
        )
        resp.raise_for_status()
        rates = resp.json().get("rates", {})
        rate = rates.get(to)
        if rate:
            return amount * rate
    except Exception:
        pass
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
        m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", usd_raw)
        amt = float(m.group(1).replace(",", "")) if m else 0.0

        # Real-time conversion
        cny_val = convert_currency(amt, "CNY")
        rub_val = convert_currency(amt, "RUB")

        cny_text = f"价格：{cny_val:,.2f} 元" if cny_val else "价格：N/A"
        rub_text = f"Цена в российских рублях: {rub_val:,.2f} ₽" if rub_val else "Цена в российских рублях: N/A"

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
                description=cny_text,
                input_message_content=InputTextMessageContent(cny_text)
            ),
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title="Российские рубли",
                description=rub_text,
                input_message_content=InputTextMessageContent(rub_text)
            ),
        ]

        # cache_time=0 ensures fresh data each inline query
        await update.inline_query.answer(results, cache_time=0)
    except Exception as e:
        await update.inline_query.answer([], cache_time=0)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("floor", floor_cmd))
    app.add_handler(InlineQueryHandler(inline_query))

    # Clean start: remove any webhook, drop pending updates
    asyncio.get_event_loop().run_until_complete(
        app.bot.delete_webhook(drop_pending_updates=True)
    )

    print("Bot started (polling)…")
    app.run_polling()
