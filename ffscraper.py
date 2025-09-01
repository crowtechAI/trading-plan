#!/usr/bin/env python3
"""
Forex Factory Economic Calendar Scraper
Updated version to handle recent website HTML structure changes.
Uses WebDriverWait for more reliable loading.
"""
import time
import argparse
import pandas as pd
from datetime import datetime, timedelta
import pytz
import csv
import sys
import calendar

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- NEW: Updated class name mapping for the new Forex Factory HTML ---
# The old 'calendar__cell' structure is gone. Now we map direct class names.
ALLOWED_ELEMENT_TYPES = {
    "date": "date",
    "time": "time",
    "currency": "currency",
    "impact": "impact",
    "event": "event",
    "actual": "actual",
    "forecast": "forecast",
    "previous": "previous"
}

# Month name mappings for Forex Factory URLs (unchanged)
MONTH_NAMES = {
    1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr', 5: 'may', 6: 'jun',
    7: 'jul', 8: 'aug', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dec'
}
FULL_MONTH_NAMES = {
    'january': 'jan', 'february': 'feb', 'march': 'mar', 'april': 'apr',
    'may': 'may', 'june': 'jun', 'july': 'jul', 'august': 'aug',
    'september': 'sep', 'october': 'oct', 'november': 'nov', 'december': 'dec'
}

def init_driver() -> webdriver.Chrome:
    """Initialize a lightweight Chrome WebDriver."""
    print("Initializing WebDriver...")
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1920x1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        print("WebDriver initialized successfully.")
        return driver
    except Exception as e:
        print(f"Fatal error initializing WebDriver: {str(e)}")
        print("Please ensure 'webdriver-manager' is in your requirements.txt file.")
        raise

def convert_gmt_to_gmt_minus_4(time_str, date_str):
    """Convert GMT time to America/New_York time (handles DST automatically)."""
    if not time_str or time_str.lower() == "empty" or not date_str or date_str.lower() == "empty":
        return time_str

    special_times = ["all day", "day 1", "day 2", "tentative", "holiday", "tbd"]
    if any(st in time_str.lower() for st in special_times):
        return time_str.lower()

    try:
        date_obj = datetime.strptime(date_str, "%d/%m/%Y").date()
        time_obj = datetime.strptime(time_str.upper(), "%I:%M%p").time()
        
        gmt_datetime = datetime.combine(date_obj, time_obj)
        gmt_datetime = pytz.UTC.localize(gmt_datetime)
        
        target_tz = pytz.timezone('America/New_York')
        target_datetime = gmt_datetime.astimezone(target_tz)
        
        return target_datetime.strftime("%I:%M%p").lower().lstrip('0')
    except (ValueError, TypeError) as e:
        print(f"Warning: Could not convert time '{time_str}' for date '{date_str}': {e}. Using original.")
        return time_str

def get_current_week_range():
    """Get the Monday-Friday range for the current or upcoming trading week."""
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

def get_week_months(week_start, week_end):
    """Get unique months that the trading week spans."""
    months = {d.month for d in (week_start, week_end)}
    return sorted(list(months))

def is_date_in_current_week(date_str, week_start, week_end):
    """Check if a date string is within the target trading week."""
    try:
        date_obj = datetime.strptime(date_str, "%d/%m/%Y").date()
        return week_start <= date_obj <= week_end
    except (ValueError, TypeError):
        return False

def clean_cell_text(element):
    """Extract clean text from a table cell."""
    try:
        # Impact is now in a span with a title
        if "impact" in element.get_attribute("class"):
            impact_span = element.find_element(By.TAG_NAME, "span")
            if impact_span:
                return impact_span.get_attribute("title").replace(" Impact Expected", "")
        
        text = element.get_attribute("innerText")
        return text.strip() if text else "empty"
    except Exception:
        return "empty"

