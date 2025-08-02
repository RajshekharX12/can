import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHROME_BINARY = os.getenv("CHROME_BINARY", "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

async def floor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Checking floor price, please wait…")
    driver = None
    try:
        # 1️⃣ Setup headless Chromium
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")
        opts.binary_location = CHROME_BINARY
        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=opts)
        wait = WebDriverWait(driver, 15)

        # 2️⃣ Go to list page & grab first number link
        driver.get("https://fragment.com/numbers?filter=sale")
        first_a = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        number_url = first_a.get_attribute("href")

        # 3️⃣ Navigate to detail page & wait for TON to show
        driver.get(number_url)
        ton_elem = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"TON") or contains(text(),"ton")]')
        ))
        ton_price = ton_elem.text.strip()

        # 4️⃣ Find USD by scanning all elements with “$” and picking the one with “~”
        usd_price = "N/A"
        for el in driver.find_elements(By.XPATH, '//*[contains(text(),"$")]'):
            txt = el.text.replace("\n", " ").strip()
            if "~" in txt:
                usd_price = txt
                break

        # 5️⃣ Build & send result
        number = number_url.rstrip("/").split("/")[-1]
        text = (
            f"**Floor Number:** +888{number}\n"
            f"**Price:** {ton_price} ({usd_price})\n"
            f"[View on fragment.com]({number_url})"
        )
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

    except Exception as e:
        await msg.edit_text(f"❌ Failed to fetch floor price.\nError: `{e}`",
                            parse_mode=ParseMode.MARKDOWN)
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("floor", floor))
    print("Bot started…")
    app.run_polling()
