# Whale Alert Script Description

This Python script monitors a cryptocurrency wallet on the [hypurrscan.io](https://hypurrscan.io) website, specifically tracking new orders and position updates for a given wallet address. It uses web scraping to extract data, sends real-time alerts via Telegram, and compares position changes over time to provide detailed updates. Below is a comprehensive overview of its features, written in Markdown format.

---

## Features

### 1. **Real-Time Wallet Monitoring**
- **Target Wallet**: Monitors a specific wallet address on `hypurrscan.io` (e.g., `https://hypurrscan.io/address/0x744cf47e88d9d0847544f0ac2fa7575cf5925f79`).
- **Order Monitoring**: Checks for new orders every 5 seconds (`CHECK_INTERVAL = 5`).
- **Position Monitoring**: Updates position data every 60 seconds (`POSITIONS_CHECK_INTERVAL = 60`).
- **Headless Browser**: Uses Selenium with Chrome in headless mode to scrape the webpage without opening a visible browser window.

### 2. **Web Scraping with Selenium and BeautifulSoup**
- **Selenium Integration**:
  - Navigates to the wallet URL and interacts with the webpage (e.g., clicking tabs to access "ORDERS" and "POSITIONS").
  - Waits for elements to load using `WebDriverWait` to ensure reliable scraping.
  - Refreshes the page before each check to get the latest data.
- **BeautifulSoup Parsing**:
  - Parses the HTML content of the webpage to extract order and position data from tables.
  - Handles dynamic content by waiting for the table to load after tab clicks.

### 3. **Order Tracking and Alerts**
- **Order Extraction**:
  - Fetches the latest order from the "ORDERS" tab (assumed to be the 4th button on the page).
  - Extracts details such as transaction hash, amount, token, price, and USD value.
  - Determines the position type ("LONG" or "SHORT") based on the amount (positive for LONG, negative for SHORT).
- **Duplicate Prevention**:
  - Uses a `deque` (`order_history`) with a maximum length of 5 (`ORDER_HISTORY_SIZE = 5`) to track recent order identifiers.
  - Prevents sending duplicate alerts for the same order by checking if the order’s identifier is already in `order_history`.
- **Telegram Alerts**:
  - Sends a Telegram message for each new order with details:
    - Icon: `🟢` for LONG, `🔴` for SHORT.
    - Token and position (e.g., `[ETH] LONG`).
    - Price, size, and USD value.
    - Wallet URL for reference.
  - Example message:
    ```
    🚨 Whale Alert!
    🟢 [ETH] LONG
    Price: $2500.123456
    Size: 1.50 ETH
    Value: $3750.19
    https://hypurrscan.io/address/0x744cf47e88d9d0847544f0ac2fa7575cf5925f79
    ```
- **No Order Notification**: If no new order is detected, sends a simple message: `🐋 No new order.`

### 4. **Position Tracking and Comparison**
- **Position Extraction**:
  - Fetches all positions from the "POSITIONS" tab (assumed to be the 3rd button on the page).
  - Extracts details for each position, including token, position type, leverage, value, size, entry price, mark price, PnL, funding, and liquidation price.
  - Creates a unique ID for each position (`token_position_entry_price`) to track changes over time.
- **Change Detection**:
  - Compares current positions with the previous positions (`last_positions`) to detect changes in:
    - Value
    - Size
    - Entry Price
    - PnL
  - Indicates changes with arrows:
    - `⬆` for increases (e.g., `(⬆ +1.53)`).
    - `⬇` for decreases (e.g., `(⬇ -0.50)`).
  - If there’s no previous data (e.g., first run), no change is shown.
- **Closed Position Detection**:
  - Identifies positions that were in the previous data but are no longer in the current data, marking them as closed.
  - Reports closed positions with a `(Closed)` label.
- **Telegram Alerts**:
  - Sends a Telegram message listing all current positions with their details and changes.
  - Includes closed positions at the end of the message.
  - Example message:
    ```
    📊 Positions:
    🟢 ETH LONG 25X
    Value: $36.53 (⬆ +1.53), Size: 0.02 (⬇ 0.00)
    Entry: $1,967.30 (⬇ 0.00), PnL: $-0.06 (⬇ -0.02)

    🟢 LINK LONG 10X
    Value: $15.41, Size: 1.10
    Entry: $14.005, PnL: $-0.004

    🔴 TIA SHORT
    (Closed)
    ```
- **No Positions Notification**: If there are no positions, sends: `📊 No open positions.`

### 5. **Telegram Integration**
- **Bot Configuration**:
  - Uses a Telegram bot token (`TELEGRAM_BOT_TOKEN`) and chat ID (`TELEGRAM_CHAT_ID`) to send messages.
- **Message Formatting**:
  - Uses emojis for visual clarity (e.g., `🚨` for orders, `📊` for positions, `🟢` for LONG, `🔴` for SHORT).
  - Formats numbers with appropriate precision (e.g., prices to 6 decimal places, other values to 2 decimal places with thousand separators).
- **Reliable Sending**:
  - Sends messages via the Telegram API with a 10-second timeout to handle network issues.

### 6. **Error Handling and Robustness**
- **Web Scraping Errors**:
  - Handles missing or malformed table rows by skipping invalid data.
  - Uses `try-except` blocks to catch `IndexError` and `ValueError` during data parsing (e.g., if a number can’t be converted to a float).
- **Dynamic Page Loading**:
  - Waits for elements to be clickable before interacting with the page.
  - Adds a 1-second delay after clicking tabs to ensure the table loads.
- **Browser Cleanup**:
  - Uses a `try-finally` block in `main` to ensure the Selenium WebDriver is closed properly, even if the script crashes or is interrupted.

### 7. **Efficient Design**
- **Dictionary Lookups**:
  - Uses dictionaries (`current_ids` and `last_ids`) to efficiently compare current and previous positions by ID, avoiding nested loops.
- **Memory Management**:
  - Limits the `order_history` deque to 5 entries to prevent excessive memory usage.
- **Minimal Dependencies**:
  - Relies on standard libraries (`time`, `collections`) and well-known packages (`requests`, `selenium`, `beautifulsoup4`).

---

## Limitations
- **Webpage Dependency**: Relies on the structure of the `hypurrscan.io` webpage (e.g., XPath for tab buttons, table column indices). If the webpage changes, the script may break.
- **No Persistence Across Runs**: Does not persist the last order identifier across script runs, so it may send a duplicate alert for the last order after a restart.
- **Minimal Error Reporting**: Does not log errors or failed Telegram requests; it silently continues if a request fails.

---

## Potential Improvements
- **Add Persistence**: Implement file-based persistence for `order_history` to avoid duplicate alerts after a restart.
- **Enhanced Error Handling**: Log errors (e.g., failed Telegram requests, scraping issues) to a file for debugging.
- **Dynamic XPath**: Use more robust selectors (e.g., by button text or class) to handle webpage changes.
- **Configurability**: Allow configuration of intervals, URLs, and Telegram settings via a config file or command-line arguments.

---

This script is a powerful tool for monitoring cryptocurrency wallet activity, providing real-time insights into orders and positions with detailed change tracking, all delivered conveniently via Telegram.