def parse_table(driver, week_filter=False):
    """Parse the main calendar table for economic events using the new HTML structure."""
    try:
        # --- CHANGED: Wait for the new table class name to be present ---
        wait = WebDriverWait(driver, 20)
        table = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "calendar--table")))
    except TimeoutException:
        print("CRITICAL ERROR: Timed out waiting for '.calendar--table' element.")
        print("This suggests the page was blocked or did not load correctly.")
        with open("debug_page_source.html", "w", encoding='utf-8') as f:
            f.write(driver.page_source)
        driver.save_screenshot("debug_screenshot.png")
        print("Saved 'debug_page_source.html' and 'debug_screenshot.png'. Check for a CAPTCHA.")
        return []

    data = []
    current_date = None
    last_time = "empty"

    week_start, week_end = (None, None)
    if week_filter:
        week_start, week_end = get_current_week_range()
        print(f"Filtering for trading week: {week_start.strftime('%d/%m/%Y')} to {week_end.strftime('%d/%m/%Y')}")

    # --- CHANGED: Iterate over `tr` elements with the correct class ---
    for row in table.find_elements(By.XPATH, ".//tr[contains(@class, 'calendar__row')]"):
        # Skip the header rows
        if "calendar__row--header" in row.get_attribute("class"):
            continue

        row_data = {v: "empty" for v in ALLOWED_ELEMENT_TYPES.values()}
        
        # --- CHANGED: Iterate over `td` cells instead of generic 'calendar__cell' ---
        cells = row.find_elements(By.TAG_NAME, "td")
        
        # Extract date from the special date row
        if "divider" in row.get_attribute("class"):
            try:
                date_text = cells[0].text.strip()
                current_year = datetime.now().year
                parsed_date = datetime.strptime(date_text + f" {current_year}", "%A, %B %d %Y")
                current_date = parsed_date.strftime("%d/%m/%Y")
            except (ValueError, IndexError):
                pass
            continue # Move to the next row after processing date

        # Process a regular event row
        row_data["date"] = current_date if current_date else "empty"
        
        for cell in cells:
            class_name = cell.get_attribute("class").split(' ')[-1] # Get the most specific class
            key = ALLOWED_ELEMENT_TYPES.get(class_name)
            
            if key:
                value = clean_cell_text(cell)
                row_data[key] = value

        # Carry over time if the time cell is empty
        if row_data.get("time") == "empty":
             row_data["time"] = last_time
        else:
            last_time = row_data["time"]

        # Convert GMT time from FF to ET
        row_data["time"] = convert_gmt_to_gmt_minus_4(row_data["time"], row_data["date"])

        # Add row if it contains any event data
        if row_data.get("event") and row_data.get("event") != "empty":
            if not week_filter or (current_date and is_date_in_current_week(current_date, week_start, week_end)):
                data.append(row_data)

    print(f"Found {len(data)} events matching the criteria.")
    return data

def save_to_csv(events, filename):
    """Save events to a CSV file."""
    if not events:
        print("No events to save.")
        return
    
    print(f"Saving {len(events)} events to {filename}")
    fieldnames = ['date', 'time', 'currency', 'impact', 'event', 'actual', 'forecast', 'previous']
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(events)
    print(f"Data saved successfully to {filename}")

def scrape_multiple_months(months_to_scrape, week_filter=False, output_file="latest_forex_data.csv"):
    """Scrape data from multiple months and combine results."""
    all_events = []
    driver = None
    
    try:
        driver = init_driver()
        
        for month_param in months_to_scrape:
            url = f"https://www.forexfactory.com/calendar?month={month_param}"
            print(f"Scraping URL: {url}")
            
            driver.get(url)
            events = parse_table(driver, week_filter=week_filter)
            all_events.extend(events)
            time.sleep(2) # Small delay between requests
        
        if all_events:
            unique_events = list({tuple(d.items()): d for d in all_events}.values())
            print(f"Total unique events after deduplication: {len(unique_events)}")
            save_to_csv(unique_events, output_file)
            return unique_events
        else:
            print("No events found across all months.")
            return []
            
    except Exception as e:
        print(f"An error occurred during multi-month scraping: {e}")
        raise
    finally:
        if driver:
            driver.quit()
            print("WebDriver closed successfully.")

def determine_months_to_scrape(args):
    """Determine which months need to be scraped based on arguments."""
    if args.month:
        month_name = args.month.lower()
        return [FULL_MONTH_NAMES.get(month_name, month_name)]
    
    if args.week:
        week_start, week_end = get_current_week_range()
        months_needed = get_week_months(week_start, week_end)
        
        month_params = []
        for month_num in months_needed:
            month_params.append("this" if month_num == datetime.now().month else MONTH_NAMES[month_num])
        print(f"Week spans months: {months_needed}, using parameters: {month_params}")
        return list(set(month_params)) # Use set to avoid duplicates like ['this', 'this']
    
    # Default: scrape current month and next month if we are in the last week
    today = datetime.now()
    _, days_in_month = calendar.monthrange(today.year, today.month)
    months_to_scrape = ["this"]
    if (days_in_month - today.day) <= 7:
        next_month_num = (today.month % 12) + 1
        months_to_scrape.append(MONTH_NAMES[next_month_num])
        print(f"Near end of month, will also scrape next month: {MONTH_NAMES[next_month_num]}")
    return months_to_scrape

def main():
    parser = argparse.ArgumentParser(description="Scrape Forex Factory calendar.")
    parser.add_argument("--month", type=str, help="Target month (e.g. june, july).")
    parser.add_argument("--week", action="store_true", help="Only scrape current trading week (Mon-Fri).")
    parser.add_argument("--output", default="latest_forex_data.csv", help="Output CSV filename.")
    args = parser.parse_args()

    try:
        months_to_scrape = determine_months_to_scrape(args)
        print(f"Will scrape month parameter(s): {months_to_scrape}")
        
        events = scrape_multiple_months(
            months_to_scrape, 
            week_filter=args.week, 
            output_file=args.output
        )
        
        if events:
            print("\n=== Scraping completed successfully ===")
        else:
            print("\n--- No events were scraped. Please check for errors above. ---")

    except KeyboardInterrupt:
        print("\nScraping interrupted by user.")
    except Exception as e:
        print(f"\nAn unrecoverable error occurred: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
