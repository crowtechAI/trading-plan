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
        os.path.exists('/usr/bin/chromium') or  # Updated path
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
    options.add_argument('--disable-images')  # Speed up loading
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
    options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Exclude automation switches
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    try:
        if is_streamlit_cloud():
            print("Detected Streamlit Cloud environment")
            # Use system chromium on Streamlit Cloud (Debian paths)
            options.binary_location = '/usr/bin/chromium'
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
        
        # Additional stealth measures
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
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

def wait_for_page_load(driver, timeout=TIMEOUT):
    """Wait for the page to fully load"""
    try:
        # Wait for document ready
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        
        # Additional wait for any dynamic content
        time.sleep(5)  # Increased from 2 to 5 seconds
        
        # Try to wait for some content to appear
        try:
            WebDriverWait(driver, 10).until(
                lambda d: len(d.find_elements(By.TAG_NAME, "table")) > 0 or 
                         len(d.find_elements(By.CSS_SELECTOR, "[class*='calendar']")) > 0
            )
        except TimeoutException:
            print("No tables or calendar elements found, but continuing...")
        
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
    
    # Debug: Save page source for inspection
    try:
        page_source = driver.page_source
        print(f"Page title: {driver.title}")
        print(f"Page source length: {len(page_source)}")
        
        # Check if we're being blocked or redirected
        if "blocked" in page_source.lower() or "cloudflare" in page_source.lower():
            print("WARNING: Page may be blocked by anti-bot protection")
        
        # Try multiple selectors for the calendar table
        calendar_selectors = [
            ".calendar__table",
            ".calendar-table", 
            "table.calendar",
            ".forexfactory-calendar",
            "[class*='calendar']",
            "table[class*='calendar']",
            ".calendar",
            "table"
        ]
        
        calendar_table = None
        for selector in calendar_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"Found {len(elements)} elements with selector: {selector}")
                    calendar_table = elements[0]
                    break
            except Exception as e:
                continue
        
        if not calendar_table:
            # Try waiting longer and check for dynamic loading
            print("No calendar table found with standard selectors, trying alternative approach...")
            
            # Wait for any table to appear
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "table"))
                )
                tables = driver.find_elements(By.TAG_NAME, "table")
                print(f"Found {len(tables)} table(s) on page")
                
                if tables:
                    calendar_table = tables[0]  # Use first table
                    print("Using first table found")
            except TimeoutException:
                print("No tables found on page")
        
        if not calendar_table:
            # Last resort: check page content
            print("DEBUG: First 1000 characters of page source:")
            print(page_source[:1000])
            raise Exception("Calendar table not found - page may have changed structure or be blocked")
        
        print("Calendar table found successfully")
        
    except Exception as e:
        print(f"Error during page inspection: {str(e)}")
        raise
    
    events = []
    current_date = None
    
    try:
        # Try different row selectors
        row_selectors = [
            ".calendar__row",
            ".calendar-row",
            "tr[class*='calendar']",
            "tr",
            ".calendar tr"
        ]
        
        rows = []
        for selector in row_selectors:
            try:
                found_rows = driver.find_elements(By.CSS_SELECTOR, selector)
                if found_rows:
                    rows = found_rows
                    print(f"Found {len(rows)} rows with selector: {selector}")
                    break
            except:
                continue
        
        if not rows:
            # Try to find rows within the table
            rows = calendar_table.find_elements(By.TAG_NAME, "tr")
            print(f"Found {len(rows)} rows using tr tag")
        
        if not rows:
            raise Exception("No calendar rows found")
        
        print(f"Processing {len(rows)} calendar rows")
        
        for i, row in enumerate(rows):
            try:
                # Try multiple approaches to extract data
                row_text = row.text.strip()
                if not row_text:
                    continue
                
                # Look for date patterns in the row
                cells = row.find_elements(By.TAG_NAME, "td")
                if not cells:
                    cells = row.find_elements(By.TAG_NAME, "th")
                
                if len(cells) < 3:  # Need at least time, currency, event
                    continue
                
                # Try to extract data from cells
                cell_texts = [cell.text.strip() for cell in cells]
                
                # Look for date in first few cells
                for j, cell_text in enumerate(cell_texts[:3]):
                    if cell_text and any(day in cell_text for day in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']):
                        try:
                            current_date = datetime.strptime(f"{cell_text} {datetime.now().year}", "%a %b %d %Y").date()
                            print(f"Found date: {current_date}")
                            break
                        except ValueError:
                            continue
                
                # Skip if no current date
                if not current_date:
                    continue
                    
                # Skip if outside date range
                if start_date and current_date < start_date:
                    continue
                if end_date and current_date > end_date:
                    continue
                
                # Extract event data from cells
                if len(cell_texts) >= 4:
                    event_time = ""
                    currency = ""
                    event_name = ""
                    impact = "Low"
                    
                    # Try to identify columns by content patterns
                    for cell_text in cell_texts:
                        # Time pattern
                        if ":" in cell_text and len(cell_text) <= 8:
                            event_time = cell_text
                        # Currency pattern (2-3 letter codes)
                        elif len(cell_text) == 3 and cell_text.isupper():
                            currency = cell_text
                        # Event name (longer text)
                        elif len(cell_text) > 10 and not ":" in cell_text:
                            event_name = cell_text
                    
                    # Check for impact indicators in row classes or attributes
                    row_classes = row.get_attribute("class") or ""
                    if "high" in row_classes.lower() or "red" in row_classes.lower():
                        impact = "High"
                    elif "medium" in row_classes.lower() or "orange" in row_classes.lower():
                        impact = "Medium"
                    
                    # Only include events with meaningful data
                    if event_name and currency and len(currency) <= 3:
                        event_data = {
                            'date': current_date.strftime('%d/%m/%Y'),
                            'time': event_time,
                            'currency': currency,
                            'event': event_name,
                            'impact': impact
                        }
                        events.append(event_data)
                        
                        if len(events) <= 5:  # Show first few events for debugging
                            print(f"Event {len(events)}: {event_data}")
                    
            except Exception as e:
                print(f"Error processing row {i}: {str(e)}")
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
