#!/usr/bin/env python3
"""
Forex Factory Economic Calendar Scraper
Rectified version for Streamlit Cloud, based on the working local script.
This version correctly handles trading weeks that span two different months.
"""

import time
import argparse
import pandas as pd
from datetime import datetime, timedelta
import pytz
import csv
import sys

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
                        parsed_date = datetime.strptime(value + f" {datetime.now().year}", "%a %b %d %Y")
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

    print(f"Found {len(data)} events matching the criteria on this page.")
    return data

def save_to_csv(events, filename):
    """Save events to a CSV file."""
    if not events:
        print("No events to save.")
        return
    
    print(f"Saving {len(events)} total events to {filename}")
    fieldnames = ['date', 'time', 'currency', 'impact', 'event', 'actual', 'forecast', 'previous']
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(events)
    print(f"Data saved successfully to {filename}")

def main():
    """Main function to run the scraper."""
    parser = argparse.ArgumentParser(description="Scrape Forex Factory calendar.")
    parser.add_argument("--month", type=str, help="Target month (e.g. June, July). Defaults to current month.")
    parser.add_argument("--week", action="store_true", help="Only scrape current trading week (Mon-Fri).")
    parser.add_argument("--output", default="latest_forex_data.csv", help="Output CSV filename.")
    args = parser.parse_args()

    # --- REVISED LOGIC TO HANDLE MULTI-MONTH WEEKS ---

    months_to_scrape = []
    
    if args.week:
        # If --week is specified, we determine the exact month(s) to scrape.
        week_start, week_end = get_current_week_range()
        print(f"Targeting trading week: {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}")

        # Add the starting month's parameter (e.g., 'jul')
        months_to_scrape.append(week_start.strftime("%b").lower())
        
        # If the week spans two different months, add the ending month's parameter too.
        if week_start.month != week_end.month:
            print("Week spans two months. Will scrape both calendar pages.")
            months_to_scrape.append(week_end.strftime("%b").lower())

    elif args.month:
        # If a specific month is given, just use that.
        months_to_scrape.append(args.month.lower())
    else:
        # Default behavior: scrape the current month.
        months_to_scrape.append("this")

    print(f"Calendar pages to scrape: {months_to_scrape}")

    all_events = []
    driver = None
    try:
        driver = init_driver()
        
        # Loop through each required month and scrape its page
        for month_param in months_to_scrape:
            url = f"https://www.forexfactory.com/calendar?month={month_param}"
            print(f"\nScraping URL: {url}")
            
            driver.get(url)
            time.sleep(3) # Give page time to load before scrolling
            scroll_to_end(driver)
            
            # The week_filter flag ensures we only keep events from the target week,
            # even when scraping a full month's page.
            events_from_page = parse_table(driver, week_filter=args.week)
            all_events.extend(events_from_page)
        
        if all_events:
            # Remove potential duplicates by converting dicts to tuples for hashing
            unique_events_set = {tuple(d.items()) for d in all_events}
            unique_events = [dict(t) for t in unique_events_set]
            
            # Sort events chronologically, as combining pages can mix them up
            unique_events.sort(key=lambda x: datetime.strptime(x['date'], "%d/%m/%Y"))

            save_to_csv(unique_events, args.output)
            print("\n=== Scraping completed successfully ===")
        else:
            print("\n--- No events were scraped. ---")

    except KeyboardInterrupt:
        print("\nScraping interrupted by user.")
    except Exception as e:
        print(f"\nAn unrecoverable error occurred: {str(e)}")
    finally:
        if driver:
            driver.quit()
            print("WebDriver closed successfully.")

if __name__ == "__main__":
    main()
