import os
import re
import requests
import asyncio
import uuid
import sqlite3
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
from telegram.constants import ParseMode
from dotenv import load_dotenv

# ─── ENV & PATHS ───────────────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN         = os.getenv("BOT_TOKEN")
CHROME_BINARY     = os.getenv("CHROME_BINARY",     "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
DB_PATH           = os.getenv("DB_PATH", "prices.db")

# ─── DB SETUP ─────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("""
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    usd_price REAL
)
""")
conn.commit()

def get_last_price() -> float | None:
    row = conn.execute("SELECT usd_price FROM history ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else None

def record_price(price: float):
    conn.execute("INSERT INTO history(usd_price) VALUES(?)", (price,))
    conn.commit()

# ─── SCRAPE & CONVERT ────────────────────────────────────────────────────────
def fetch_usd_price() -> tuple[str, float]:
    """Returns (raw_text, numeric_usd) for the floor price."""
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = CHROME_BINARY

    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)
    wait = WebDriverWait(driver, 15)
    try:
        driver.get("https://fragment.com/numbers?filter=sale")
        first = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        detail_url = first.get_attribute("href")

        driver.get(detail_url)
        wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"$")]')
        ))

        raw = "N/A"
        for el in driver.find_elements(By.XPATH, '//*[contains(text(),"$")]'):
            t = el.text.replace("\n"," ").strip()
            if "~" in t:
                raw = t
                break

        # parse numeric USD
        m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", raw)
        amt = float(m.group(1).replace(",", "")) if m else 0.0

        return raw, amt
    finally:
        driver.quit()

def convert_currency(amount: float, to: str) -> float:
    """Convert USD→to using free open.er-api.com rates."""
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
        r.raise_for_status()
        rate = r.json().get("rates", {}).get(to)
        return amount * rate if rate else 0.0
    except:
        return 0.0

# ─── /floor COMMAND ───────────────────────────────────────────────────────────
async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching price…")
    try:
        raw, current = fetch_usd_price()
        prev = get_last_price()
        record_price(current)

        if prev:
            diff = current - prev
            pct = (diff/prev)*100
            sign = "+" if diff>=0 else ""
            diff_usd = f"{sign}{diff:,.2f} $"
        else:
            pct = None
            diff_usd = None

        lines = [f"Current price of +888 number: {raw}"]
        if pct is not None:
            lines.append(f"Fall by {pct:+.2f}% ({diff_usd})")
        text = "\n".join(lines)

        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`", parse_mode=ParseMode.MARKDOWN)

# ─── INLINE QUERY ─────────────────────────────────────────────────────────────
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw, current = fetch_usd_price()
        prev = get_last_price()
        record_price(current)

        # compute diffs
        if prev:
            diff = current - prev
            pct = (diff/prev)*100
            sign = "+" if diff>=0 else ""
            diff_usd = f"{sign}{diff:,.2f} $"
        else:
            pct = None
            diff_usd = None

        # conversions
        cny = convert_currency(current, "CNY")
        prev_cny = convert_currency(prev, "CNY") if prev else 0.0
        diff_cny = cny - prev_cny
        rub = convert_currency(current, "RUB")
        prev_rub = convert_currency(prev, "RUB") if prev else 0.0
        diff_rub = rub - prev_rub

        # build messages
        eng = f"Current price of +888 number: {raw}"
        if pct is not None:
            eng += f"\nFall by {pct:+.2f}% ({diff_usd})"

        chi = f"+888号码的当前价格：{cny:,.2f} 元"
        if pct is not None:
            chi += f"\n跌幅：{pct:+.2f}% ({sign}{diff_cny:,.2f} 元)"

        rus = f"Текущая цена номера +888: {rub:,.2f} ₽"
        if pct is not None:
            rus += f"\nПадение: {pct:+.2f}% ({sign}{diff_rub:,.2f} ₽)"

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

# ─── ENTRY POINT ─────────────────────────────────────────────────────────────
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
