# --- main_app.py (Corrected Version) ---

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
# IMPORTANT: Replace the placeholder with your actual MongoDB Atlas connection string.
MONGO_CONNECTION_STRING = "mongodb+srv://pcrouthers:CarbonHelix1%21@rendevous.kxkntoa.mongodb.net/?retryWrites=true&w=majority&appName=DailyTradingPlanner"
DB_NAME = "DailyTradingPlanner"
COLLECTION_NAME = "economic_events"  # <-- Here is your collection name

# --- CONSTANTS ---
SCRAPED_DATA_PATH = "latest_forex_data.csv"

# --- CSS STYLE (No Changes) ---
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

# --- STRATEGY RULES (No Changes) ---
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

def update_mongo_with_scraped_data():
    """Reads the scraped CSV and upserts data into the MongoDB collection."""
    collection = get_mongo_collection()
    # --- FIX #1: Corrected the check from 'if not collection' to 'if collection is None' ---
    if collection is None:
        st.warning("MongoDB connection not available. Cannot update data.")
        return 0, 0

    if not os.path.exists(SCRAPED_DATA_PATH):
        st.error(f"Scraper output file not found: '{SCRAPED_DATA_PATH}'. Cannot update database.")
        return 0, 0

    try:
        df = pd.read_csv(SCRAPED_DATA_PATH).fillna('')
        records = df.to_dict('records')
        if not records:
            return 0, 0
        deleted_count = collection.delete_many({}).deleted_count
        result = collection.insert_many(records)
        inserted_count = len(result.inserted_ids)
        return inserted_count, deleted_count
    except Exception as e:
        st.error(f"An error occurred while updating MongoDB: {e}")
        return 0, 0

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
    """
    --- FIX #2: Made this function more robust. ---
    It will now gracefully handle any string that isn't a valid time
    (like 'Day 3', 'Tentative', '11th-15th') by returning None.
    """
    if not isinstance(time_str, str) or not time_str.strip():
        return None
    
    clean_time_str = time_str.strip()
    for fmt in ('%I:%M%p', '%I:%M %p', '%H:%M'):
        try:
            return datetime.strptime(clean_time_str, fmt).time()
        except ValueError:
            continue
    # If all parsing attempts fail, it's not a valid time.
    return None

def parse_date(date_str):
    if not isinstance(date_str, str): return None
    try:
        return datetime.strptime(date_str.strip(), '%d/%m/%Y').date()
    except (ValueError, TypeError):
        return None

def parse_impact(impact_str):
    if not impact_str: return "Low"
    lower = impact_str.lower()
    if 'high' in lower: return "High"
    if 'medium' in lower: return "Medium"
    if 'low' in lower: return "Low"
    return "Low"

# --- ANALYSIS LOGIC (No Changes) ---
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

        if event_time is None: all_day_events.append(event_details)
        elif event_time < MORNING_CUTOFF: morning_events.append(event_details)
        else: afternoon_events.append(event_details)

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

