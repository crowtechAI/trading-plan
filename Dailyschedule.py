import streamlit as st
import pandas as pd
import csv
from datetime import datetime, time, date, timedelta
import pytz
import subprocess
import sys
import os
import pymongo

# --- CONFIGURATION ---
st.set_page_config(
    page_title="US Index Trading Plan",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CONSTANTS ---
SCRAPED_DATA_PATH = "latest_forex_data.csv"
DB_NAME = "DailyTradingPlanner"
COLLECTION_NAME = "economic_events"


# --- CSS STYLE ---
st.markdown("""
<style>
    .main-plan-card {
        padding: 1.5rem;
        border-radius: 12px;
        text-align: center;
        margin: 1rem 0;
        border: 3px solid;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .no-trade { 
        background: rgba(244, 67, 54, 0.15); 
        border-color: #f44336; 
        color: #ff6b6b;
        box-shadow: 0 0 20px rgba(244, 67, 54, 0.3);
    }
    .news-day { 
        background: rgba(255, 152, 0, 0.15); 
        border-color: #ff9800; 
        color: #ffb74d;
        box-shadow: 0 0 20px rgba(255, 152, 0, 0.3);
    }
    .standard-day { 
        background: rgba(76, 175, 80, 0.15); 
        border-color: #4caf50; 
        color: #81c784;
        box-shadow: 0 0 20px rgba(76, 175, 80, 0.3);
    }
    .checklist-item {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 0.75rem;
        margin: 0.5rem 0;
        border-left: 4px solid #00d4ff;
        border-radius: 6px;
        color: #e0e0e0;
        backdrop-filter: blur(10px);
    }
    .event-timeline {
        display: flex;
        align-items: center;
        padding: 0.6rem;
        margin: 0.3rem 0;
        border-radius: 6px;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: #e0e0e0;
        backdrop-filter: blur(5px);
    }
    .event-high { 
        border-left: 4px solid #ff5252;
        background: rgba(255, 82, 82, 0.1);
    }
    .event-medium { 
        border-left: 4px solid #ff9800;
        background: rgba(255, 152, 0, 0.1);
    }
    .event-low { 
        border-left: 4px solid #4caf50;
        background: rgba(76, 175, 80, 0.1);
    }
    .metric-card {
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.15);
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .metric-card .metric-label { color: #b0b0b0; font-size: 0.9rem; }
    .metric-card .metric-value { color: #ffffff; font-size: 1.2rem; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- STRATEGY RULES ---
MORNING_CUTOFF = time(12, 0)
AFTERNOON_NO_TRADE_START = time(13, 55)
NO_TRADE_KEYWORDS = ['FOMC Statement', 'FOMC Press Conference', 'Interest Rate Decision', 'Monetary Policy Report']
FORCED_HIGH_IMPACT_KEYWORDS = ['Powell Speaks', 'Fed Chair', 'Non-Farm', 'NFP', 'CPI', 'Consumer Price Index', 'PPI', 'Producer Price Index', 'GDP']


# --- DATABASE LOGIC ---

# Initialize connection to MongoDB using Streamlit's secrets
@st.cache_resource
def init_connection():
    try:
        connection_string = st.secrets["mongo"]["connection_string"]
        client = pymongo.MongoClient(connection_string)
        return client
    except (KeyError, pymongo.errors.ConfigurationError) as e:
        st.error(f"Failed to connect to MongoDB. Please check your secrets.toml file. Error: {e}")
        return None

# Fetch all events from the database
@st.cache_data(ttl=600) # Cache data for 10 minutes
def get_events_from_db():
    client = init_connection()
    if client is None:
        return pd.DataFrame() # Return empty dataframe if connection fails
        
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    # Fetch all documents, excluding the default '_id' field
    items = list(collection.find({}, {'_id': 0}))
    
    if not items:
        st.info("Database is currently empty. Please fetch live economic data.")
        return pd.DataFrame()
        
    return pd.DataFrame(items)

# Update the database with data from the CSV file
def update_db_from_csv(file_path):
    client = init_connection()
    if client is None:
        return 0, 0
        
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    try:
        df = pd.read_csv(file_path)
        # Convert DataFrame to a list of dictionaries for MongoDB insertion
        events = df.to_dict('records')
    except FileNotFoundError:
        st.error(f"Scraped data file not found at: {file_path}")
        return 0, 0

    upserted_count = 0
    modified_count = 0
    
    # Iterate over each event and update or insert it
    for event in events:
        # Create a unique filter for each event based on its core properties
        query = {
            'date': event.get('date'),
            'time': event.get('time'),
            'event': event.get('event'),
            'currency': event.get('currency')
        }
        
        # Use update_one with upsert=True to either insert a new document or update an existing one
        result = collection.update_one(query, {"$set": event}, upsert=True)
        
        if result.upserted_id:
            upserted_count += 1
        elif result.modified_count > 0:
            modified_count += 1
            
    return upserted_count, modified_count


# --- UTILITIES ---
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
    if not time_str or pd.isna(time_str) or time_str.lower() in ['empty', '']: return None
    for fmt in ('%I:%M%p', '%I:%M %p', '%H:%M'):
        try: return datetime.strptime(str(time_str).strip(), fmt).time()
        except ValueError: continue
    return None

def parse_date(date_str):
    try: return datetime.strptime(str(date_str).strip(), '%d/%m/%Y').date()
    except (ValueError, TypeError): return None

def parse_impact(impact_str):
    if not impact_str or pd.isna(impact_str): return "Low"
    lower = impact_str.lower()
    if 'high' in lower: return "High"
    if 'medium' in lower: return "Medium"
    if 'low' in lower: return "Low"
    return "Low"

# --- ANALYSIS LOGIC ---
def analyze_day_events(target_date, events):
    plan = "Standard Day Plan"
    reason = "No high-impact USD news found. Proceed with directional bias. - Check Seasonality Alignment"
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
        event_details = {'name': event_name, 'currency': currency, 'impact': display_impact, 'time': event_time.strftime('%I:%M %p') if event_time else 'All Day', 'raw_time': event_time}

        if event_time is None:
            all_day_events.append(event_details)
        elif event_time < MORNING_CUTOFF:
            morning_events.append(event_details)
        else:
            afternoon_events.append(event_details)

        if currency == 'USD':
            if any(keyword.lower() in event_name.lower() for keyword in NO_TRADE_KEYWORDS):
                if event_time and event_time >= AFTERNOON_NO_TRADE_START:
                    return "No Trade Day", f"Critical afternoon USD event '{event_name}' at {event_time.strftime('%I:%M %p')}.", morning_events, afternoon_events, all_day_events
            
            if is_high_impact and event_time:
                has_high_impact_usd_event = True

    if has_high_impact_usd_event:
        plan = "News Day Plan"
        reason = "High-impact USD news detected. Abandon directional bias and switch to a non-bias scalping model."
        
    return plan, reason, morning_events, afternoon_events, all_day_events

# --- UI COMPONENTS ---

def display_tgif_alert(plan):
    with st.expander("🎯 Potential T.G.I.F. (Thank God It's Friday) Setup Alert!", expanded=False):
        st.markdown("""
        <div style="padding: 1rem; border-radius: 8px; background-color: rgba(0, 150, 255, 0.1); border-left: 5px solid #00d4ff; color: #e0e0e0;">
            <p>Today is Friday, which means the <strong>T.G.I.F. Setup</strong> might be in play. This is a model for a retracement back into the weekly range.</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("#### ⚠️ Pre-Conditions (MUST be met):")
        st.markdown("""
        **1. Strong Weekly Trend:** Has the week been strongly directional (e.g., multiple consecutive bullish or bearish days)?
        **2. Higher Timeframe Level Hit:** Has price reached a significant **premium array** (for a bullish week) or **discount array** (for a bearish week) on the weekly/monthly chart?
        """)
        st.info("If these conditions are not met, this setup is unlikely. If they are, proceed with the plan below.")
        st.markdown("#### 🔎 Friday Action Plan & Key Times (ET):")
        st.markdown("**Step 1: Mark the Weekly Range**\nIdentify the absolute lowest low and highest high of the week so far.")
        if plan == "Standard Day Plan":
            st.markdown("""**Step 2: Watch for Morning "Judas Swing" Peak (9:30 AM - 10:30 AM)**\nSince today is a Standard Day, focus on the morning window. Look for a false run higher right after the New York open - this is designed to trap buyers before the price reverses. If a sharp reversal occurs after this peak, that's likely the high of the week.\n\n✅ *This perfectly aligns with your Standard Day Plan timing and entry models.*""")
        elif plan == "News Day Plan":
            st.markdown("""**Step 2: Watch for Afternoon Peak Formation (1:30 PM - 2:00 PM)**\nSince today is a News Day, focus on the afternoon window. If the market continues higher through the morning, the high of the week may form around the lunch session. Watch for signs of exhaustion and reversal here, especially after news releases.\n\n✅ *This perfectly aligns with your News Day Plan timing and entry models.*""")
        else:
            st.markdown("""**Step 2: Observe Only (No Trading)**\nSince today is a No Trade Day, simply observe price action for educational purposes. The high/low of the week could still form, but avoid trading due to the high-risk news environment.""")
        st.markdown("""**Step 3: Define the Retracement Target**\nOnce you are confident the week's high/low is in, use a Fibonacci tool from the weekly low to the weekly high. Your target is the area between the **20% and 30% retracement levels**.\n\n**Step 4: Execute the Trade**\nLook for a valid ICT entry model (e.g., Fair Value Gap after displacement, Order Block, Breaker) that signals a move *towards* your 20%-30% target zone using the same timing windows as your regular day plan.""")

def display_plan_card(plan, reason):
    if plan == "No Trade Day": card_class, icon, title = "no-trade", "🚫", "NO TRADE DAY"
    elif plan == "News Day Plan": card_class, icon, title = "news-day", "📰", "NEWS DAY PLAN"
    else: card_class, icon, title = "standard-day", "✅", "STANDARD DAY PLAN"
    st.markdown(f'<div class="main-plan-card {card_class}"><h1>{icon} {title}</h1><p style="font-size: 1.1rem; margin-top: 1rem;">{reason}</p></div>', unsafe_allow_html=True)

def display_action_checklist(plan):
    with st.expander("📝 Action Checklist", expanded=True):
        if plan == "News Day Plan":
            checklist = ["🚫 DO NOT trade the morning session", "📊 Mark NY Lunch Range (12:00 PM - 1:30 PM)", "👀 Wait for liquidity raid after 1:30 PM", "🎯 Prime entry window: 2:00 PM - 3:00 PM", "✅ Look for displacement/FVG confirmation"]
        elif plan == "Standard Day Plan":
            checklist = ["📈 Ready for morning open at 9:30 AM", "📊 Mark Previous Day PM Range (1:30 PM - 4:00 PM)", "🌍 Mark London Session (2:00 AM - 5:00 AM)", "👀 Wait for Judas Swing at open", "✅ Enter after sweep with displacement/FVG"]
        else:
            checklist = ["🚫 Stand aside completely", "💰 Preserve capital", "📚 Use time for analysis", "🧘 Practice mindfulness or journaling"]
        for item in checklist:
            st.markdown(f'<div class="checklist-item">{item}</div>', unsafe_allow_html=True)

def display_perfect_trade_idea(plan):
    st.markdown("## 🎯 Perfect Trade Idea")
    if plan == "Standard Day Plan":
        idea = """**Time Window:** 10:00 AM – 11:00 AM ET\n• Identify a Judas Swing early in the NY session\n• Wait for liquidity sweep of the AM range high or low\n• Look for displacement + FVG in the opposite direction\n• Ideal target: 1-hour imbalance or PD array (e.g., PDH/PDL/IPDA levels)"""
    elif plan == "News Day Plan":
        idea = """**Time Window:** 2:00 PM – 3:00 PM ET\n• Observe reaction post high-impact news release\n• Wait for stop run/liquidity raid into PD arrays\n• Look for SMT divergence and clean displacement\n• Ideal setup: News reversal or continuation with clean risk parameters"""
    else:
        idea = "📴 No trade ideas today. Preserve capital and prepare for future opportunities."
    st.markdown(f'<div class="checklist-item">{idea}</div>', unsafe_allow_html=True)

def display_timeline_events(events, title):
    if not events: return
    st.markdown(f"### {title}")
    sorted_events = sorted([e for e in events if e['raw_time']], key=lambda x: x['raw_time'])
    sorted_events.extend([e for e in events if not e['raw_time']])
    for event in sorted_events:
        impact_class = "event-high" if "High" in event['impact'] else ("event-medium" if "Medium" in event['impact'] else "event-low")
        emoji = "🔴" if "High" in event['impact'] else ("🟠" if "Medium" in event['impact'] else "🟡")
        currency_display = f"**{event['currency']}**" if event['currency'] == 'USD' else event['currency']
        st.markdown(f'<div class="event-timeline {impact_class}"><div style="min-width: 80px; font-weight: bold;">{event["time"]}</div><div style="min-width: 30px; text-align: center;">{emoji}</div><div style="min-width: 50px; font-weight: bold;">{currency_display}</div><div style="flex: 1; margin-left: 10px;">{event["name"]}</div></div>', unsafe_allow_html=True)

def get_current_session(current_time):
    current = current_time.time()
    if time(2, 0) <= current < time(5, 0): return "London"
    elif time(9, 30) <= current < time(12, 0): return "NY Morning"
    elif time(12, 0) <= current < time(13, 30): return "NY Lunch"
    elif time(13, 30) <= current < time(16, 0): return "NY Afternoon"
    else: return "Pre-Market"

def display_market_status():
    current_time = get_current_market_time()
    time_to_open = time_until_market_open()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Current ET Time</div><div class="metric-value">{current_time.strftime("%I:%M %p")}</div></div>', unsafe_allow_html=True)
    with col2:
        if time_to_open.total_seconds() > 0:
            hours, rem = divmod(int(time_to_open.total_seconds()), 3600)
            mins, _ = divmod(rem, 60)
            display, label = f"{hours}h {mins}m", "Time to Market Open"
        else:
            display, label = ("OPEN" if current_time.time() < time(16, 0) else "CLOSED"), "Market Status"
        st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{display}</div></div>', unsafe_allow_html=True)
    with col3:
        session = get_current_session(current_time)
        st.markdown(f'<div class="metric-card"><div class="metric-label">Current Session</div><div class="metric-value">{session}</div></div>', unsafe_allow_html=True)

# --- MAIN APP ---
def main():
    st.title("📈 US Index Trading Plan ($NQ, $ES)")
    display_market_status()

    st.markdown("")
    if st.button("🔄 Fetch & Update Live Economic Data", type="primary", help="Runs the scraper and updates the database with the latest events."):
        with st.spinner("🚀 Running scraper... please wait."):
            try:
                # Run the external scraper script
                result = subprocess.run([sys.executable, "ffscraper.py"], capture_output=True, check=True, text=True)
                st.success("✅ Scraper completed successfully!")
                with st.expander("📋 Scraper Log"):
                    st.code(result.stdout)

                # Update the database from the newly created CSV file
                with st.spinner("💾 Updating database..."):
                    upserted, modified = update_db_from_csv(SCRAPED_DATA_PATH)
                    st.success(f"Database updated! ✨ {upserted} new events added, {modified} existing events updated.")
                
                # Clear cache and rerun to show new data immediately
                st.cache_data.clear()
                st.rerun()

            except FileNotFoundError:
                 st.error("❌ Scraper script 'ffscraper.py' not found. Make sure it's in the same directory.")
            except subprocess.CalledProcessError as e:
                st.error("❌ Scraper failed to execute.")
                st.code(f"Error: {e.stderr}")
            except Exception as e:
                st.error(f"❌ An unexpected error occurred: {e}")

    col1, col2 = st.columns([2, 2])
    with col1:
        selected_date = st.date_input("📅 Analysis Date", value=date.today())
    with col2:
        st.write("")
        st.write("")
        view_option = st.radio("View Options", ["Today", "Week"], horizontal=True, label_visibility="collapsed")
    
    st.markdown("---")
    
    # Handle weekend display
    if selected_date.weekday() >= 5:
        st.markdown('<div class="main-plan-card no-trade"><h1>📴 MARKET CLOSED</h1><p style="font-size: 1.1rem; margin-top: 1rem;">US indices do not trade on weekends. 📚 Use this time to journal, review trades, or recharge.</p></div>', unsafe_allow_html=True)
        return

    # Load data from MongoDB
    df = get_events_from_db()
    
    if df.empty:
        # This message will show if the DB connection fails or the DB is empty.
        st.warning("👋 No economic data found. Click the **Fetch & Update** button above to load data.")
        return

    records = df.to_dict('records')

    def get_events_for(d): 
        return [row for row in records if parse_date(row.get('date', '')) == d]

    if view_option == "Today":
        events = get_events_for(selected_date)
        if not events:
            st.warning(f"No economic events found in the database for {selected_date.strftime('%A, %B %d, %Y')}.")
            return
            
        plan, reason, morning, afternoon, allday = analyze_day_events(selected_date, events)
        display_plan_card(plan, reason)

        # Display TGIF alert on Fridays
        if selected_date.weekday() == 4:
            display_tgif_alert(plan)

        display_action_checklist(plan)
        display_perfect_trade_idea(plan)
        st.markdown("## 🕒 Today's Event Timeline")
        c1, c2 = st.columns(2)
        with c1: display_timeline_events(morning, "🌅 Morning Events")
        with c2: display_timeline_events(afternoon, "🌇 Afternoon Events")
        if allday: display_timeline_events(allday, "📅 All-Day Events")
    else:
        st.markdown("## 🗓 Weekly Outlook")
        start_of_week = selected_date - timedelta(days=selected_date.weekday())
        for i in range(5): # Iterate Monday to Friday
            d = start_of_week + timedelta(days=i)
            events_for_day = get_events_for(d)
            
            # Use an expander for each day in the weekly view for better organization
            with st.expander(f"**{d.strftime('%A, %b %d')}**", expanded=(d == selected_date)):
                if not events_for_day:
                    st.info("No significant events scheduled.")
                else:
                    plan, reason, *_ = analyze_day_events(d, events_for_day)
                    # Display a more compact card for the weekly view
                    if plan == "No Trade Day": card_class, icon = "no-trade", "🚫"
                    elif plan == "News Day Plan": card_class, icon = "news-day", "📰"
                    else: card_class, icon = "standard-day", "✅"
                    st.markdown(f'<div class="main-plan-card {card_class}" style="margin: 0.5rem 0; padding: 1rem;"><h3 style="margin:0;">{icon} {plan}</h3><p style="margin-bottom:0;">{reason}</p></div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
