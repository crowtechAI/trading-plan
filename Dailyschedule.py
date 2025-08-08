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
try:
    MONGO_CONNECTION_STRING = st.secrets["mongo"]["connection_string"]
except KeyError:
    st.error("MongoDB connection string not found in Streamlit Secrets. Please add it to your .streamlit/secrets.toml file.")
    st.stop()

DB_NAME = "DailyTradingPlanner"
COLLECTION_NAME = "economic_events"

# --- CONSTANTS ---
SCRAPED_DATA_PATH = "latest_forex_data.csv"

# --- CSS STYLE ---
st.markdown("""
<style>
    .main-plan-card { padding: 1.5rem; border-radius: 12px; text-align: center; margin: 1rem 0; border: 3px solid; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
    .no-trade { background: rgba(244, 67, 54, 0.15); border-color: #f44336; color: #ff6b6b; box-shadow: 0 0 20px rgba(244, 67, 54, 0.3); }
    .news-day { background: rgba(255, 152, 0, 0.15); border-color: #ff9800; color: #ffb74d; box-shadow: 0 0 20px rgba(255, 152, 0, 0.3); }
    .standard-day { background: rgba(76, 175, 80, 0.15); border-color: #4caf50; color: #81c784; box-shadow: 0 0 20px rgba(76, 175, 80, 0.3); }
    .debug-info { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); padding: 1rem; margin: 1rem 0; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# --- STRATEGY RULES ---
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
        st.error(f"MongoDB Connection Failed: {e}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred while connecting to MongoDB: {e}")
        return None

def debug_database_contents():
    """Debug function to inspect database contents"""
    collection = get_mongo_collection()
    if collection is None:
        return None, "No database connection"
    
    try:
        # Count total documents
        total_count = collection.count_documents({})
        
        # Get a few sample documents
        sample_docs = list(collection.find().limit(5))
        
        # Get unique dates in the collection
        pipeline = [
            {"$group": {"_id": "$date", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        unique_dates = list(collection.aggregate(pipeline))
        
        debug_info = {
            "total_count": total_count,
            "sample_docs": sample_docs,
            "unique_dates": unique_dates
        }
        
        return debug_info, "Success"
        
    except Exception as e:
        return None, f"Error querying database: {e}"

def update_mongo_with_scraped_data():
    collection = get_mongo_collection()
    if collection is None:
        st.warning("MongoDB connection not available. Cannot update data.")
        return 0, 0
    
    if not os.path.exists(SCRAPED_DATA_PATH):
        st.error(f"Scraper output file not found: '{SCRAPED_DATA_PATH}'.")
        return 0, 0
    
    try:
        # Read and preview the CSV data
        df = pd.read_csv(SCRAPED_DATA_PATH).fillna('')
        st.write(f"📊 **CSV Data Preview** ({len(df)} rows):")
        st.dataframe(df.head())
        
        # Show column names and data types
        st.write("**Column Info:**")
        for col in df.columns:
            st.write(f"- {col}: {df[col].dtype} (sample: {df[col].iloc[0] if len(df) > 0 else 'N/A'})")
        
        records = df.to_dict('records')
        if not records: 
            return 0, 0
        
        # Clear existing data and insert new
        deleted_count = collection.delete_many({}).deleted_count
        result = collection.insert_many(records)
        inserted_count = len(result.inserted_ids)
        
        st.success(f"✅ Successfully processed CSV: {len(records)} records")
        return inserted_count, deleted_count
        
    except Exception as e:
        st.error(f"An error occurred while updating MongoDB: {e}")
        import traceback
        st.code(traceback.format_exc())
        return 0, 0

def parse_time(time_str):
    """Enhanced time parsing to handle your data format"""
    if not isinstance(time_str, str) or not time_str.strip():
        return None
    
    clean_time_str = time_str.strip()
    
    # Handle formats like "7:01pm", "12:30am", "15:30", etc.
    time_formats = [
        '%I:%M%p',    # 7:01pm
        '%I:%M %p',   # 7:01 pm
        '%H:%M',      # 15:30
        '%I%p',       # 7pm
        '%I %p'       # 7 pm
    ]
    
    for fmt in time_formats:
        try: 
            parsed_time = datetime.strptime(clean_time_str, fmt).time()
            # Debug: uncomment to see time parsing
            # st.write(f"DEBUG TIME: '{clean_time_str}' parsed with '{fmt}' → {parsed_time}")
            return parsed_time
        except ValueError: 
            continue
    
    # If no format worked
    # st.write(f"DEBUG TIME: Could not parse time '{clean_time_str}'")
    return None

def parse_date(date_str):
    """Parse date string with enhanced debugging"""
    if not isinstance(date_str, str): 
        return None
    
    date_str = date_str.strip()
    
    # If empty string, return None
    if not date_str:
        return None
    
    # Try multiple date formats - DD/MM/YYYY first (your data appears to be in this format)
    date_formats = [
        '%d/%m/%Y',  # 01/07/2025 = July 1st, 2025 (DD/MM/YYYY - likely correct for your data)
        '%m/%d/%Y',  # 01/07/2025 = January 7th, 2025 (MM/DD/YYYY - US format)
        '%Y-%m-%d',  # 2025-07-01
        '%d-%m-%Y',  # 01-07-2025
        '%Y/%m/%d',  # 2025/07/01
        '%d.%m.%Y',  # 01.07.2025
        '%Y%m%d',    # 20250701
        '%d %m %Y',  # 01 07 2025
        '%d/%m/%y',  # 01/07/25
        '%m/%d/%y'   # 01/07/25 (US format)
    ]
    
    for fmt in date_formats:
        try: 
            parsed = datetime.strptime(date_str, fmt).date()
            # Enable this debug line temporarily if you want to see what format is working
            # st.write(f"DEBUG: '{date_str}' parsed with format '{fmt}' → {parsed}")
            return parsed
        except (ValueError, TypeError): 
            continue
    
    # If no format worked, show debug info
    # st.write(f"DEBUG: Could not parse date '{date_str}' with any known format")
    return None

def parse_impact(impact_str):
    if not impact_str: return "Low"
    lower = impact_str.lower()
    if 'high' in lower: return "High"
    if 'medium' in lower: return "Medium"
    if 'low' in lower: return "Low"
    return "Low"

def analyze_day_events(target_date, events):
    plan = "Standard Day Plan"
    reason = "No high-impact USD news found."
    has_high_impact_usd_event = False
    morning_events, afternoon_events, all_day_events = [], [], []
    
    for event in events:
        event_time = parse_time(event.get('time', ''))
        event_name = event.get('event', '')
        currency = event.get('currency', '').strip().upper()
        parsed_impact = parse_impact(event.get('impact', ''))
        is_forced_high = any(keyword.lower() in event_name.lower() for keyword in FORCED_HIGH_IMPACT_KEYWORDS)
        is_high_impact = (parsed_impact == 'High') or is_forced_high
        display_impact = "High (Forced)" if is_forced_high and parsed_impact != 'High' else ("High" if is_high_impact else parsed_impact)
        
        event_details = {
            'name': event_name, 
            'currency': currency, 
            'impact': display_impact, 
            'time': event_time.strftime('%I:%M %p') if event_time else 'All Day', 
            'raw_time': event_time
        }
        
        if event_time is None: 
            all_day_events.append(event_details)
        elif event_time < MORNING_CUTOFF: 
            morning_events.append(event_details)
        else: 
            afternoon_events.append(event_details)
        
        if currency == 'USD':
            if any(keyword.lower() in event_name.lower() for keyword in NO_TRADE_KEYWORDS):
                if event_time and event_time >= AFTERNOON_NO_TRADE_START:
                    return "No Trade Day", f"Critical afternoon USD event '{event_name}'.", morning_events, afternoon_events, all_day_events
            if is_high_impact and event_time: 
                has_high_impact_usd_event = True
    
    if has_high_impact_usd_event: 
        plan = "News Day Plan"
        reason = "High-impact USD news detected. Switch to non-bias scalping."
    
    return plan, reason, morning_events, afternoon_events, all_day_events

def get_current_market_time():
    et = pytz.timezone('US/Eastern')
    return datetime.now(et)

def display_market_status():
    market_time = get_current_market_time()
    is_market_open = (market_time.weekday() < 5 and 
                     time(9, 30) <= market_time.time() <= time(16, 0))
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown('<div class="metric-card"><div class="metric-label">Market Time (ET)</div><div class="metric-value">' + 
                   market_time.strftime('%I:%M %p') + '</div></div>', unsafe_allow_html=True)
    with col2:
        status = "🟢 OPEN" if is_market_open else "🔴 CLOSED"
        st.markdown('<div class="metric-card"><div class="metric-label">Market Status</div><div class="metric-value">' + 
                   status + '</div></div>', unsafe_allow_html=True)
    with col3:
        current_day = market_time.strftime('%A')
        st.markdown('<div class="metric-card"><div class="metric-label">Trading Day</div><div class="metric-value">' + 
                   current_day + '</div></div>', unsafe_allow_html=True)

# --- MAIN APP ---
def main():
    st.title("📈 US Index Trading Plan ($NQ, $ES)")
    display_market_status()
    st.markdown("")
    
    # Add debug section
    st.markdown("## 🔍 Database Debug Info")
    if st.button("🔍 Inspect Database Contents"):
        debug_info, status = debug_database_contents()
        
        if debug_info:
            st.success(f"✅ Database Status: {status}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Records", debug_info["total_count"])
            
            with col2:
                st.metric("Unique Dates", len(debug_info["unique_dates"]))
            
            if debug_info["sample_docs"]:
                st.write("**Sample Documents:**")
                for i, doc in enumerate(debug_info["sample_docs"]):
                    with st.expander(f"Document {i+1}"):
                        st.json(doc)
            
            if debug_info["unique_dates"]:
                st.write("**Dates in Database:**")
                for date_info in debug_info["unique_dates"]:
                    parsed_date = parse_date(date_info["_id"]) if date_info["_id"] else None
                    st.write(f"- {date_info['_id']} → {parsed_date} ({date_info['count']} events)")
        else:
            st.error(f"❌ Database Status: {status}")
    
    st.markdown("---")
    
    collection = get_mongo_collection()

    if st.button("🚀 Fetch Live Economic Data & Update DB", type="primary"):
        if collection is None:
            st.error("Cannot fetch data: database connection not available.")
            return
        try:
            result = subprocess.run([sys.executable, "ffscraper.py"], capture_output=True, check=True, text=True)
            st.success("✅ Scraper script executed.")
            with st.expander("📋 Scraper Log"): 
                st.code(result.stdout)
            inserted, deleted = update_mongo_with_scraped_data()
            st.success(f"✅ Database updated: {deleted} records removed, {inserted} records added.")
            st.rerun()
        except FileNotFoundError: 
            st.error("❌ Scraper Error: `ffscraper.py` not found.")
        except subprocess.CalledProcessError as e:
            st.error("❌ Scraper script failed.")
            st.code(e.stderr)
        except Exception as e: 
            st.error(f"❌ An error occurred: {e}")

    col1, col2 = st.columns([2, 2])
    with col1: 
        selected_date = st.date_input("📅 Analysis Date", value=date.today())
    with col2: 
        st.write("")
        st.write("")
        view_option = st.radio("View", ["Today", "Week"], horizontal=True, label_visibility="collapsed")
    
    st.markdown("---")

    if selected_date.weekday() >= 5:
        st.markdown('<div class="main-plan-card no-trade"><h1>📴 MARKET CLOSED</h1></div>', unsafe_allow_html=True)
        return
    
    if collection is None:
        st.warning("Awaiting database connection...")
        return

    # Get all records with enhanced debugging
    records = list(collection.find({}))
    st.write(f"📊 **Total records found:** {len(records)}")
    
    if not records:
        st.info("👋 Database is empty. Click **Fetch Live Data** to populate it.")
        return

    # Enhanced debug function to show exactly what's happening
    def get_events_for(target_date):
        matching_events = []
        target_date_str = target_date.strftime('%d/%m/%Y')
        
        st.write(f"🎯 **Looking for events on:** {target_date} (formatted as {target_date_str})")
        
        # Debug: Show detailed matching process
        debug_matches = []
        debug_non_matches = []
        
        for i, row in enumerate(records):
            row_date_str = row.get('date', '')
            parsed_date = parse_date(row_date_str)
            
            debug_info = {
                'index': i,
                'raw_date': row_date_str,
                'parsed_date': parsed_date,
                'target_date': target_date,
                'matches': parsed_date == target_date,
                'event_name': row.get('event', 'N/A')[:50],  # Truncate long names
                'currency': row.get('currency', 'N/A'),
                'time': row.get('time', 'N/A')
            }
            
            if parsed_date == target_date:
                matching_events.append(row)
                debug_matches.append(debug_info)
            else:
                debug_non_matches.append(debug_info)
        
        st.write(f"✅ **Found {len(matching_events)} events for {target_date}**")
        
        # Show detailed matching results
        if debug_matches:
            st.write("**✅ MATCHING Events:**")
            for match in debug_matches:
                st.write(f"- Row {match['index']}: '{match['raw_date']}' → {match['parsed_date']} | {match['event_name']} ({match['currency']} at {match['time']})")
        
        # Show some non-matching examples for comparison
        if debug_non_matches and len(debug_non_matches) > 0:
            st.write("**❌ NON-MATCHING Examples (first 5):**")
            for non_match in debug_non_matches[:5]:
                st.write(f"- Row {non_match['index']}: '{non_match['raw_date']}' → {non_match['parsed_date']} | {non_match['event_name']}")
        
        # Show all unique dates in the database
        all_dates = set()
        for row in records:
            date_str = row.get('date', '')
            parsed = parse_date(date_str)
            if parsed:
                all_dates.add(parsed)
        
        st.write(f"**📅 All unique dates in database ({len(all_dates)} total):**")
        sorted_dates = sorted(all_dates)
        for date_obj in sorted_dates[:10]:  # Show first 10 dates
            is_target = "← TARGET" if date_obj == target_date else ""
            st.write(f"- {date_obj} {is_target}")
        
        if len(sorted_dates) > 10:
            st.write(f"... and {len(sorted_dates) - 10} more dates")
        
        return matching_events

    if view_option == "Today":
        st.markdown("## Daily Plan")
        events_today = get_events_for(selected_date)
        
        if not events_today: 
            plan, reason, morning, afternoon, allday = "Standard Day Plan", "No economic events found.", [], [], []
            st.warning(f"⚠️ No events found for {selected_date}. This might be due to:")
            st.write("1. **Date format mismatch** - Check if CSV dates match expected format")
            st.write("2. **No data for this date** - The date might not exist in your dataset")
            st.write("3. **Database sync issues** - Try fetching fresh data")
        else: 
            st.success(f"✅ Found {len(events_today)} events for analysis")
            plan, reason, morning, afternoon, allday = analyze_day_events(selected_date, events_today)
            
            # Show the raw events we found
            with st.expander(f"📋 Raw Events Data ({len(events_today)} events)"):
                for i, event in enumerate(events_today):
                    st.write(f"**Event {i+1}:**")
                    st.json(event)
            
            # Show the processed events
            st.write("**📊 Processed Events for Analysis:**")
            all_processed = morning + afternoon + allday
            if all_processed:
                for event in all_processed:
                    st.write(f"- **{event['time']}** {event['name']} ({event['currency']}) - Impact: {event['impact']}")
            else:
                st.write("No events after processing (this might indicate parsing issues)")
        
        st.markdown(f"**Plan:** {plan}")
        st.markdown(f"**Reason:** {reason}")
        
        # Show detailed analysis results
        st.write("**📈 Analysis Results:**")
        st.write(f"- Morning Events ({len(morning)}): {[e['name'] for e in morning]}")
        st.write(f"- Afternoon Events ({len(afternoon)}): {[e['name'] for e in afternoon]}")
        st.write(f"- All Day Events ({len(allday)}): {[e['name'] for e in allday]}")
        
        # Display plan card
        if "No Trade" in plan:
            card_class = "no-trade"
        elif "News Day" in plan:
            card_class = "news-day"
        else:
            card_class = "standard-day"
            
        st.markdown(f'<div class="main-plan-card {card_class}"><h2>{plan}</h2><p>{reason}</p></div>', 
                   unsafe_allow_html=True)

if __name__ == "__main__":
    main()
