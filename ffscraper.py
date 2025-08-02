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
TIMEOUT = 30
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5

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
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-images')
    options.add_argument('--remote-debugging-port=9222')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-features=TranslateUI')
    options.add_argument('--disable-default-apps')
    options.add_argument('--disable-web-security')
    options.add_argument('--disable-features=VizDisplayCompositor')
    
    # Additional options to avoid detection and improve compatibility
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--no-first-run')
    options.add_argument('--disable-infobars')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-popup-blocking')
    
    # User agent to avoid detection
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    
    # Exclude automation switches
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    try:
        if is_streamlit_cloud():
            print("Detected Streamlit Cloud environment")
            options.binary_location = '/usr/bin/chromium'
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
        print(f"Error initializing WebDriver: {str(e)}")
        # Fallback
        try:
            print("Attempting fallback initialization...")
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            if is_streamlit_cloud():
                options.binary_location = '/usr/bin/chromium'
                service = Service('/usr/bin/chromedriver')
            else:
                service = Service()
                
            driver = webdriver.Chrome(service=service, options=options)
            print("Fallback WebDriver initialized successfully")
            return driver
            
        except Exception as fallback_error:
            print(f"Fallback also failed: {str(fallback_error)}")
            raise Exception(f"Could not initialize WebDriver. Original error: {str(e)}, Fallback error: {str(fallback_error)}")

def convert_gmt_to_gmt_minus_5(time_str, date_str):
    """Convert GMT time to GMT-5, accounting for daylight saving time"""
    if not time_str or time_str == "empty" or not date_str or date_str == "empty":
        return time_str
    
    # Handle special time values that aren't actual times
    special_times = ["all day", "day 1", "day 2", "tentative", "holiday", "tbd"]
    if time_str.lower() in special_times:
        return time_str
    
    try:
        # Parse the date (DD/MM/YYYY format)
        date_obj = datetime.strptime(date_str, "%d/%m/%Y").date()
        
        # Parse the time string
        if "am" in time_str.lower() or "pm" in time_str.lower():
            time_obj = datetime.strptime(time_str, "%I:%M%p").time()
        else:
            time_obj = datetime.strptime(time_str, "%H:%M").time()
        
        # Combine date and time
        gmt_datetime = datetime.combine(date_obj, time_obj)
        
        # Set timezone to UTC (same as GMT)
        utc_tz = pytz.UTC
        gmt_datetime = utc_tz.localize(gmt_datetime)
        
        # Convert to GMT-5 Time
        gmt_minus_5_tz = pytz.timezone('Etc/GMT+5')
        gmt_minus_5_datetime = gmt_datetime.astimezone(gmt_minus_5_tz)
        
        # Format back to 12-hour format
        return gmt_minus_5_datetime.strftime("%I:%M%p").lower().lstrip('0')
        
    except (ValueError, TypeError) as e:
        print(f"Error converting time {time_str} for date {date_str}: {e}")
        return time_str

def get_current_week_range():
    """Get the Monday-Friday range for the current trading week"""
    today = datetime.now()
    current_weekday = today.weekday()  # Monday is 0, Sunday is 6
    
    if current_weekday >= 5:  # Saturday (5) or Sunday (6)
        # Get next Monday (start of next week)
        days_until_monday = 7 - current_weekday
        monday = today + timedelta(days=days_until_monday)
    else:  # Monday (0) to Friday (4)
        # Get Monday of current week
        days_since_monday = current_weekday
        monday = today - timedelta(days=days_since_monday)
    
    # Calculate Friday of that week
    friday = monday + timedelta(days=4)
    
    return monday.date(), friday.date()

def is_date_in_current_week(date_str, week_start, week_end):
    """Check if a date string is within the current trading week"""
    try:
        date_obj = datetime.strptime(date_str, "%d/%m/%Y").date()
        return week_start <= date_obj <= week_end
    except (ValueError, TypeError):
        return False

def scroll_to_end(driver):
    """Scroll to the end of the page to load all content"""
    previous_position = None
    while True:
        current_position = driver.execute_script("return window.pageYOffset;")
        driver.execute_script("window.scrollTo(0, window.pageYOffset + 500);")
        time.sleep(1.5)
        if current_position == previous_position:
            break
        previous_position = current_position

def clean_cell_text(element):
    """Extract clean text from table cells, handling special cases"""
    try:
        # Specifically handle the impact cell by checking the span's title
        if "calendar__impact" in element.get_attribute("class"):
            impact_span = element.find_element(By.TAG_NAME, "span")
            if impact_span:
                return impact_span.get_attribute("title").replace(" Impact Expected", "")
        
        text = element.get_attribute("innerText")
        if text:
            return text.strip()
        spans = element.find_elements(By.TAG_NAME, "span")
        if spans:
            return spans[0].text.strip()
        return "empty"
    except:
        return "empty"

def wait_for_page_load(driver, timeout=TIMEOUT):
    """Wait for the page to fully load"""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(3)  # Additional wait for dynamic content
        
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "calendar__table"))
            )
        except TimeoutException:
            print("Calendar table not found immediately, but continuing...")
        
        return True
    except TimeoutException:
        print("Page load timeout")
        return False

