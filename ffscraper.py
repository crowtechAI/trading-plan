#!/usr/bin/env python3
"""
Forex Factory Economic Calendar Scraper
Fixed version with improved month navigation for end-of-month scenarios.
"""

import time
import argparse
import pandas as pd
from datetime import datetime, timedelta
import pytz
import csv
import sys
import calendar

# It's crucial that webdriver-manager is listed in your requirements.txt
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException

# Using the consistent mapping from your more detailed script
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

# Month name mappings for Forex Factory URLs
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
    """Initialize a lightweight Chrome WebDriver based on the working local script."""
    print("Initializing WebDriver...")
    options = webdriver.ChromeOptions()
    # Using the same simple and effective options as the working local script
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1920x1080")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )

    try:
        # Using webdriver-manager is more reliable across different environments
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        print("WebDriver initialized successfully.")
        return driver
    except Exception as e:
        print(f"Fatal error initializing WebDriver: {str(e)}")
        print("Please ensure 'webdriver-manager' is in your requirements.txt file.")
        raise

def convert_gmt_to_gmt_minus_4(time_str, date_str):
    """Convert GMT time to GMT-4 (e.g., New York time during DST)."""
    if not time_str or time_str == "empty" or not date_str or date_str == "empty":
        return time_str

    special_times = ["all day", "day 1", "day 2", "tentative", "holiday", "tbd"]
    if time_str.lower() in special_times:
        return time_str

    try:
        date_obj = datetime.strptime(date_str, "%d/%m/%Y").date()
        time_obj = datetime.strptime(time_str, "%I:%M%p").time()
        
        gmt_datetime = datetime.combine(date_obj, time_obj)
        gmt_datetime = pytz.UTC.localize(gmt_datetime)
        
        # Using a named timezone like 'America/New_York' is better practice
        # as it handles Daylight Saving Time automatically. Etc/GMT+4 is a fixed offset.
        target_tz = pytz.timezone('America/New_York') # Equivalent to GMT-5/GMT-4
        target_datetime = gmt_datetime.astimezone(target_tz)
        
        return target_datetime.strftime("%I:%M%p").lower().lstrip('0')
    except (ValueError, TypeError) as e:
        print(f"Error converting time {time_str} for date {date_str}: {e}")
        return time_str

def get_current_week_range():
    """Get the Monday-Friday range for the current or upcoming trading week."""
    today = datetime.now()
    current_weekday = today.weekday()  # Monday is 0, Sunday is 6

    if current_weekday >= 5:  # Saturday (5) or Sunday (6)
        days_until_monday = 7 - current_weekday
        monday = today + timedelta(days=days_until_monday)
    else:
        days_since_monday = current_weekday
        monday = today - timedelta(days=days_since_monday)

    friday = monday + timedelta(days=4)
    return monday.date(), friday.date()

def get_week_months(week_start, week_end):
    """Get unique months that the trading week spans."""
    months = set()
    current_date = week_start
    while current_date <= week_end:
        months.add(current_date.month)
        current_date += timedelta(days=1)
    return sorted(months)

def is_date_in_current_week(date_str, week_start, week_end):
    """Check if a date string is within the target trading week."""
    try:
        date_obj = datetime.strptime(date_str, "%d/%m/%Y").date()
        return week_start <= date_obj <= week_end
    except (ValueError, TypeError):
        return False

def scroll_to_end(driver):
    """Scroll down the page to ensure all dynamic content is loaded."""
    print("Scrolling to load all events...")
    previous_position = None
    time.sleep(2) # Initial wait
    while True:
        current_position = driver.execute_script("return window.pageYOffset;")
        driver.execute_script("window.scrollTo(0, window.pageYOffset + 500);")
        time.sleep(1.5)  # Allow time for content to load
        if current_position == previous_position:
            print("Finished scrolling.")
            break
        previous_position = current_position

def clean_cell_text(element):
    """Extract clean text from a table cell."""
    try:
        if "calendar__impact" in element.get_attribute("class"):
            impact_span = element.find_element(By.TAG_NAME, "span")
            if impact_span:
                return impact_span.get_attribute("title").replace(" Impact Expected", "")
        
        text = element.get_attribute("innerText")
        return text.strip() if text else "empty"
    except Exception:
        return "empty"