# --- All other analysis and UI display functions remain unchanged ---
# (get_weekly_profile_analysis, display_tgif_alert, display_plan_card, etc.)
def get_weekly_profile_analysis(bias, events, day_of_week):
    profiles = []
    if bias == 'Bullish':
        if 'Mon Low Run' in events and day_of_week in [1, 2]: profiles.append({'name': "Classic Tuesday/Wednesday Low of the Week", 'probability': "High", 'expectation': "The low of the week may now be in. Expect expansion higher towards a premium array.", 'action': "Look for a Market Structure Shift on the 15m chart. Your entry is a long on a retracement into a Fair Value Gap.", 'invalidation': "Price breaks decisively below the new low."})
        if 'Mon High Run' in events and 'Hit Premium Array' in events: profiles.append({'name': "Possible Reversal - Wednesday High of Week", 'probability': "High", 'expectation': "The run on Monday's high was a liquidity raid. The reaction at the premium array suggests the high of the week could be forming.", 'action': "Your bullish bias is now suspect. Look for a bearish Market Structure Shift on the 15m chart for a potential short trade.", 'invalidation': "Price breaks decisively *above* the premium array."})
        if 'Mon High Run' in events and 'Hit Premium Array' not in events: profiles.append({'name': "Consolidation Midweek Rally", 'probability': "High", 'expectation': "The run on Monday's high is a sign of strength. Expect continued expansion higher into Friday.", 'action': "Look for small retracements on lower timeframes to pyramid into your long position. Target the next major premium array.", 'invalidation': "Price sharply rejects and moves back below Monday's high."})
        if 'Consolidating' in events and day_of_week == 3: profiles.append({'name': "Consolidation Thursday Reversal (Bullish)", 'probability': "Medium", 'expectation': "Awaiting a run below the consolidation lows to engineer liquidity, followed by a sharp reversal higher, often on afternoon news.", 'action': "Stay patient. Wait for the stop hunt and reversal. Your entry is after the reversal is confirmed.", 'invalidation': "Price runs the lows and continues to drop without reversing."})
    elif bias == 'Bearish':
        if 'Mon High Run' in events and day_of_week in [1, 2]: profiles.append({'name': "Classic Tuesday/Wednesday High of the Week", 'probability': "High", 'expectation': "The high of the week may now be in. Expect expansion lower towards a discount array.", 'action': "Look for a bearish Market Structure Shift on the 15m chart. Your entry is a short on a retracement into a Fair Value Gap.", 'invalidation': "Price breaks decisively above the new high."})
        if 'Mon Low Run' in events and 'Hit Discount Array' in events: profiles.append({'name': "Possible Reversal - Wednesday Low of Week", 'probability': "High", 'expectation': "The run on Monday's low was a liquidity raid. The reaction at the discount array suggests the low of the week could be forming.", 'action': "Your bearish bias is now suspect. Look for a bullish Market Structure Shift on the 15m chart for a potential long trade.", 'invalidation': "Price breaks decisively *below* the discount array."})
        if 'Mon Low Run' in events and 'Hit Discount Array' not in events: profiles.append({'name': "Consolidation Midweek Decline", 'probability': "High", 'expectation': "The run on Monday's low is a sign of strength to the downside. Expect continued expansion lower into Friday.", 'action': "Look for small retracements to pyramid into your short position. Target the next major discount array.", 'invalidation': "Price sharply rejects and moves back above Monday's low."})
        if 'Consolidating' in events and day_of_week == 3: profiles.append({'name': "Consolidation Thursday Reversal (Bearish)", 'probability': "Medium", 'expectation': "Awaiting a run above the consolidation highs to engineer liquidity, followed by a sharp reversal lower, often on afternoon news.", 'action': "Stay patient. Wait for the stop hunt above the highs and the reversal. Your entry is after the reversal is confirmed with an MSS.", 'invalidation': "Price runs the highs and continues to rally without reversing."})
    if not profiles: profiles.append({'name': "Awaiting Clarity", 'probability': "N/A", 'expectation': "The market has not yet revealed its intention for the week.", 'action': "Remain patient and let Monday's range develop. Do not force a trade.", 'invalidation': "N/A"})
    return profiles

def display_tgif_alert(plan):
    with st.expander("🎯 Potential T.G.I.F. Setup Alert!", expanded=False):
        st.markdown("<div style='padding: 1rem; border-radius: 8px; background-color: rgba(0, 150, 255, 0.1); border-left: 5px solid #00d4ff; color: #e0e0e0;'><p>Today is Friday, which means the <strong>T.G.I.F. Setup</strong> might be in play. This is a model for a retracement back into the weekly range.</p></div>", unsafe_allow_html=True)
        st.markdown("#### ⚠️ Pre-Conditions (MUST be met):")
        st.markdown("**1. Strong Weekly Trend:** Has the week been strongly directional?\n**2. Higher Timeframe Level Hit:** Has price reached a significant **premium array** (bullish week) or **discount array** (bearish week)?")
        st.info("If these conditions are not met, this setup is unlikely. If they are, proceed with the plan below.")
        st.markdown("#### 🔎 Friday Action Plan & Key Times (ET):")
        st.markdown("**Step 1: Mark the Weekly Range**")
        if plan == "Standard Day Plan": st.markdown("**Step 2: Watch for Morning \"Judas Swing\" Peak (9:30 AM - 10:30 AM)**")
        elif plan == "News Day Plan": st.markdown("**Step 2: Watch for Afternoon Peak Formation (1:30 PM - 2:00 PM)**")
        else: st.markdown("**Step 2: Observe Only (No Trading)**")
        st.markdown("**Step 3: Define the Retracement Target** - Use a Fib from weekly low to high. Target the **20%-30% retracement**.")
        st.markdown("**Step 4: Execute the Trade** - Look for a valid ICT entry model (e.g., FVG, Order Block) moving *towards* your target.")

