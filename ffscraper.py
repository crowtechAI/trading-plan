#!/usr/bin/env python3
"""
Forex Factory Economic Calendar Scraper
Scrapes economic events and saves to CSV for trading analysis
"""

import os
import sys
import time
import csv
import argparse
from datetime import datetime, timedelta
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

def is_streamlit_cloud():
    """Detect if running on Streamlit Cloud or similar environment"""
    return (
        os.getenv('STREAMLIT_SHARING_MODE') == 'true' or
        'streamlit' in str(os.getcwd()).lower() or
        os.path.exists('/usr/bin/chromium-browser') or
        'STREAMLIT' in os.environ or
        any('streamlit' in str(arg).lower() for arg in sys.argv) or
        os.path.exists('/mount/src')  # Common Streamlit Cloud path
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
    
    # User agent to avoid detection
    options.add_argument('--user-agent=Mozilla/5.0 (Linux; X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36')
    
    try:
        if is_streamlit_cloud():
            print("Detected Streamlit Cloud environment")
            # Use system chromium on Streamlit Cloud
            options.binary_location = '/usr/bin/chromium-browser'
            service = Service('/usr/bin/chromedriver')
        else:
            print("Detected local environment")
            # Use webdriver-manager for local development
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
            except ImportError:
                print("webdriver-manager not available, using system chromedriver")
                service = Service()  # Use system PATH chromedriver
        
        driver = webdriver.Chrome(service=service, options=options)
        print("WebDriver initialized successfully")
        return driver
        
    except Exception as e:
        print(f"Error initializing WebDriver: {str(e)}")
        # Fallback: try with minimal options
        try:
            print("Attempting fallback initialization...")
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            if is_streamlit_cloud():
                options.binary_location = '/usr/bin/chromium-browser'
                service = Service('/usr/bin/chromedriver')
            else:
                service = Service()
                
            driver = webdriver.Chrome(service=service, options=options)
            print("Fallback WebDriver initialized successfully")
            return driver
            
        except Exception as fallback_error:
            print(f"Fallback also failed: {str(fallback_error)}")
            raise Exception(f"Could not initialize WebDriver. Original error: {str(e)}, Fallback error: {str(fallback_error)}")

def wait_for_page_load(driver, timeout=TIMEOUT):
    """Wait for the page to fully load"""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(2)  # Additional wait for dynamic content
        return True
    except TimeoutException:
        print("Page load timeout")
        return False

def scrape_calendar_data(driver, start_date=None, end_date=None):
    """Scrape economic calendar data from Forex Factory"""
    print(f"Scraping data from {start_date} to {end_date}")
    
    # Navigate to calendar
    url = BASE_URL
    if start_date and end_date:
        url += f"?month={start_date.strftime('%m.%Y')}"
    
    print(f"Navigating to: {url}")
    driver.get(url)
    
    if not wait_for_page_load(driver):
        raise Exception("Failed to load calendar page")
    
    # Wait for calendar table to load
    try:
        calendar_table = WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, "calendar__table"))
        )
        print("Calendar table found")
    except TimeoutException:
        raise Exception("Calendar table not found - page may have changed structure")
    
    events = []
    current_date = None
    
    try:
        # Find all calendar rows
        rows = driver.find_elements(By.CSS_SELECTOR, ".calendar__row")
        print(f"Found {len(rows)} calendar rows")
        
        for row in rows:
            try:
                # Check if this is a date row
                date_cell = row.find_elements(By.CLASS_NAME, "calendar__cell--date")
                if date_cell and date_cell[0].text.strip():
                    date_text = date_cell[0].text.strip()
                    try:
                        # Parse date (format: "Wed Jan 10")
                        current_date = datetime.strptime(f"{date_text} {datetime.now().year}", "%a %b %d %Y").date()
                        print(f"Processing date: {current_date}")
                    except ValueError:
                        continue
                
                # Skip if no current date or outside date range
                if not current_date:
                    continue
                    
                if start_date and current_date < start_date:
                    continue
                    
                if end_date and current_date > end_date:
                    continue
                
                # Extract event data
                time_cell = row.find_elements(By.CLASS_NAME, "calendar__cell--time")
                currency_cell = row.find_elements(By.CLASS_NAME, "calendar__cell--currency")
                impact_cell = row.find_elements(By.CLASS_NAME, "calendar__cell--impact")
                event_cell = row.find_elements(By.CLASS_NAME, "calendar__cell--event")
                
                # Skip if this isn't an event row
                if not (currency_cell and event_cell):
                    continue
                
                # Extract data
                event_time = time_cell[0].text.strip() if time_cell else ""
                currency = currency_cell[0].text.strip() if currency_cell else ""
                event_name = event_cell[0].text.strip() if event_cell else ""
                
                # Extract impact level from icon classes
                impact = "Low"  # default
                if impact_cell:
                    impact_icons = impact_cell[0].find_elements(By.TAG_NAME, "span")
                    for icon in impact_icons:
                        classes = icon.get_attribute("class") or ""
                        if "ff-impact-red" in classes or "high" in classes.lower():
                            impact = "High"
                            break
                        elif "ff-impact-ora" in classes or "medium" in classes.lower():
                            impact = "Medium"
                            break
                
                # Only include events with meaningful data
                if event_name and currency:
                    event_data = {
                        'date': current_date.strftime('%d/%m/%Y'),
                        'time': event_time,
                        'currency': currency,
                        'event': event_name,
                        'impact': impact
                    }
                    events.append(event_data)
                    
            except Exception as e:
                print(f"Error processing row: {str(e)}")
                continue
                
    except Exception as e:
        print(f"Error scraping data: {str(e)}")
        raise
    
    print(f"Successfully scraped {len(events)} events")
    return events

