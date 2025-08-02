import warnings
from requests.exceptions import RequestsDependencyWarning
warnings.filterwarnings("ignore", category=RequestsDependencyWarning)

import os, re, asyncio, uuid
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

def fetch_detail_prices(listing_url: str):
    """Click first +888 link in `listing_url`, return (ton_val, usd_val)."""
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = CHROME_BINARY

    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)
    wait = WebDriverWait(driver, 15)
    try:
        # Go to listing & click first +888
        driver.get(listing_url)
        link = wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        url = link.get_attribute("href")

        # Now on detail page
        driver.get(url)

        # TON: first element containing " TON"
        ton_elem = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"TON")]')
        ))
        ton_val = float(re.search(r"([\d,]+)", ton_elem.text).group(1).replace(",", ""))

        # USD: first element containing "~" and "$"
        usd_elem = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"~") and contains(text(),"$")]')
        ))
        usd_val = float(re.search(r"\$\s*([\d,]+(?:\.\d+)?)", usd_elem.text).group(1).replace(",", ""))

        return ton_val, usd_val
    finally:
        driver.quit()

async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching prices…")
    try:
        sale_ton, sale_usd = fetch_detail_prices(SALE_URL)
        sold_ton, sold_usd = fetch_detail_prices(SOLD_URL)

        diff_usd = sale_usd - sold_usd
        pct = (diff_usd / sold_usd * 100) if sold_usd else 0.0
        action = "Fall by" if diff_usd < 0 else "Rise by"

        text = (f"Current price of +888 number: {sale_ton:.0f} TON (~ ${sale_usd:,.0f})\n"
                f"{action} {pct:+.2f}% ({diff_usd:+.2f} $)")
        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sale_ton, sale_usd = fetch_detail_prices(SALE_URL)
        sold_ton, sold_usd = fetch_detail_prices(SOLD_URL)

        diff_usd = sale_usd - sold_usd
        pct = (diff_usd / sold_usd * 100) if sold_usd else 0.0

        action_en = "Fall by" if diff_usd < 0 else "Rise by"
        action_cn = "跌幅"  if diff_usd < 0 else "涨幅"
        action_ru = "Падение" if diff_usd < 0 else "Рост"

        eng = (f"Current price of +888 number: {sale_ton:.0f} TON (~ ${sale_usd:,.0f})\n"
               f"{action_en} {pct:+.2f}% ({diff_usd:+.2f} $)")
        chi = (f"+888号码的当前价格：{sale_ton:.0f} TON (~ ${sale_usd:,.0f})\n"
               f"{action_cn}：{pct:+.2f}% ({diff_usd:+.2f} $)")
        rus = (f"Текущая цена номера +888: {sale_ton:.0f} TON (~ ${sale_usd:,.0f})\n"
               f"{action_ru}: {pct:+.2f}% ({diff_usd:+.2f} $)")

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

    asyncio.get_event_loop().run_until_complete(
        app.bot.delete_webhook(drop_pending_updates=True)
    )
    app.run_polling()