def display_plan_card(plan, reason):
    if plan == "No Trade Day": card_class, icon, title = "no-trade", "🚫", "NO TRADE DAY"
    elif plan == "News Day Plan": card_class, icon, title = "news-day", "📰", "NEWS DAY PLAN"
    else: card_class, icon, title = "standard-day", "✅", "STANDARD DAY PLAN"
    st.markdown(f'<div class="main-plan-card {card_class}"><h1>{icon} {title}</h1><p style="font-size: 1.1rem; margin-top: 1rem;">{reason}</p></div>', unsafe_allow_html=True)

def display_action_checklist(plan):
    with st.expander("📝 Action Checklist", expanded=True):
        if plan == "News Day Plan": checklist = ["🚫 DO NOT trade the morning session", "📊 Mark NY Lunch Range (12:00 - 1:30 PM)", "👀 Wait for liquidity raid after 1:30 PM", "🎯 Prime entry window: 2:00 - 3:00 PM", "✅ Look for displacement/FVG confirmation"]
        elif plan == "Standard Day Plan": checklist = ["📈 Ready for morning open at 9:30 AM", "📊 Mark Previous Day PM Range (1:30 - 4:00 PM)", "🌍 Mark London Session (2:00 - 5:00 AM)", "👀 Wait for Judas Swing at open", "✅ Enter after sweep with displacement/FVG"]
        else: checklist = ["🚫 Stand aside completely", "💰 Preserve capital", "📚 Use time for analysis", "🧘 Practice mindfulness or journaling"]
        for item in checklist: st.markdown(f'<div class="checklist-item">{item}</div>', unsafe_allow_html=True)

def display_perfect_trade_idea(plan):
    st.markdown("## 🎯 Perfect Trade Idea")
    if plan == "Standard Day Plan": idea = "**Time Window:** 10:00 – 11:00 AM ET<br>• Identify a Judas Swing<br>• Wait for liquidity sweep of AM range<br>• Look for displacement + FVG in opposite direction<br>• Ideal target: 1-hour imbalance or PD array"
    elif plan == "News Day Plan": idea = "**Time Window:** 2:00 – 3:00 PM ET<br>• Observe reaction post-news<br>• Wait for stop run into PD arrays<br>• Look for SMT divergence and clean displacement<br>• Ideal setup: News reversal or continuation"
    else: idea = "📴 No trade ideas today. Preserve capital."
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
    with col1: st.markdown(f'<div class="metric-card"><div class="metric-label">Current ET Time</div><div class="metric-value">{current_time.strftime("%I:%M %p")}</div></div>', unsafe_allow_html=True)
    with col2:
        if time_to_open.total_seconds() > 0:
            hours, rem = divmod(int(time_to_open.total_seconds()), 3600); mins, _ = divmod(rem, 60)
            display, label = f"{hours}h {mins}m", "Time to Market Open"
        else:
            display, label = ("OPEN" if time(9, 30) <= current_time.time() < time(16, 0) else "CLOSED"), "Market Status"
        st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{display}</div></div>', unsafe_allow_html=True)
    with col3:
        session = get_current_session(current_time)
        st.markdown(f'<div class="metric-card"><div class="metric-label">Current Session</div><div class="metric-value">{session}</div></div>', unsafe_allow_html=True)

