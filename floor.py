import os
import re
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

load_dotenv()  # loads BOT_TOKEN, optional CHROME_BINARY & CHROMEDRIVER_PATH
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHROME_BINARY = os.getenv("CHROME_BINARY", "/usr/bin/chromium-browser")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

async def floor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Checking floor price, please wait…")
    driver = None
    try:
        # 1) Setup headless Chromium
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.binary_location = CHROME_BINARY

        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 15)

        # 2) Go to the list page, wait for first link
        list_url = "https://fragment.com/numbers?filter=sale"
        driver.get(list_url)
        first_elem = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//a[contains(@href,"/number/888")]')
        ))
        number_url = first_elem.get_attribute("href")

        # 3) Go to the number’s page, wait for TON text to appear
        driver.get(number_url)
        wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"TON") or contains(text(),"ton")]')
        ))

        # 4) Extract via regex from page_source
        html = driver.page_source
        ton_m = re.search(r'([\d,]+)\s*TON', html, re.IGNORECASE)
        usd_m = re.search(r'~\s*\$\s*([\d,]+(?:\.\d+)?)', html)

        ton_price = f"{ton_m.group(1)} TON" if ton_m else "N/A"
        usd_price = f"~ ${usd_m.group(1)}" if usd_m else "N/A"
        number = number_url.rstrip("/").split("/")[-1]

        # 5) Send result
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
