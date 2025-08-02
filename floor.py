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

# Load configuration
load_dotenv()
BOT_TOKEN         = os.getenv("BOT_TOKEN")
CHROME_BINARY     = os.getenv("CHROME_BINARY",     "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

SALE_LIST_URL = "https://fragment.com/numbers?filter=sale"

def create_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = CHROME_BINARY
    return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)

def fetch_current_price():
    """
    Scrape the first +888 sale detail page and return (raw_text, numeric_value).
    """
    driver = create_driver()
    wait = WebDriverWait(driver, 10)
    try:
        # 1) find detail URL
        driver.get(SALE_LIST_URL)
        link = wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        detail_url = link.get_attribute("href")
        # 2) scrape USD price
        driver.get(detail_url)
        elem = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"~") and contains(text(),"$")]')
        ))
        raw = elem.text.replace("\n"," ").strip()  # e.g. "~ $2,589"
        m = re.search(r"\$\s*([\d,]+)", raw)
        val = float(m.group(1).replace(",","")) if m else 0.0
        return raw, val
    finally:
        driver.quit()

async def floor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Fetching current floor price…")
    raw, _ = fetch_current_price()
    text = f"Current price of +888 number: ({raw})"
    await msg.edit_text(text)

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw, _ = fetch_current_price()
    # prepare texts
    eng = f"Current price of +888 number: ({raw})"
    chi = f"+888号码的当前价格：({raw})"
    rus = f"Текущая цена номера +888: ({raw})"
    esp = f"Precio actual del número +888: ({raw})"
    results = [
        InlineQueryResultArticle(id=uuid.uuid4().hex, title="🇺🇸 English", description=eng,
                                 input_message_content=InputTextMessageContent(eng)),
        InlineQueryResultArticle(id=uuid.uuid4().hex, title="🇨🇳 中文", description=chi,
                                 input_message_content=InputTextMessageContent(chi)),
        InlineQueryResultArticle(id=uuid.uuid4().hex, title="🇷🇺 Русский", description=rus,
                                 input_message_content=InputTextMessageContent(rus)),
        InlineQueryResultArticle(id=uuid.uuid4().hex, title="🇪🇸 Español", description=esp,
                                 input_message_content=InputTextMessageContent(esp)),
    ]
    await update.inline_query.answer(results, cache_time=0)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("floor", floor_cmd))
    app.add_handler(InlineQueryHandler(inline_query))
    asyncio.get_event_loop().run_until_complete(
        app.bot.delete_webhook(drop_pending_updates=True)
    )
    app.run_polling()

