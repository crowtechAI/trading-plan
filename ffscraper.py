#!/usr/bin/env python3
"""
Forex Factory Economic Calendar Scraper
Improved version combining functionality from both scripts
Scrapes economic events and saves to CSV for trading analysis
"""

import os
import sys
import time
import csv
import argparse
import pandas as pd
from datetime import datetime, timedelta
import pytz
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException

# Configuration
BASE_URL = "https://www.forexfactory.com/calendar"
OUTPUT_FILE = "latest_forex_data.csv"
TIMEOUT = 45  # Increased timeout for cloud environments
RETRY_ATTEMPTS = 2 # Reduced retries to fail faster during debugging
RETRY_DELAY = 10

# Element type mappings for proper data extraction
ALLOWED_ELEMENT_TYPES = {
    "calendar__cell calendar__date": "date",
    "calendar__cell calendar__time": "time", 
    "calendar__cell calendar__currency": "currency",
    "calendar__cell calendar__impact": "impact",
    "calendar__cell calendar__event": "event",
    "calendar__cell calendar__actual": "actual",
    "calendar__cell calendar__forecast": "forecast",
    "calendar__cell calendar__previous": "previous"
}

def is_streamlit_cloud():
    """Detect if running on Streamlit Cloud or similar environment"""
    return (
        os.getenv('STREAMLIT_SHARING_MODE') == 'true' or
        'streamlit' in str(os.getcwd()).lower() or
        os.path.exists('/usr/bin/chromium') or
        'STREAMLIT' in os.environ or
        any('streamlit' in str(arg).lower() for arg in sys.argv) or
        os.path.exists('/mount/src')
    )

def init_driver():
    """Initialize Chrome WebDriver with environment-specific settings"""
    print("Initializing WebDriver...")
    
    options = Options()
    
    # Essential headless options
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-extensions')
    options.add_argument("--disable-images")
    options.add_argument('--remote-debugging-port=9222')
    
    # Options to avoid detection
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36')
    
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    try:
        if is_streamlit_cloud():
            print("Detected Streamlit Cloud environment")
            service = Service('/usr/bin/chromedriver')
        else:
            print("Detected local environment")
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
            except ImportError:
                print("webdriver-manager not available, using system chromedriver")
                service = Service()
        
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        print("WebDriver initialized successfully")
        return driver
        
    except Exception as e:
        print(f"Fatal error initializing WebDriver: {str(e)}")
        raise

def convert_gmt_to_gmt_minus_5(time_str, date_str):
    """Convert GMT time to GMT-5, accounting for daylight saving time"""
    if not time_str or time_str == "empty" or not date_str or date_str == "empty":
        return time_str
    
    special_times = ["all day", "day 1", "day 2", "tentative", "holiday", "tbd"]
    if time_str.lower() in special_times:
        return time_str
    
    try:
        date_obj = datetime.strptime(date_str, "%d/%m/%Y").date()
        
        if "am" in time_str.lower() or "pm" in time_str.lower():
            time_obj = datetime.strptime(time_str, "%I:%M%p").time()
        else:
            time_obj = datetime.strptime(time_str, "%H:%M").time()
        
        gmt_datetime = datetime.combine(date_obj, time_obj)
        gmt_datetime = pytz.UTC.localize(gmt_datetime)
        
        gmt_minus_5_tz = pytz.timezone('Etc/GMT+5')
        gmt_minus_5_datetime = gmt_datetime.astimezone(gmt_minus_5_tz)
        
        return gmt_minus_5_datetime.strftime("%I:%M%p").lower().lstrip('0')
        
    except (ValueError, TypeError) as e:
        print(f"Error converting time {time_str} for date {date_str}: {e}")
        return time_str

def get_current_week_range():
    """Get the Monday-Friday range for the current trading week"""
    today = datetime.now()
    current_weekday = today.weekday()
    
    if current_weekday >= 5:
        days_until_monday = 7 - current_weekday
        monday = today + timedelta(days=days_until_monday)
    else:
        days_since_monday = current_weekday
        monday = today - timedelta(days=days_since_monday)
    
    friday = monday + timedelta(days=4)
    return monday.date(), friday.date()

def is_date_in_current_week(date_str, week_start, week_end):
    """Check if a date string is within the current trading week"""
    try:
        date_obj = datetime.strptime(date_str, "%d/%m/%Y").date()
        return week_start <= date_obj <= week_end
    except (ValueError, TypeError):
        return False

def clean_cell_text(element):
    """Extract clean text from table cells, handling special cases"""
    try:
        if "calendar__impact" in element.get_attribute("class"):
            impact_span = element.find_element(By.TAG_NAME, "span")
            return impact_span.get_attribute("title").replace(" Impact Expected", "")
        
        text = element.get_attribute("innerText")
        return text.strip() if text else "empty"
    except:
        return "empty"