def parse_table(driver, week_filter=False):
    """Parse the main calendar table for economic events."""
    try:
        table = driver.find_element(By.CLASS_NAME, "calendar__table")
    except NoSuchElementException:
        print("CRITICAL ERROR: Could not find the '.calendar__table' element.")
        print("This suggests the page was blocked or did not load correctly.")
        print("Saving debug files...")
        with open("debug_page_source.html", "w", encoding='utf-8') as f:
            f.write(driver.page_source)
        driver.save_screenshot("debug_screenshot.png")
        print("Saved 'debug_page_source.html' and 'debug_screenshot.png'. Check for a CAPTCHA or block page.")
        return []

    data = []
    current_date = None
    last_time = "empty"

    week_start, week_end = None, None
    if week_filter:
        week_start, week_end = get_current_week_range()
        print(f"Filtering for trading week: {week_start.strftime('%d/%m/%Y')} to {week_end.strftime('%d/%m/%Y')}")

    for row in table.find_elements(By.TAG_NAME, "tr"):
        if "calendar__row--day-breaker" in row.get_attribute("class"):
            continue

        row_data = {key: "empty" for key in ALLOWED_ELEMENT_TYPES.values()}
        cells = row.find_elements(By.CLASS_NAME, "calendar__cell")
        has_time = False

        for cell in cells:
            class_name = cell.get_attribute("class").strip()
            key = ALLOWED_ELEMENT_TYPES.get(class_name)

            if key:
                value = clean_cell_text(cell)
                if key == "date" and value and value != "empty":
                    try:
                        # Parse the date and handle year wrapping
                        current_year = datetime.now().year
                        parsed_date = datetime.strptime(value + f" {current_year}", "%a %b %d %Y")
                        
                        # Handle year boundary: if parsed date is more than 6 months ago, it's probably next year
                        today = datetime.now()
                        if (today - parsed_date).days > 180:
                            parsed_date = parsed_date.replace(year=current_year + 1)
                        
                        current_date = parsed_date.strftime("%d/%m/%Y")
                        value = current_date
                    except ValueError:
                        current_date = "invalid"
                elif key == "time" and value and value != "empty":
                    converted_time = convert_gmt_to_gmt_minus_4(value, current_date)
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
            scroll_to_end(driver)
            events = parse_table(driver, week_filter=week_filter)
            all_events.extend(events)
            
            # Small delay between requests
            time.sleep(2)
        
        if all_events:
            # Remove duplicates based on all fields
            seen = set()
            unique_events = []
            for event in all_events:
                event_tuple = tuple(event.values())
                if event_tuple not in seen:
                    seen.add(event_tuple)
                    unique_events.append(event)
            
            print(f"Total unique events after deduplication: {len(unique_events)}")
            save_to_csv(unique_events, output_file)
            return unique_events
        else:
            print("No events found across all months.")
            return []
            
    except Exception as e:
        print(f"Error during multi-month scraping: {e}")
        raise
    finally:
        if driver:
            driver.quit()
            print("WebDriver closed successfully.")

def determine_months_to_scrape(args):
    """Determine which months need to be scraped based on arguments."""
    if args.month:
        # User specified a specific month
        month_name = args.month.lower()
        if month_name in FULL_MONTH_NAMES:
            return [FULL_MONTH_NAMES[month_name]]
        else:
            return [month_name]  # Assume it's already in correct format
    
    if args.week:
        # For week filtering, determine which months the trading week spans
        week_start, week_end = get_current_week_range()
        months_needed = get_week_months(week_start, week_end)
        
        # Convert month numbers to Forex Factory format
        month_params = []
        for month_num in months_needed:
            if month_num == datetime.now().month:
                month_params.append("this")
            else:
                month_params.append(MONTH_NAMES[month_num])
        
        print(f"Week spans months: {months_needed}, using parameters: {month_params}")
        return month_params
    
    # Default case: check if we need current and/or next month
    today = datetime.now()
    current_month = today.month
    
    # If we're in the last week of the month, also scrape next month
    days_in_current_month = calendar.monthrange(today.year, current_month)[1]
    days_remaining = days_in_current_month - today.day
    
    months_to_scrape = ["this"]
    
    if days_remaining <= 7:  # Last week of month
        next_month = current_month + 1 if current_month < 12 else 1
        months_to_scrape.append(MONTH_NAMES[next_month])
        print(f"Near end of month, will also scrape next month: {MONTH_NAMES[next_month]}")
    
    return months_to_scrape

def main():
    """Main function to run the scraper."""
    parser = argparse.ArgumentParser(description="Scrape Forex Factory calendar.")
    parser.add_argument("--month", type=str, help="Target month (e.g. June, July). Defaults to current month.")
    parser.add_argument("--week", action="store_true", help="Only scrape current trading week (Mon-Fri).")
    parser.add_argument("--output", default="latest_forex_data.csv", help="Output CSV filename.")
    args = parser.parse_args()

    try:
        months_to_scrape = determine_months_to_scrape(args)
        print(f"Will scrape months: {months_to_scrape}")
        
        events = scrape_multiple_months(
            months_to_scrape, 
            week_filter=args.week, 
            output_file=args.output
        )
        
        if events:
            print("\n=== Scraping completed successfully ===")
        else:
            print("\n--- No events were scraped. ---")

    except KeyboardInterrupt:
        print("\nScraping interrupted by user.")
    except Exception as e:
        print(f"\nAn unrecoverable error occurred: {str(e)}")

if __name__ == "__main__":
    main()
