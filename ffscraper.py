import time
import argparse
import pandas as pd
from datetime import datetime, timedelta
import pytz
from config import ALLOWED_ELEMENT_TYPES, ICON_COLOR_MAP
from utils import save_csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def init_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1920x1080")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def convert_gmt_to_gmt_minus_4(time_str, date_str):
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
            # Handle 12-hour format
            time_obj = datetime.strptime(time_str, "%I:%M%p").time()
        else:
            # Handle 24-hour format (if any)
            time_obj = datetime.strptime(time_str, "%H:%M").time()
        
        # Combine date and time
        gmt_datetime = datetime.combine(date_obj, time_obj)
        
        # Set timezone to UTC (same as GMT)
        utc_tz = pytz.UTC
        gmt_datetime = utc_tz.localize(gmt_datetime)
        
        # Convert to GMT-5 Time
        gmt_minus_4_tz = pytz.timezone('Etc/GMT+5')
        gmt_minus_4_datetime = gmt_datetime.astimezone(gmt_minus_4_tz)
        
        # Format back to 12-hour format
        return gmt_minus_4_datetime.strftime("%I:%M%p").lower().lstrip('0')
        
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
        # Parse the date string (assuming DD/MM/YYYY format)
        date_obj = datetime.strptime(date_str, "%d/%m/%Y").date()
        return week_start <= date_obj <= week_end
    except (ValueError, TypeError):
        return False

def scroll_to_end(driver):
    previous_position = None
    while True:
        current_position = driver.execute_script("return window.pageYOffset;")
        driver.execute_script("window.scrollTo(0, window.pageYOffset + 500);")
        time.sleep(1.5)
        if current_position == previous_position:
            break
        previous_position = current_position
        
def clean_cell_text(element):
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

def parse_table(driver, month, year, week_filter=False):
    data = []
    table = driver.find_element(By.CLASS_NAME, "calendar__table")
    current_date = None
    last_time = "empty"  # Variable to store the last valid time

    # Get current week range if filtering is enabled
    if week_filter:
        week_start, week_end = get_current_week_range()
        print(f"Filtering for trading week: {week_start.strftime('%d/%m/%Y')} to {week_end.strftime('%d/%m/%Y')}")

    for row in table.find_elements(By.TAG_NAME, "tr"):
        row_data = {key: "empty" for key in ALLOWED_ELEMENT_TYPES.values()}
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
                    converted_time = convert_gmt_to_gmt_minus_4(value, current_date)
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

    save_csv(data, month, year)
    return data, month

def get_target_month(arg_month=None, week_mode=False):
    now = datetime.now()
    
    if week_mode:
        # For week mode, we might need to look at next month if weekend scraping
        week_start, week_end = get_current_week_range()
        target_date = week_start if now.weekday() >= 5 else now.date()
        month = target_date.strftime("%B")
        year = target_date.strftime("%Y")
    else:
        month = arg_month if arg_month else now.strftime("%B")
        year = now.strftime("%Y")
    
    return month, year

def main():
    parser = argparse.ArgumentParser(description="Scrape Forex Factory calendar.")
    parser.add_argument("--month", type=str, help="Target month (e.g. June, July). Defaults to current month.")
    parser.add_argument("--week", action="store_true", help="Only scrape current trading week (Mon-Fri)")
    args = parser.parse_args()
    
    # Determine if we're in week mode
    week_mode = args.week
    
    month, year = get_target_month(args.month, week_mode)
    
    # Build URL - for week mode, we might need to navigate to the right month
    if week_mode and not args.month:
        week_start, week_end = get_current_week_range()
        today = datetime.now()
        
        # If we're on weekend and the target week is next month
        if today.weekday() >= 5 and week_start.month != today.month:
            url_param = week_start.strftime("%B").lower()
        else:
            url_param = "this"
    else:
        url_param = "this" if not args.month else args.month.lower()
    
    url = f"https://www.forexfactory.com/calendar?month={url_param}"
    
    print(f"Scraping URL: {url}")
    if week_mode:
        week_start, week_end = get_current_week_range()
        print(f"Week mode: Targeting trading week {week_start} to {week_end}")
    
    driver = init_driver()
    try:
        driver.get(url)
        scroll_to_end(driver)
        parse_table(driver, month, year, week_filter=week_mode)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
