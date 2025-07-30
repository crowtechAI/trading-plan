import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
from utils import save_csv  # You’ll still need this
from config import ALLOWED_ELEMENT_TYPES  # Should match the simplified schema

def get_current_week_range():
    today = datetime.utcnow()
    start = today - timedelta(days=today.weekday())  # Monday
    end = start + timedelta(days=4)  # Friday
    return start.date(), end.date()

def convert_time_to_gmt_minus_4(time_str, date_str):
    try:
        naive_time = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %I:%M%p")
        gmt = pytz.utc.localize(naive_time)
        target_tz = pytz.timezone("Etc/GMT+4")
        return gmt.astimezone(target_tz).strftime("%I:%M %p").lower()
    except Exception:
        return time_str

def parse_forex_factory(week_mode=False):
    url = "https://www.forexfactory.com/calendar"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table", {"class": "calendar__table"})
    rows = table.find_all("tr") if table else []

    results = []
    current_date = None
    week_start, week_end = get_current_week_range()

    for row in rows:
        if "calendar__row--day-breaker" in row.get("class", []):
            continue

        cells = row.find_all("td")
        if not cells:
            continue

        data = {key: "empty" for key in ALLOWED_ELEMENT_TYPES.values()}
        for cell in cells:
            class_name = cell.get("class", [""])[0].strip()
            key = ALLOWED_ELEMENT_TYPES.get(class_name)
            if not key:
                continue

            text = cell.get_text(strip=True)
            if key == "date" and text:
                try:
                    dt = datetime.strptime(text + f" {datetime.now().year}", "%a%b%d %Y")
                    current_date = dt.strftime("%d/%m/%Y")
                    data["date"] = current_date
                except:
                    pass
            elif key == "time":
                if current_date:
                    data["time"] = convert_time_to_gmt_minus_4(text, current_date)
            else:
                data[key] = text

        data["date"] = current_date or "empty"

        if week_mode:
            try:
                row_date = datetime.strptime(data["date"], "%d/%m/%Y").date()
                if not (week_start <= row_date <= week_end):
                    continue
            except:
                continue

        if any(val != "empty" for key, val in data.items() if key != "date"):
            results.append(data)

    return results

def run_scraper(week=False):
    events = parse_forex_factory(week_mode=week)
    month = datetime.now().strftime("%B")
    year = datetime.now().year
    save_csv(events, month, year)
    return events
