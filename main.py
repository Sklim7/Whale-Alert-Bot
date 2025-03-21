import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import time
from collections import deque
import logging
import os

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration (use environment variables for sensitive data)
WALLET_URL = os.getenv("WALLET_URL", "https://hypurrscan.io/address/0x744cf47e88d9d0847544f0ac2fa7575cf5925f79")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 5))
POSITIONS_CHECK_INTERVAL = int(os.getenv("POSITIONS_CHECK_INTERVAL", 60))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ORDER_HISTORY_SIZE = int(os.getenv("ORDER_HISTORY_SIZE", 5))

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")  # Required for cloud environments
    chrome_options.add_argument("--disable-dev-shm-usage")  # Avoids issues in cloud environments
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124")
    
    # Use a remote WebDriver or rely on the cloud service's Chrome setup
    driver = webdriver.Chrome(options=chrome_options)
    logger.info("Chrome WebDriver initialized successfully")
    return driver

def get_latest_order(driver):
    try:
        driver.refresh()
        WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, "//button[4]/span[3]"))).click()
        time.sleep(1)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        rows = soup.find_all("tr")[1:]
        if not rows:
            logger.info("No order rows found")
            return None

        cells = rows[0].find_all("td")
        order_hash = cells[0].text.strip()
        amount = float(cells[5].text.strip().replace(",", ""))
        token = cells[6].text.strip()
        price = float(cells[7].text.strip().replace(",", "").replace("$", ""))
        value_usd = float(cells[8].text.strip().replace(",", "").replace("$", ""))
        position = "LONG" if amount > 0 else "SHORT"
        identifier = f"{order_hash}_{token}_{amount}_{price}"
        logger.info(f"New order found: {identifier}")
        return {
            "order_hash": order_hash,
            "token": token,
            "position": position,
            "amount": abs(amount),
            "price": price,
            "value_usd": value_usd,
            "identifier": identifier
        }
    except Exception as e:
        logger.error(f"Error fetching latest order: {e}")
        return None

def get_positions(driver):
    try:
        driver.refresh()
        WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, "//button[3]/span[3]"))).click()
        time.sleep(1)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        rows = soup.find("table")
        if not rows:
            logger.info("No position table found")
            return []

        positions = []
        for row in rows.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 10:
                continue
            try:
                positions.append({
                    "token": cells[0].text.strip(),
                    "position": cells[1].text.strip(),
                    "leverage": cells[2].text.strip(),
                    "value": float(cells[3].text.strip().replace(",", "").replace("$", "")),
                    "amount": float(cells[4].text.strip().split()[0].replace(",", "")),
                    "entry_price": float(cells[5].text.strip().replace(",", "").replace("$", "")),
                    "mark_price": float(cells[6].text.strip().replace(",", "").replace("$", "")),
                    "pnl": float(cells[7].text.strip().replace(",", "").replace("$", "")),
                    "funding": cells[8].text.strip(),
                    "liquidation_price": float(cells[9].text.strip().replace(",", "").replace("$", "")) if cells[9].text.strip() != "-" else None,
                    "id": f"{cells[0].text.strip()}_{cells[1].text.strip()}_{cells[5].text.strip()}"
                })
            except (ValueError, IndexError) as e:
                logger.warning(f"Error parsing position row: {e}")
                continue
        logger.info(f"Found {len(positions)} positions")
        return positions
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        return []

def format_change(current, previous):
    if previous is None:
        return ""
    diff = current - previous
    if diff > 0:
        return f" (⬆ +{diff:,.2f})"
    else:
        return f" (⬇ {diff:,.2f})"

def send_telegram_alert(order_details=None, positions=None, last_positions=None):
    try:
        if order_details:
            icon = "🟢" if order_details["position"] == "LONG" else "🔴"
            message = (
                f"🚨 Whale Alert!\n"
                f"{icon} [{order_details['token']}] {order_details['position']}\n"
                f"Price: ${order_details['price']:.6f}\n"
                f"Size: {order_details['amount']:,.2f} {order_details['token']}\n"
                f"Value: ${order_details['value_usd']:,.2f}\n"
                f"{WALLET_URL}"
            )
        elif positions is not None:
            if not positions:
                message = "📊 No open positions."
            else:
                message = "📊 Positions:\n"
                current_ids = {p["id"]: p for p in positions}
                last_ids = {p["id"]: p for p in last_positions} if last_positions else {}

                for pos in positions:
                    icon = "🟢" if pos["position"] == "LONG" else "🔴"
                    prev_pos = last_ids.get(pos["id"])
                    value_change = format_change(pos["value"], prev_pos["value"] if prev_pos else None)
                    size_change = format_change(pos["amount"], prev_pos["amount"] if prev_pos else None)
                    entry_change = format_change(pos["entry_price"], prev_pos["entry_price"] if prev_pos else None)
                    pnl_change = format_change(pos["pnl"], prev_pos["pnl"] if prev_pos else None)

                    message += (
                        f"{icon} {pos['token']} {pos['position']} {pos['leverage']}\n"
                        f"Value: ${pos['value']:,.2f}{value_change}, "
                        f"Size: {pos['amount']:,.2f}{size_change}\n"
                        f"Entry: ${pos['entry_price']:,.2f}{entry_change}, "
                        f"PnL: ${pos['pnl']:,.2f}{pnl_change}\n\n"
                    )

                for old_id in last_ids:
                    if old_id not in current_ids:
                        old_pos = last_ids[old_id]
                        icon = "🟢" if old_pos["position"] == "LONG" else "🔴"
                        message += f"{icon} {old_pos['token']} {old_pos['position']}\n(Closed)\n\n"
        else:
            message = "🐋 No new order."

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        response = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to send Telegram message: {response.text}")
        else:
            logger.info("Telegram message sent successfully")
    except Exception as e:
        logger.error(f"Error sending Telegram alert: {e}")

def main():
    driver = None
    try:
        driver = get_driver()
        order_history = deque(maxlen=ORDER_HISTORY_SIZE)
        last_positions_check = time.time()
        last_positions = []

        driver.get(WALLET_URL)
        logger.info(f"Started monitoring wallet: {WALLET_URL}")

        while True:
            try:
                order = get_latest_order(driver)
                if order and order["identifier"] not in order_history:
                    order_history.append(order["identifier"])
                    send_telegram_alert(order_details=order)
                else:
                    send_telegram_alert()

                if time.time() - last_positions_check >= POSITIONS_CHECK_INTERVAL:
                    current_positions = get_positions(driver)
                    send_telegram_alert(positions=current_positions, last_positions=last_positions)
                    last_positions = current_positions
                    last_positions_check = time.time()

                time.sleep(CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(CHECK_INTERVAL)  # Wait before retrying
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        if driver:
            driver.quit()
            logger.info("WebDriver closed")

if __name__ == "__main__":
    main()
