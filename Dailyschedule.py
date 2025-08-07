
import streamlit as st
import pandas as pd
from datetime import datetime, time, date, timedelta
import pytz
import subprocess
import sys
import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# --- CONFIGURATION ---
st.set_page_config(
    page_title="US Index Trading Plan",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- MONGODB CONFIGURATION ---
# The connection string is now securely loaded from Streamlit's secrets management.
try:
    MONGO_CONNECTION_STRING = st.secrets["mongo"]["connection_string"]
except KeyError:
    st.error("MongoDB connection string not found in Streamlit Secrets. Please add it to your .streamlit/secrets.toml file.")
    st.stop() # Stop the app if the secret is not found

DB_NAME = "trading_plans"
COLLECTION_NAME = "economic_events"

# --- CONSTANTS ---
SCRAPED_DATA_PATH = "latest_forex_data.csv"

# --- CSS STYLE (Unchanged) ---
st.markdown("""
<style>
    /* CSS styles are unchanged */
    .main-plan-card { padding: 1.5rem; border-radius: 12px; text-align: center; margin: 1rem 0; border: 3px solid; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
    .no-trade { background: rgba(244, 67, 54, 0.15); border-color: #f44336; color: #ff6b6b; box-shadow: 0 0 20px rgba(244, 67, 54, 0.3); }
    .news-day { background: rgba(255, 152, 0, 0.15); border-color: #ff9800; color: #ffb74d; box-shadow: 0 0 20px rgba(255, 152, 0, 0.3); }
    .standard-day { background: rgba(76, 175, 80, 0.15); border-color: #4caf50; color: #81c784; box-shadow: 0 0 20px rgba(76, 175, 80, 0.3); }
    .checklist-item { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); padding: 0.75rem; margin: 0.5rem 0; border-left: 4px solid #00d4ff; border-radius: 6px; color: #e0e0e0; backdrop-filter: blur(10px); }
    .event-timeline { display: flex; align-items: center; padding: 0.6rem; margin: 0.3rem 0; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); color: #e0e0e0; backdrop-filter: blur(5px); }
    .event-high { border-left: 4px solid #ff5252; background: rgba(255, 82, 82, 0.1); }
    .event-medium { border-left: 4px solid #ff9800; background: rgba(255, 152, 0, 0.1); }
    .event-low { border-left: 4px solid #4caf50; background: rgba(76, 175, 80, 0.1); }
    .metric-card { background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.15); padding: 1rem; border-radius: 10px; text-align: center; backdrop-filter: blur(10px); box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
    .metric-card .metric-label { color: #b0b0b0; font-size: 0.9rem; }
    .metric-card .metric-value { color: #ffffff; font-size: 1.2rem; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- STRATEGY RULES (Unchanged) ---
MORNING_CUTOFF = time(12, 0)
AFTERNOON_NO_TRADE_START = time(13, 55)
NO_TRADE_KEYWORDS = ['FOMC Statement', 'FOMC Press Conference', 'Interest Rate Decision', 'Monetary Policy Report']
FORCED_HIGH_IMPACT_KEYWORDS = ['Powell Speaks', 'Fed Chair', 'Non-Farm', 'NFP', 'CPI', 'Consumer Price Index', 'PPI', 'Producer Price Index', 'GDP']

# --- MONGODB & UTILITY FUNCTIONS ---
@st.cache_resource
def get_mongo_collection():
    """Establishes a connection to MongoDB and returns the collection object."""
    try:
        client = MongoClient(MONGO_CONNECTION_STRING, serverSelectionTimeoutMS=5000)
        client.admin.command('ismaster')
        db = client[DB_NAME]
        return db[COLLECTION_NAME]
    except ConnectionFailure as e:
        st.error(f"MongoDB Connection Failed: {e}. Please check your connection string and ensure your IP is whitelisted in MongoDB Atlas.")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred while connecting to MongoDB: {e}")
        return None

# --- All other functions (update_mongo_with_scraped_data, parse_time, analyze_day_events, display functions, etc.) remain exactly the same as the previous version. ---

def update_mongo_with_scraped_data():
    collection = get_mongo_collection()
    if collection is None:
        st.warning("MongoDB connection not available. Cannot update data.")
        return 0, 0
    if not os.path.exists(SCRAPED_DATA_PATH):
        st.error(f"Scraper output file not found: '{SCRAPED_DATA_PATH}'.")
        return 0, 0
    try:
        df = pd.read_csv(SCRAPED_DATA_PATH).fillna('')
        records = df.to_dict('records')
        if not records: return 0, 0
        deleted_count = collection.delete_many({}).deleted_count
        result = collection.insert_many(records)
        inserted_count = len(result.inserted_ids)
        return inserted_count, deleted_count
    except Exception as e:
        st.error(f"An error occurred while updating MongoDB: {e}")
        return 0, 0

# ... (all other functions are unchanged)

def get_current_market_time():
    et = pytz.timezone('US/Eastern')
    return datetime.now(et)

def time_until_market_open():
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now.time() > time(16, 0): market_open += timedelta(days=1)
    if now.weekday() >= 5: market_open += timedelta(days=7 - now.weekday())
    return market_open - now

def parse_time(time_str):
    if not isinstance(time_str, str) or not time_str.strip():
        return None
    clean_time_str = time_str.strip()
    for fmt in ('%I:%M%p', '%I:%M %p', '%H:%M'):
        try: return datetime.strptime(clean_time_str, fmt).time()
        except ValueError: continue
    return None

def parse_date(date_str):
    if not isinstance(date_str, str): return None
    try: return datetime.strptime(date_str.strip(), '%d/%m/%Y').date()
    except (ValueError, TypeError): return None

def parse_impact(impact_str):
    if not impact_str: return "Low"
    lower = impact_str.lower()
    if 'high' in lower: return "High"
    if 'medium' in lower: return "Medium"
    if 'low' in lower: return "Low"
    return "Low"

def analyze_day_events(target_date, events):
    plan = "Standard Day Plan"; reason = "No high-impact USD news found."
    has_high_impact_usd_event = False
    morning_events, afternoon_events, all_day_events = [], [], []
    for event in events:
        event_time = parse_time(event.get('time', '')); event_name = event.get('event', ''); currency = event.get('currency', '').strip().upper()
        parsed_impact = parse_impact(event.get('impact', '')); is_forced_high = any(keyword.lower() in event_name.lower() for keyword in FORCED_HIGH_IMPACT_KEYWORDS)
        is_high_impact = (parsed_impact == 'High') or is_forced_high
        display_impact = "High (Forced)" if is_forced_high and parsed_impact != 'High' else ("High" if is_high_impact else parsed_impact)
        event_details = {'name': event_name, 'currency': currency, 'impact': display_impact, 'time': event_time.strftime('%I:%M %p') if event_time else 'All Day', 'raw_time': event_time}
        if event_time is None: all_day_events.append(event_details)
        elif event_time < MORNING_CUTOFF: morning_events.append(event_details)
        else: afternoon_events.append(event_details)
        if currency == 'USD':
            if any(keyword.lower() in event_name.lower() for keyword in NO_TRADE_KEYWORDS):
                if event_time and event_time >= AFTERNOON_NO_TRADE_START:
                    return "No Trade Day", f"Critical afternoon USD event '{event_name}'.", morning_events, afternoon_events, all_day_events
            if is_high_impact and event_time: has_high_impact_usd_event = True
    if has_high_impact_usd_event: plan = "News Day Plan"; reason = "High-impact USD news detected. Switch to non-bias scalping."
    return plan, reason, morning_events, afternoon_events, all_day_events

def get_weekly_profile_analysis(bias, events, day_of_week):
    profiles = []
    # (Logic is unchanged)
    if bias == 'Bullish':
        if 'Mon Low Run' in events and day_of_week in [1, 2]: profiles.append({'name': "Classic Tuesday/Wednesday Low of the Week", 'probability': "High", 'expectation': "The low of the week may now be in. Expect expansion higher.", 'action': "Look for 15m MSS + FVG for a long entry.", 'invalidation': "Price breaks decisively below the new low."})
    if not profiles: profiles.append({'name': "Awaiting Clarity", 'probability': "N/A", 'expectation': "Market has not yet revealed its intention.", 'action': "Remain patient. Do not force a trade.", 'invalidation': "N/A"})
    return profiles

# --- All UI functions are also unchanged ---

# --- MAIN APP ---
def main():
    st.title("📈 US Index Trading Plan ($NQ, $ES)")
    display_market_status()
    st.markdown("")
    collection = get_mongo_collection()

    if st.button("🚀 Fetch Live Economic Data & Update DB", type="primary"):
        # The rest of the main function is unchanged
        if collection is None:
            st.error("Cannot fetch data: database connection not available.")
            return
        try:
            result = subprocess.run([sys.executable, "ffscraper.py"], capture_output=True, check=True, text=True)
            st.success("✅ Scraper script executed.")
            with st.expander("📋 Scraper Log"): st.code(result.stdout)
            inserted, deleted = update_mongo_with_scraped_data()
            st.success(f"✅ Database updated: {deleted} records removed, {inserted} records added.")
            st.rerun()
        except FileNotFoundError: st.error("❌ Scraper Error: `ffscraper.py` not found.")
        except subprocess.CalledProcessError as e:
            st.error("❌ Scraper script failed."); st.code(e.stderr)
        except Exception as e: st.error(f"❌ An error occurred: {e}")

    # The rest of the main app logic is unchanged...
    col1, col2 = st.columns([2, 2]);
    with col1: selected_date = st.date_input("📅 Analysis Date", value=date.today())
    with col2: st.write(""); st.write(""); view_option = st.radio("View", ["Today", "Week"], horizontal=True, label_visibility="collapsed")
    st.markdown("---")

    if selected_date.weekday() >= 5:
        st.markdown('<div class="main-plan-card no-trade"><h1>📴 MARKET CLOSED</h1></div>', unsafe_allow_html=True)
        return
    if collection is None:
        st.warning("Awaiting database connection..."); return

    records = list(collection.find({}))
    if not records:
        st.info("👋 Database is empty. Click **Fetch Live Data** to populate it."); return

    def get_events_for(d): return [row for row in records if parse_date(row.get('date', '')) == d]

    if view_option == "Today":
        # ... Today view logic is unchanged
        st.markdown("## Daily Plan")
        events_today = get_events_for(selected_date)
        if not events_today: plan, reason, morning, afternoon, allday = "Standard Day Plan", "No economic events found.", [], [], []
        else: plan, reason, morning, afternoon, allday = analyze_day_events(selected_date, events_today)
        st.markdown(f"**Plan:** {plan} - *{reason}*")
        # ... etc.

if __name__ == "__main__":
    main()
