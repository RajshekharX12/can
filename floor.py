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
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ApplicationBuilder, CommandHandler, InlineQueryHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN         = os.getenv("BOT_TOKEN")
CHROME_BINARY     = os.getenv("CHROME_BINARY",     "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

SALE_URL = "https://fragment.com/numbers?filter=sale"
SOLD_URL = "https://fragment.com/numbers?sort=ending&filter=sold"

def fetch_prices():
    """
    Scrape live values:
      - current floor TON & USD from SALE_URL
      - last sold TON from SOLD_URL
    Returns:
      curr_ton_raw: str, e.g. "740 TON"
      curr_ton_val: float, e.g. 740.0
      usd_raw     : str, e.g. "~ $2,643"
      usd_val     : float, e.g. 2643.0
      sold_ton_val: float, e.g. 720.0
    """
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
        # 1) current floor
        driver.get(SALE_URL)
        ton_elem = wait.until(EC.presence_of_element_located(
            (By.XPATH, '(//div[contains(text(),"TON")])[1]')
        ))
        curr_ton_raw = ton_elem.text.strip()
        curr_ton_val = float(curr_ton_raw.split()[0].replace(",", ""))

        usd_elem = driver.find_element(By.XPATH, '(//div[contains(text(),"~")])[1]')
        usd_raw = usd_elem.text.strip()
        m_usd = re.search(r'([\d,]+(?:\.\d+)?)', usd_raw)
        usd_val = float(m_usd.group(1).replace(",", "")) if m_usd else 0.0

        # 2) last sold
        driver.get(SOLD_URL)
        sold_elem = wait.until(EC.presence_of_element_located(
            (By.XPATH, '(//div[contains(text(),"TON")])[1]')
        ))
        sold_ton_val = float(sold_elem.text.split()[0].replace(",", ""))

        return curr_ton_raw, curr_ton_val, usd_raw, usd_val, sold_ton_val
    finally:
        driver.quit()

def convert_currency(amount: float, to: str) -> float:
    """Convert USD→<to> using open.er-api.com free endpoint."""
    try:
        resp = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
        resp.raise_for_status()
        rate = resp.json().get("rates", {}).get(to, 0.0)
        return amount * rate if rate else 0.0
    except:
        return 0.0

async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching price…")
    try:
        curr_ton_raw, curr_ton_val, usd_raw, usd_val, sold_ton_val = fetch_prices()

        diff_ton = curr_ton_val - sold_ton_val
        pct = (diff_ton / sold_ton_val * 100) if sold_ton_val else 0.0
        usd_per_ton = (usd_val / curr_ton_val) if curr_ton_val else 0.0
        diff_usd = diff_ton * usd_per_ton

        action = "Rise by" if diff_ton >= 0 else "Fall by"
        text = (
            f"Current price of +888 number: {curr_ton_raw} ({usd_raw})\n"
            f"{action} {pct:+.2f}% ({diff_usd:+.2f} $)"
        )

        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        curr_ton_raw, curr_ton_val, usd_raw, usd_val, sold_ton_val = fetch_prices()

        diff_ton = curr_ton_val - sold_ton_val
        pct = (diff_ton / sold_ton_val * 100) if sold_ton_val else 0.0
        usd_per_ton = (usd_val / curr_ton_val) if curr_ton_val else 0.0
        diff_usd = diff_ton * usd_per_ton

        # convert USD values
        cny_current = convert_currency(usd_val, "CNY")
        rub_current = convert_currency(usd_val, "RUB")
        diff_cny = convert_currency(diff_usd, "CNY")
        diff_rub = convert_currency(diff_usd, "RUB")

        action_en = "Rise by" if diff_ton >= 0 else "Fall by"
        action_cn = "涨幅" if diff_ton >= 0 else "跌幅"
        action_ru = "Рост" if diff_ton >= 0 else "Падение"

        eng = (
            f"Current price of +888 number: {curr_ton_raw} ({usd_raw})\n"
            f"{action_en} {pct:+.2f}% ({diff_usd:+.2f} $)"
        )
        chi = (
            f"+888号码的当前价格：{curr_ton_raw} (~ {cny_current:,.2f} 元)\n"
            f"{action_cn}：{pct:+.2f}% ({diff_cny:+.2f} 元)"
        )
        rus = (
            f"Текущая цена номера +888: {curr_ton_raw} (~ {rub_current:,.2f} ₽)\n"
            f"{action_ru}: {pct:+.2f}% ({diff_rub:+.2f} ₽)"
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

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("floor", floor_cmd))
    app.add_handler(InlineQueryHandler(inline_query))

    # clean start
    asyncio.get_event_loop().run_until_complete(
        app.bot.delete_webhook(drop_pending_updates=True)
    )

    print("Bot started (polling)…")
    app.run_polling()
