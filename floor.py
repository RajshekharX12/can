import warnings
from requests.exceptions import RequestsDependencyWarning
warnings.filterwarnings("ignore", category=RequestsDependencyWarning)

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
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"

def fetch_prices():
    """Return (curr_ton_raw, curr_ton_val, usd_raw, usd_val, sold_ton_val)."""
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = CHROME_BINARY

    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)
    wait = WebDriverWait(driver, 15)
    try:
        # — Current floor TON & USD —
        driver.get(SALE_URL)
        elems = driver.find_elements(By.XPATH, "//*[contains(text(),'TON')]")
        if elems:
            ton_text = elems[0].text
            m = re.search(r"([\d,]+)\s*TON", ton_text, re.IGNORECASE)
            curr_ton_raw = m.group(0).upper() if m else ton_text
            curr_ton_val = float(m.group(1).replace(",", "")) if m else 0.0
        else:
            curr_ton_raw, curr_ton_val = "N/A", 0.0

        elems = driver.find_elements(By.XPATH, "//*[contains(text(),'~') and contains(text(),'$')]")
        if elems:
            usd_raw = elems[0].text.strip()
            m = re.search(r"([\d,]+(?:\.\d+)?)", usd_raw)
            usd_val = float(m.group(1).replace(",", "")) if m else 0.0
        else:
            usd_raw, usd_val = "N/A", 0.0

        # — Last sold TON —
        driver.get(SOLD_URL)
        elems = driver.find_elements(By.XPATH, "//*[contains(text(),'TON')]")
        if elems:
            sold_text = elems[0].text
            m = re.search(r"([\d,]+)\s*TON", sold_text, re.IGNORECASE)
            sold_ton_val = float(m.group(1).replace(",", "")) if m else 0.0
        else:
            sold_ton_val = 0.0

        return curr_ton_raw, curr_ton_val, usd_raw, usd_val, sold_ton_val
    finally:
        driver.quit()

def fetch_ton_usdt_price() -> float:
    """Fetch live TON/USDT price from CoinGecko."""
    try:
        resp = requests.get(COINGECKO_URL, params={"ids":"toncoin","vs_currencies":"usdt"}, timeout=5)
        resp.raise_for_status()
        return float(resp.json().get("toncoin", {}).get("usdt", 0.0))
    except:
        return 0.0

async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching price…")
    try:
        curr_ton_raw, curr_ton_val, usd_raw, usd_val, sold_ton_val = fetch_prices()
        ton_usdt = fetch_ton_usdt_price()

        detail = ""
        if sold_ton_val > 0:
            diff_ton = curr_ton_val - sold_ton_val
            pct = diff_ton / sold_ton_val * 100
            usd_per_ton = usd_val / curr_ton_val if curr_ton_val else 0.0
            diff_usd = diff_ton * usd_per_ton
            action = "Rise by" if diff_ton >= 0 else "Fall by"
            detail = f"\n{action} {pct:+.2f}% ({diff_usd:+.2f} $)"

        text = (
            f"Current price of +888 number: {curr_ton_raw} ({usd_raw}){detail}\n"
            f"Live TON/USDT price: {ton_usdt:.4f} USDT"
        )
        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        curr_ton_raw, curr_ton_val, usd_raw, usd_val, sold_ton_val = fetch_prices()
        ton_usdt = fetch_ton_usdt_price()

        if sold_ton_val > 0:
            diff_ton = curr_ton_val - sold_ton_val
            pct = diff_ton / sold_ton_val * 100
            usd_per_ton = usd_val / curr_ton_val if curr_ton_val else 0.0
            diff_usd = diff_ton * usd_per_ton
            action_en = "Rise by" if diff_ton >= 0 else "Fall by"
            action_cn = "涨幅" if diff_ton >= 0 else "跌幅"
            action_ru = "Рост" if diff_ton >= 0 else "Падение"
        else:
            pct = diff_usdt = 0.0
            action_en = action_cn = action_ru = ""

        def conv(a, c):
            try:
                r = requests.get("https://open.er-api.com/v6/latest/USD", params={"symbols": c}, timeout=5)
                r.raise_for_status()
                rate = r.json().get("rates", {}).get(c, 0.0)
                return a * rate if rate else 0.0
            except:
                return 0.0

        cny_cur = conv(usd_val, "CNY")
        diff_cny = conv(diff_usd, "CNY")
        rub_cur = conv(usd_val, "RUB")
        diff_rub = conv(diff_usdt, "RUB")

        eng = f"Current price of +888 number: {curr_ton_raw} ({usd_raw})"
        if action_en:
            eng += f"\n{action_en} {pct:+.2f}% ({diff_usd:+.2f} $)"
        eng += f"\nLive TON/USDT price: {ton_usdt:.4f} USDT"

        chi = f"+888号码的当前价格：{curr_ton_raw} (~ {cny_cur:,.2f} 元)"
        if action_cn:
            chi += f"\n{action_cn}：{pct:+.2f}% ({diff_cny:,.2f} 元)"
        chi += f"\nTON/USDT 实时价格：{ton_usdt:.4f} USDT"

        rus = f"Текущая цена номера +888: {curr_ton_raw} (~ {rub_cur:,.2f} ₽)"
        if action_ru:
            rus += f"\n{action_ru}: {pct:+.2f}% ({diff_rub:+.2f} ₽)"
        rus += f"\nЦена TON/USDT: {ton_usdt:.4f} USDT"

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
