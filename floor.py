import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def floor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Checking floor price, please wait...")

    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")

        driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
        driver.get("https://fragment.com/numbers?filter=sale")
        time.sleep(3)  # Let JS load

        # Find the first number link
        first_link = driver.find_element(By.XPATH, '//a[contains(@href,"/number/888")]')
        number_url = first_link.get_attribute('href')

        driver.get(number_url)
        time.sleep(2)

        # Number itself
        number = number_url.split("/")[-1]

        # TON price
        ton_price_elem = driver.find_element(By.XPATH, '//div[contains(text(),"TON") or contains(text(),"ton")]')
        ton_price = ton_price_elem.text.strip()

        # USD price
        usd_price_elem = driver.find_element(By.XPATH, '//div[contains(text(),"~ $")]')
        usd_price = usd_price_elem.text.strip()

        result = (
            f"**Floor Number:** +888{number}\n"
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