def display_weekly_profile_analysis(analysis):
    st.markdown("### 🧠 ICT Weekly Profile Analysis")
    for profile in analysis:
        prob = profile.get('probability', 'N/A')
        color = "#4caf50" if prob == "High" else ("#ff9800" if prob == "Medium" else "#f44336")
        st.markdown(f"""
        <div style="border: 1px solid {color}; border-left: 5px solid {color}; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; background: rgba(255,255,255,0.03);">
            <h4 style="margin-top: 0; color: {color};">{profile['name']} (Probability: {prob})</h4>
            <ul style="padding-left: 20px; margin-bottom: 0;">
                <li><b>Expectation:</b> {profile['expectation']}</li>
                <li><b>Your Action:</b> {profile['action']}</li>
                <li><b>Invalidation:</b> {profile['invalidation']}</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
# --- MAIN APP (No other changes needed) ---
def main():
    st.title("📈 US Index Trading Plan ($NQ, $ES)")
    display_market_status()
    st.markdown("")
    collection = get_mongo_collection()

    if st.button("🚀 Fetch Live Economic Data & Update DB", type="primary"):
        if collection is None:
            st.error("Cannot fetch data because the database connection is not available.")
            return
        st.info("Note: The scraper `ffscraper.py` must exist in the same directory.")
        try:
            result = subprocess.run([sys.executable, "ffscraper.py"], capture_output=True, check=True, text=True)
            st.success("✅ Scraper script executed successfully.")
            with st.expander("📋 Scraper Log"): st.code(result.stdout)
            inserted, deleted = update_mongo_with_scraped_data()
            st.success(f"✅ Database updated: {deleted} old records removed, {inserted} new records added.")
            st.rerun()
        except FileNotFoundError: st.error("❌ Scraper Error: `ffscraper.py` not found.")
        except subprocess.CalledProcessError as e:
            st.error("❌ Scraper script failed to execute."); st.code(e.stderr)
        except Exception as e: st.error(f"❌ An unexpected error occurred: {e}")

    col1, col2 = st.columns([2, 2]);
    with col1: selected_date = st.date_input("📅 Analysis Date", value=date.today())
    with col2: st.write(""); st.write(""); view_option = st.radio("View", ["Today", "Week"], horizontal=True, label_visibility="collapsed")
    st.markdown("---")

    if selected_date.weekday() >= 5:
        st.markdown('<div class="main-plan-card no-trade"><h1>📴 MARKET CLOSED</h1><p>US indices do not trade on weekends.</p></div>', unsafe_allow_html=True)
        return
    if collection is None:
        st.warning("Awaiting database connection..."); return

    records = list(collection.find({}))
    if not records:
        st.info("👋 The database is empty. Click **Fetch Live Data** to populate it."); return

    def get_events_for(d): return [row for row in records if parse_date(row.get('date', '')) == d]

    if view_option == "Today":
        st.markdown("## Weekly Context & Profile Analysis")
        c1, c2 = st.columns(2)
        with c1: weekly_bias = st.selectbox("Weekly Bias?", ("Bullish 📈", "Bearish 📉", "Neutral/Unclear ⚖️"))
        with c2: key_events = st.multiselect("Key events this week?", ['Mon High Run', 'Mon Low Run', 'Hit Premium Array', 'Hit Discount Array', 'Consolidating'])
        weekly_analysis = get_weekly_profile_analysis(weekly_bias.split(' ')[0], key_events, selected_date.weekday())
        display_weekly_profile_analysis(weekly_analysis)

        st.markdown("---")
        st.markdown("## Daily Plan")
        events_today = get_events_for(selected_date)
        if not events_today: plan, reason, morning, afternoon, allday = "Standard Day Plan", "No economic events found. Proceed with standard technical analysis.", [], [], []
        else: plan, reason, morning, afternoon, allday = analyze_day_events(selected_date, events_today)

        display_plan_card(plan, reason)
        if selected_date.weekday() == 4: display_tgif_alert(plan)
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
        for i in range(5):
            day = start_of_week + timedelta(days=i)
            events_for_day = get_events_for(day)
            with st.container():
                st.markdown(f"### {day.strftime('%A, %b %d')}")
                if not events_for_day: st.markdown("*No significant economic events scheduled.*")
                else:
                    plan, reason, *_ = analyze_day_events(day, events_for_day)
                    plan_class = "standard-day" if "Standard" in plan else ("news-day" if "News" in plan else "no-trade")
                    st.markdown(f"<div class='event-timeline {plan_class}' style='border-left-width: 4px; padding-left: 15px;'><strong>{plan}:</strong> {reason}</div>", unsafe_allow_html=True)
                if i < 4: st.markdown("---")

if __name__ == "__main__":
    main()