def save_to_csv(events, filename=OUTPUT_FILE):
    """Save events to CSV file"""
    if not events:
        print("No events to save")
        return
    
    print(f"Saving {len(events)} events to {filename}")
    
    fieldnames = ['date', 'time', 'currency', 'event', 'impact']
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(events)
    
    print(f"Data saved successfully to {filename}")

def get_date_range(week_only=False):
    """Get start and end dates for scraping"""
    today = datetime.now().date()
    
    if week_only:
        # Get current trading week (Monday to Friday)
        days_since_monday = today.weekday()
        start_date = today - timedelta(days=days_since_monday)
        end_date = start_date + timedelta(days=4)  # Friday
        print(f"Scraping current trading week: {start_date} to {end_date}")
    else:
        # Get current month
        start_date = today.replace(day=1)
        # Get last day of current month
        if today.month == 12:
            end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        print(f"Scraping current month: {start_date} to {end_date}")
    
    return start_date, end_date

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Scrape Forex Factory Economic Calendar')
    parser.add_argument('--week', action='store_true', help='Scrape current trading week only (default: current month)')
    parser.add_argument('--output', default=OUTPUT_FILE, help=f'Output CSV filename (default: {OUTPUT_FILE})')
    
    args = parser.parse_args()
    
    print("=== Forex Factory Economic Calendar Scraper ===")
    print(f"Environment: {'Streamlit Cloud' if is_streamlit_cloud() else 'Local'}")
    
    driver = None
    try:
        # Initialize driver
        driver = init_driver()
        
        # Get date range
        start_date, end_date = get_date_range(args.week)
        
        # Scrape data with retries
        events = None
        for attempt in range(RETRY_ATTEMPTS):
            try:
                print(f"\nAttempt {attempt + 1}/{RETRY_ATTEMPTS}")
                events = scrape_calendar_data(driver, start_date, end_date)
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
            save_to_csv(events, args.output)
            print(f"\n=== Scraping completed successfully ===")
            print(f"Total events: {len(events)}")
            print(f"Output file: {args.output}")
            
            # Show sample of events
            if len(events) > 0:
                print("\nSample events:")
                for event in events[:5]:  # Show first 5 events
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
