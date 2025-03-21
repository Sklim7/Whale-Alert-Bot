import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import time
import os
from collections import deque

# Configuration
WALLET_URL = "https://hypurrscan.io/address/0xf3f496c9486be5924a93d67e98298733bb47057c"
CHECK_INTERVAL =5
POSITIONS_CHECK_INTERVAL = 60
LAST_ORDER_FILE = "last_order.txt"
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
ORDER_HISTORY_SIZE = 5 # Maximum number of recent order identifiers to keep in memory to avoid processing duplicates

def get_driver():
    chrome_options = Options() #Creates a Chrome options object to configure the browser.
    chrome_options.add_argument("--headless") #Runs Chrome in headless mode (no visible browser window).
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124") #mimic a real browser, avoiding detection as a bot.
    return webdriver.Chrome(options=chrome_options)

def get_latest_order(driver):
    driver.refresh()
    WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, "//button[4]/span[3]"))).click()
    time.sleep(1)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    rows = soup.find_all("tr")[1:]
    if not rows:
        return None

    cells = rows[0].find_all("td") #Gets all cells (<td> tags) from the first row (latest order).
    try: #formating data by stripping
        order_hash = cells[0].text.strip() #Transaction hash (column 0).
        amount = float(cells[5].text.strip().replace(",", "")) #Order amount (column 5), converted to float after removing commas.
        token = cells[6].text.strip()
        price = float(cells[7].text.strip().replace(",", "").replace("$", ""))
        value_usd = float(cells[8].text.strip().replace(",", "").replace("$", ""))
        position = "LONG" if amount > 0 else "SHORT" #Determines the position type: "LONG" if amount is positive, "SHORT" if negative.
        identifier = f"{order_hash}_{token}_{amount}_{price}"
        return {"order_hash": order_hash, "token": token, "position": position, "amount": abs(amount),
                "price": price, "value_usd": value_usd, "identifier": identifier}
    except (IndexError, ValueError):
        return None

def get_positions(driver):
    #Refreshes the page
    driver.refresh()
    #clicks the "POSITIONS" tab (assumed to be the 3rd button), and waits 1 second for the table to load.
    WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, "//button[3]/span[3]"))).click()
    time.sleep(1)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    rows = soup.find("table")
    if not rows: #Parses the page HTML and finds the table. If no table is found, returns an empty list
        return []

    positions = [] #nitializes an empty list positions to store position data.
    for row in rows.find_all("tr")[1:]: #Loops through each table row, skipping the header row ([1:]).
        cells = row.find_all("td")
        if len(cells) < 10:#Gets all cells in the row; skips rows with fewer than 10 columns (incomplete data).
            continue
        try:
            positions.append({
                "token": cells[0].text.strip(), #Token name (column 0).
                "position": cells[1].text.strip(),#Position type (e.g., LONG/SHORT, column 1).
                "leverage": cells[2].text.strip(), #Leverage (e.g., 25X, column 2).
                "value": float(cells[3].text.strip().replace(",", "").replace("$", "")),#Position value (column 3), converted to float.
                "amount": float(cells[4].text.strip().split()[0].replace(",", "")), #Position size (column 4), takes the numeric part (e.g., "1.8287 ETH" → 1.8287).
                "entry_price": float(cells[5].text.strip().replace(",", "").replace("$", "")),
                "mark_price": float(cells[6].text.strip().replace(",", "").replace("$", "")),
                "pnl": float(cells[7].text.strip().replace(",", "").replace("$", "")),
                "funding": cells[8].text.strip(),
                "liquidation_price": float(cells[9].text.strip().replace(",", "").replace("$", "")) if cells[9].text.strip() != "-" else None, #Liquidation price (column 9), converted to float or None if it’s a dash (-).
                "id": f"{cells[0].text.strip()}_{cells[1].text.strip()}_{cells[5].text.strip()}"  # Unique identifier for the position (token + position + entry price).
            })
        except (ValueError, IndexError):
            continue
    return positions

def format_change(current, previous):
    if previous is None:
        return ""  # No previous data, no change to display
    diff = current - previous

    if diff ==0:
        return " (+ 0)"
    elif diff > 0:
        return f" (⬆ +{diff:,.2f})"
    else:
        return f" (⬇ {diff:,.2f})"

def send_telegram_alert(order_details=None, positions=None, last_positions=None):
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
            current_ids = {p["id"]: p for p in positions} #maps each position’s unique ID to its full data (the entire position dictionary). Allows quick lookups of position data by ID
            last_ids = {p["id"]: p for p in last_positions} if last_positions else {}

            for pos in positions:
                icon = "🟢" if pos["position"] == "LONG" else "🔴"
                # Get previous data for comparison
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

            # Check for removed positions
            for old_id in last_ids:
                if old_id not in current_ids:
                    old_pos = last_ids[old_id]
                    icon = "🟢" if old_pos["position"] == "LONG" else "🔴"
                    message += f"{icon} {old_pos['token']} {old_pos['position']}\n(Closed)\n\n"
    else:
        message = "🐋 No new order."

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)


def main():

    driver = get_driver()
    order_history = deque(maxlen=ORDER_HISTORY_SIZE)
    last_positions_check = time.time()
    last_positions = []  # Store the last known positions

    driver.get(WALLET_URL)
    try:
        while True:
            # Check orders
            order = get_latest_order(driver)
            if order and order["identifier"] not in order_history:
                order_history.append(order["identifier"])
                send_telegram_alert(order_details=order)

            else:
                send_telegram_alert()

            # Check positions every x minutes
            if time.time() - last_positions_check >= POSITIONS_CHECK_INTERVAL:
                current_positions = get_positions(driver)
                send_telegram_alert(positions=current_positions, last_positions=last_positions)
                last_positions = current_positions  # Update last known positions
                last_positions_check = time.time()

            time.sleep(CHECK_INTERVAL)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()

