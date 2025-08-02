import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv

# Load bot token from .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def floor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Checking floor price, please wait...")

    try:
        # Configure headless Chromium
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.binary_location = "/snap/bin/chromium"

        # Use webdriver-manager to install driver and start browser
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        # Navigate to the sale listings page
        driver.get("https://fragment.com/numbers?filter=sale")
        time.sleep(3)  # let JS render the page

        # Click the first number (floor price)
        first_link = driver.find_element(By.XPATH, '//a[contains(@href,"/number/888")]')
        number_url = first_link.get_attribute('href')

        # Visit the number’s page and extract prices
        driver.get(number_url)
        time.sleep(2)

        number = number_url.split("/")[-1]  # e.g. "88806973657"
        ton_price = driver.find_element(By.XPATH, '//div[contains(text(),"TON") or contains(text(),"ton")]').text.strip()
        usd_price = driver.find_element(By.XPATH, '//div[contains(text(),"~ $")]').text.strip()

        # Format and send the result
        result = (
            f"**Floor Number:** +{number}\n"
            f"**Price:** {ton_price} ({usd_price})\n"
            f"[View Number]({number_url})"
        )
        await msg.edit_text(result, parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        await msg.edit_text(f"❌ Failed to fetch floor price.\nError: `{e}`", parse_mode="Markdown")
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("floor", floor))
    print("Bot started...")
    app.run_polling()