def scrape_calendar_data(driver, month, year, week_filter=False):
    """Scrape economic calendar data from Forex Factory"""
    print(f"Scraping data for {month} {year}")
    
    # Build URL
    if week_filter:
        week_start, week_end = get_current_week_range()
        today = datetime.now()
        
        if today.weekday() >= 5 and week_start.month != today.month:
            url_param = week_start.strftime("%B").lower()
        else:
            url_param = "this"
    else:
        url_param = "this" if month.lower() == datetime.now().strftime("%B").lower() else month.lower()
    
    url = f"{BASE_URL}?month={url_param}"
    print(f"Navigating to: {url}")
    
    driver.get(url)
    
    if not wait_for_page_load(driver):
        raise Exception("Failed to load calendar page")
    
    # Scroll to load all content
    scroll_to_end(driver)
    
    data = []
    current_date = None
    last_time = "empty"

    # Get current week range if filtering is enabled
    if week_filter:
        week_start, week_end = get_current_week_range()
        print(f"Filtering for trading week: {week_start.strftime('%d/%m/%Y')} to {week_end.strftime('%d/%m/%Y')}")

    try:
        table = driver.find_element(By.CLASS_NAME, "calendar__table")
        print("Calendar table found successfully")
        
        for row in table.find_elements(By.TAG_NAME, "tr"):
            # Initialize row data with empty values
            row_data = {
                'date': 'empty',
                'time': 'empty', 
                'currency': 'empty',
                'impact': 'empty',
                'event': 'empty',
                'actual': 'empty',
                'forecast': 'empty',
                'previous': 'empty'
            }
            
            cells = row.find_elements(By.CLASS_NAME, "calendar__cell")

            # Skip rows that are just day separators
            if "calendar__row--day-breaker" in row.get_attribute("class"):
                continue

            has_time = False
            for cell in cells:
                class_name = cell.get_attribute("class").strip()
                key = ALLOWED_ELEMENT_TYPES.get(class_name)

                if key:
                    value = clean_cell_text(cell)

                    if key == "date" and value and value != "empty":
                        try:
                            # Parse the date from the calendar
                            parsed_date = datetime.strptime(value + f" {datetime.now().year}", "%a %b %d %Y")
                            current_date = parsed_date.strftime("%d/%m/%Y")
                            value = current_date
                        except ValueError:
                            current_date = "invalid"
                            value = "invalid"
                    elif key == "time" and value and value != "empty":
                        # Convert GMT to GMT-5 before storing
                        converted_time = convert_gmt_to_gmt_minus_5(value, current_date)
                        last_time = converted_time
                        has_time = True
                        value = converted_time

                    row_data[key] = value

            # If the row has no time cell, use the last one we recorded
            if not has_time:
                row_data["time"] = last_time

            # Attach current date to row
            row_data["date"] = current_date if current_date else "empty"

            # Filter out rows with only the date
            if any(v != "empty" for k, v in row_data.items() if k != "date"):
                # Apply week filter if enabled
                if week_filter and current_date and current_date != "invalid":
                    if is_date_in_current_week(current_date, week_start, week_end):
                        data.append(row_data)
                        print(f"Including data for: {current_date}")
                elif not week_filter:
                    data.append(row_data)

        if week_filter:
            print(f"Found {len(data)} events for the current trading week")
        else:
            print(f"Found {len(data)} events for {month} {year}")

    except Exception as e:
        print(f"Error scraping data: {str(e)}")
        raise

    return data

def save_to_csv(events, filename=None, month=None, year=None):
    """Save events to CSV file"""
    if not events:
        print("No events to save")
        return
    
    if not filename:
        if month and year:
            filename = f"forex_calendar_{month}_{year}.csv"
        else:
            filename = OUTPUT_FILE
    
    print(f"Saving {len(events)} events to {filename}")
    
    # Define field order
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
        week_start, week_end = get_current_week_range()
        target_date = week_start if now.weekday() >= 5 else now.date()
        month = target_date.strftime("%B")
        year = target_date.strftime("%Y")
    else:
        month = arg_month if arg_month else now.strftime("%B")
        year = now.strftime("%Y")
    
    return month, year

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Scrape Forex Factory Economic Calendar')
    parser.add_argument('--month', type=str, help='Target month (e.g. June, July). Defaults to current month.')
    parser.add_argument('--week', action='store_true', help='Only scrape current trading week (Mon-Fri)')
    parser.add_argument('--output', default=None, help='Output CSV filename (auto-generated if not specified)')
    
    args = parser.parse_args()
    
    print("=== Forex Factory Economic Calendar Scraper ===")
    print(f"Environment: {'Streamlit Cloud' if is_streamlit_cloud() else 'Local'}")
    
    # Determine if we're in week mode
    week_mode = args.week
    
    month, year = get_target_month(args.month, week_mode)
    
    if week_mode:
        week_start, week_end = get_current_week_range()
        print(f"Week mode: Targeting trading week {week_start} to {week_end}")
    
    driver = None
    try:
        # Initialize driver
        driver = init_driver()
        
        # Scrape data with retries
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
                    raise
        
        if events:
            # Save to CSV
            save_to_csv(events, args.output, month, year)
            print(f"\n=== Scraping completed successfully ===")
            print(f"Total events: {len(events)}")
            
            # Show sample of events
            if len(events) > 0:
                print("\nSample events:")
                for event in events[:5]:
                    print(f"  {event['date']} {event['time']} {event['currency']} - {event['event']} ({event['impact']})")
                if len(events) > 5:
                    print(f"  ... and {len(events) - 5} more events")
        else:
            print("No events were scraped")
            
    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
        sys.exit(1)
        
    except Exception as e:
        print(f"\nError during scraping: {str(e)}")
        sys.exit(1)
        
    finally:
        if driver:
            try:
                driver.quit()
                print("WebDriver closed successfully")
            except Exception as e:
                print(f"Error closing WebDriver: {str(e)}")

if __name__ == "__main__":
    main()