def scrape_calendar_data(driver, month, year, week_filter=False):
    """Scrape economic calendar data from Forex Factory"""
    print(f"Scraping data for {month} {year}")
    
    url = f"{BASE_URL}?month=this"
    print(f"Navigating to: {url}")
    driver.get(url)

    try:
        # First, try to find and click the "Accept all" cookie button
        print("Looking for cookie consent button...")
        cookie_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept all')]"))
        )
        cookie_button.click()
        print("Clicked cookie consent button.")
        time.sleep(3) # Wait for overlay to disappear
    except TimeoutException:
        print("Cookie consent button not found or not clickable, continuing...")

    data = []
    current_date = None
    last_time = "empty"

    if week_filter:
        week_start, week_end = get_current_week_range()
        print(f"Filtering for trading week: {week_start.strftime('%d/%m/%Y')} to {week_end.strftime('%d/%m/%Y')}")

    try:
        # CRITICAL CHANGE: Wait for the table to be present right before scraping
        print("Waiting for calendar table to load...")
        table = WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, "calendar__table"))
        )
        print("Calendar table found successfully. Starting scrape.")
        
        # Scroll to load all rows
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(5)

        for row in table.find_elements(By.TAG_NAME, "tr"):
            if "calendar__row--day-breaker" in row.get_attribute("class"):
                continue

            row_data = {k: 'empty' for k in ['date', 'time', 'currency', 'impact', 'event', 'actual', 'forecast', 'previous']}
            cells = row.find_elements(By.CLASS_NAME, "calendar__cell")
            has_time = False

            for cell in cells:
                class_name = cell.get_attribute("class").strip()
                key = ALLOWED_ELEMENT_TYPES.get(class_name)

                if key:
                    value = clean_cell_text(cell)
                    if key == "date" and value and value != "empty":
                        try:
                            parsed_date = datetime.strptime(value + f" {datetime.now().year}", "%a %b %d %Y")
                            current_date = parsed_date.strftime("%d/%m/%Y")
                            value = current_date
                        except ValueError:
                            current_date = "invalid"
                    elif key == "time" and value and value != "empty":
                        converted_time = convert_gmt_to_gmt_minus_5(value, current_date)
                        last_time = converted_time
                        has_time = True
                        value = converted_time
                    row_data[key] = value

            if not has_time:
                row_data["time"] = last_time
            row_data["date"] = current_date if current_date else "empty"

            if any(v != "empty" for k, v in row_data.items() if k != "date"):
                if not week_filter or (current_date and is_date_in_current_week(current_date, week_start, week_end)):
                    data.append(row_data)

        print(f"Found {len(data)} events.")

    except TimeoutException:
        # *** ESSENTIAL DEBUGGING STEP ***
        print(f"CRITICAL ERROR: Timed out waiting for '.calendar__table' after {TIMEOUT} seconds.")
        print("The page did not load the expected content. This is likely due to anti-scraping measures.")
        
        # Save the page source and a screenshot for manual inspection
        with open("debug_page_source.html", "w", encoding='utf-8') as f:
            f.write(driver.page_source)
        driver.save_screenshot("debug_screenshot.png")
        
        print("\n*** Saved 'debug_page_source.html' and 'debug_screenshot.png' for analysis. ***")
        print("Please check these files to see if there is a CAPTCHA or a block page.")
        raise
    except Exception as e:
        print(f"An unexpected error occurred during scraping: {str(e)}")
        raise

    return data

def save_to_csv(events, filename=None, month=None, year=None):
    """Save events to CSV file"""
    if not events:
        print("No events to save")
        return
    
    filename = filename if filename else f"forex_calendar_{month}_{year}.csv" if month and year else OUTPUT_FILE
    print(f"Saving {len(events)} events to {filename}")
    
    fieldnames = ['date', 'time', 'currency', 'impact', 'event', 'actual', 'forecast', 'previous']
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(events)
    print(f"Data saved successfully to {filename}")

def get_target_month(arg_month=None, week_mode=False):
    """Get target month and year for scraping"""
    now = datetime.now()
    if week_mode:
        target_date = get_current_week_range()[0] if now.weekday() >= 5 else now.date()
        return target_date.strftime("%B"), target_date.strftime("%Y")
    return arg_month if arg_month else now.strftime("%B"), now.strftime("%Y")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Scrape Forex Factory Economic Calendar')
    parser.add_argument('--month', type=str, help='Target month (e.g. June, July). Defaults to current month.')
    parser.add_argument('--week', action='store_true', help='Only scrape current trading week (Mon-Fri)')
    parser.add_argument('--output', default=None, help='Output CSV filename (auto-generated if not specified)')
    
    args = parser.parse_args()
    
    print("=== Forex Factory Economic Calendar Scraper ===")
    
    week_mode = args.week
    month, year = get_target_month(args.month, week_mode)
    
    if week_mode:
        print(f"Week mode enabled: Targeting current/upcoming trading week.")
    
    driver = None
    try:
        driver = init_driver()
        events = None
        for attempt in range(RETRY_ATTEMPTS):
            try:
                print(f"\nAttempt {attempt + 1}/{RETRY_ATTEMPTS}")
                events = scrape_calendar_data(driver, month, year, week_filter=week_mode)
                break
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < RETRY_ATTEMPTS - 1:
                    print(f"Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
                else:
                    raise Exception("All retry attempts failed.")
        
        if events:
            save_to_csv(events, args.output, month, year)
            print("\n=== Scraping completed successfully ===")
        else:
            print("\n--- No events were scraped. ---")
            
    except KeyboardInterrupt:
        print("\nScraping interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unrecoverable error occurred: {str(e)}")
        sys.exit(1)
    finally:
        if driver:
            driver.quit()
            print("WebDriver closed successfully.")

if __name__ == "__main__":
    main()
