import streamlit as st
import pandas as pd
from datetime import datetime, time, date, timedelta
import pytz
import subprocess
import sys
import pymongo

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Forex Majors Trading Plan",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CONSTANTS ---
SCRAPED_DATA_PATH = "latest_forex_data.csv"
DB_NAME = "DailyTradingPlanner"
COLLECTION_NAME = "economic_events"
LONDON_KILLZONE_START = time(2, 0)
LONDON_KILLZONE_END = time(5, 0)

# --- CSS STYLE ---
st.markdown("""
<style>
    .main-plan-card {
        padding: 1.5rem; border-radius: 12px; text-align: center; margin: 1rem 0;
        border: 3px solid; box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .no-trade { 
        background: rgba(244, 67, 54, 0.15); border-color: #f44336; 
        color: #ff6b6b; box-shadow: 0 0 20px rgba(244, 67, 54, 0.3);
    }
    .clash-day {
        background: rgba(156, 39, 176, 0.15); border-color: #9c27b0;
        color: #ce93d8; box-shadow: 0 0 20px rgba(156, 39, 176, 0.3);
    }
    .news-day { 
        background: rgba(255, 152, 0, 0.15); border-color: #ff9800; 
        color: #ffb74d; box-shadow: 0 0 20px rgba(255, 152, 0, 0.3);
    }
    .standard-day { 
        background: rgba(76, 175, 80, 0.15); border-color: #4caf50; 
        color: #81c784; box-shadow: 0 0 20px rgba(76, 175, 80, 0.3);
    }
    .checklist-item {
        background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 1rem 1.25rem; margin: 0.75rem 0; border-left: 5px solid #00d4ff;
        border-radius: 8px; color: #e0e0e0; backdrop-filter: blur(10px);
    }
    .event-timeline {
        display: flex; align-items: center; padding: 0.6rem; margin: 0.3rem 0;
        border-radius: 6px; background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1); color: #e0e0e0; backdrop-filter: blur(5px);
    }
    .event-high { 
        border-left: 4px solid #ff5252; background: rgba(255, 82, 82, 0.1);
    }
    .event-medium { 
        border-left: 4px solid #ff9800; background: rgba(255, 152, 0, 0.1);
    }
    .event-low { 
        border-left: 4px solid #4caf50; background: rgba(76, 175, 80, 0.1);
    }
    .metric-card {
        background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.15);
        padding: 1rem; border-radius: 10px; text-align: center;
        backdrop-filter: blur(10px); box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .metric-card .metric-label { color: #b0b0b0; font-size: 0.9rem; }
    .metric-card .metric-value { color: #ffffff; font-size: 1.2rem; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- FOREX STRATEGY RULES ---
FORCED_HIGH_IMPACT_KEYWORDS = ['Speaks', 'Chair', 'Governor', 'Non-Farm', 'NFP', 'CPI', 'Interest Rate', 'GDP', 'Retail Sales', 'PPI', 'MPC', 'FOMC']
NO_TRADE_KEYWORDS = ['FOMC Statement', 'Monetary Policy Report']

# --- DATABASE LOGIC ---
@st.cache_resource
def init_connection():
    try:
        connection_string = st.secrets["mongo"]["connection_string"]
        client = pymongo.MongoClient(connection_string)
        return client
    except Exception as e:
        st.error(f"Failed to connect to MongoDB: {e}")
        return None

@st.cache_data(ttl=600)
def get_events_from_db():
    client = init_connection()
    if client is None:
        return pd.DataFrame()
        
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    items = list(collection.find({}, {'_id': 0}))
    
    if not items:
        st.info("Database is empty. Please fetch live data.")
        return pd.DataFrame()
        
    df = pd.DataFrame(items)
    df['parsed_date'] = pd.to_datetime(df['date'], format='%d/%m/%Y', errors='coerce').dt.date
    df['parsed_time'] = df['time'].apply(parse_time)
    
    return df

# --- UTILITIES ---
def get_current_market_time():
    return datetime.now(pytz.timezone('US/Eastern'))

def parse_time(time_str):
    if not time_str or pd.isna(time_str) or str(time_str).lower() in ['all day', '']:
        return None
    for fmt in ('%I:%M%p', '%I:%M %p', '%H:%M'):
        try:
            return datetime.strptime(str(time_str).strip(), fmt).time()
        except ValueError:
            continue
    return None

def parse_impact(impact_str):
    if not impact_str or pd.isna(impact_str):
        return "Low"
    lower = impact_str.lower()
    if 'high' in lower:
        return "High"
    if 'medium' in lower:
        return "Medium"
    return "Low"

# --- FOREX ANALYSIS LOGIC ---
def analyze_day_events_forex(events, ccy1, ccy2):
    has_ccy1_high_impact = False
    has_ccy2_high_impact = False
    is_no_trade_event = False
    reason = f"No high-impact news for {ccy1} or {ccy2}. Proceed with the Standard Day Plan and your DXY-driven bias."

    for event in events:
        event_name = event.get('event', '')
        currency = event.get('currency', '').strip().upper()
        
        if currency not in [ccy1, ccy2]:
            continue

        parsed_impact = parse_impact(event.get('impact', ''))
        is_forced_high = any(keyword.lower() in event_name.lower() for keyword in FORCED_HIGH_IMPACT_KEYWORDS)
        is_high_impact = (parsed_impact == 'High') or is_forced_high

        if any(keyword.lower() in event_name.lower() for keyword in NO_TRADE_KEYWORDS):
            is_no_trade_event = True
            reason = f"Critical event '{event_name}' scheduled. Capital preservation is priority."

        if is_high_impact:
            if currency == ccy1:
                has_ccy1_high_impact = True
            if currency == ccy2:
                has_ccy2_high_impact = True

    if is_no_trade_event:
        return "No Trade Day", reason

    if has_ccy1_high_impact and has_ccy2_high_impact:
        return "Clash of Titans", f"High-impact news for BOTH {ccy1} and {ccy2}. Expect extreme volatility and whipsaws. Stand aside until dust settles."
    
    if has_ccy1_high_impact or has_ccy2_high_impact:
        affected_ccy = ccy1 if has_ccy1_high_impact else ccy2
        return "News Day Plan", f"High-impact news for {affected_ccy} detected. The News Day Plan is active. Be patient for the news-driven liquidity sweep."

    return "Standard Day Plan", reason

# --- UI COMPONENTS ---
def display_plan_card(plan, reason):
    if plan == "No Trade Day": card_class, icon, title = "no-trade", "🚫", "NO TRADE DAY"
    elif plan == "Clash of Titans": card_class, icon, title = "clash-day", "⚔️", "CLASH OF TITANS"
    elif plan == "News Day Plan": card_class, icon, title = "news-day", "📰", "NEWS DAY PLAN"
    else: card_class, icon, title = "standard-day", "✅", "STANDARD DAY PLAN"
    st.markdown(f'<div class="main-plan-card {card_class}"><h1>{icon} {title}</h1><p style="font-size: 1.1rem; margin-top: 1rem;">{reason}</p></div>', unsafe_allow_html=True)

def display_action_checklist_forex(plan, pair):
    st.markdown("### 📝 Action Checklist & Key Levels")
    with st.container():
        st.markdown(f"""
        <div class="checklist-item" style="border-left-color: #fdd835;">
            <strong>Step 1: Confirm Bias (via DXY):</strong> Your Higher Timeframe bias for the Dollar Index (DXY) determines your inverse bias for {pair}. This is the foundation of your narrative.
        </div>
        """, unsafe_allow_html=True)

        if plan == "Standard Day Plan":
            checklist_items = [
                "<strong>Step 2: Mark Target & Context Levels (NY Time):</strong>",
                "&nbsp;&nbsp;&nbsp;&nbsp;• <strong>🎯 Primary Target Liquidity: Asian Range (8:00 PM - 12:00 AM).</strong> This is the range the Judas Swing will attack.",
                "&nbsp;&nbsp;&nbsp;&nbsp;• <strong>Secondary Context Levels:</strong> Previous Day PM Session (1:30 PM - 4:00 PM).",
                "<strong>Step 3: Stalk the Prime Time Window:</strong> Focus exclusively on the <strong>London Killzone (2:00 AM - 5:00 AM)</strong> for the highest probability setup.",
                "<strong>Step 4: Await the Setup Condition (The Sweep):</strong> Patiently wait for the Judas Swing to engineer a clear sweep of the liquidity resting above the <strong>Asian Range High</strong> or below the <strong>Asian Range Low.</strong>",
                "<strong>Step 5: Execute on Confirmation:</strong> After the sweep, enter the trade only after you see a clear <strong>Market Structure Shift (MSS) + Fair Value Gap (FVG).</strong>"
            ]
        elif plan == "News Day Plan" or plan == "Clash of Titans":
            checklist_items = [
                "<strong>Step 2: Mark Target Liquidity (NY Time):</strong>",
                "&nbsp;&nbsp;&nbsp;&nbsp;• <strong>🎯 Primary Target: Pre-News Consolidation.</strong> Mark the high and low of the range formed in the 1-2 hours before the news release.",
                "<strong>Step 3: Stand Aside:</strong> Do NOT trade before or during the news release. Your job is to wait for the volatility to create the setup.",
                "<strong>Step 4: Await the Setup Condition (The Sweep):</strong> Wait for the news-driven spike to violently sweep the liquidity of the pre-news consolidation range.",
                "<strong>Step 5: Execute on Confirmation:</strong> Enter on the reversal away from the sweep, confirmed by a clear <strong>MSS + FVG.</strong>"
            ]
        else: # No Trade Day
            checklist_items = [
                "🚫 **Stand aside completely.**",
                "💰 **Preserve your mental and financial capital.**",
                "📚 **Use the time for focused backtesting and journaling.**",
                "🧘 **Prepare your analysis for the next trading day.**"
            ]
        
        st.markdown(f"""
        <div class="checklist-item">
            {"<br>".join(checklist_items)}
        </div>
        """, unsafe_allow_html=True)

def display_forex_trade_idea(plan):
    st.markdown("## 🎯 The A+ Forex Trade Setup")

    if plan == "Standard Day Plan":
        st.markdown("""
        <div class="checklist-item" style="border-left: 5px solid #4caf50;">
            <h4 style="margin-top:0; color: #81c784;">Profile A: Standard Day Plan (The London Judas Swing)</h4>
            <ol>
                <li><strong>Phase I (Pre-Market):</strong> Confirm DXY Bias. Mark the <strong>Asian Session High/Low</strong> as the target liquidity.</li>
                <li><strong>Phase II (The Tactic):</strong> Focus on the <strong>London Killzone (2 AM - 5 AM ET)</strong>. This is the highest probability window for Forex majors.</li>
                <li><strong>Phase III (The Setup):</strong>
                    <ul>
                        <li>Wait for the **Judas Swing** to engineer a false move and then **sweep the liquidity** on the opposite side of the Asian Range.</li>
                        <li>Confirm with SMT Divergence between EUR/USD and GBP/USD if possible.</li>
                    </ul>
                </li>
                <li><strong>Phase IV (The Entry):</strong>
                    <ul>
                        <li>After the sweep, wait for a lower timeframe (1m/5m) **Market Structure Shift (MSS)** with displacement.</li>
                        <li>Enter on a retracement into the **Fair Value Gap (FVG)** created during the MSS.</li>
                        <li><strong>Stop Loss:</strong> Place just beyond the high/low created by the Judas Swing.</li>
                    </ul>
                </li>
                 <li><strong>Phase V (The Target):</strong> Your primary target is the opposing side of the Asian Range, or the Previous Day's PM High/Low.</li>
            </ol>
        </div>
        """, unsafe_allow_html=True)

    if plan in ["News Day Plan", "Clash of Titans"]:
        st.markdown("""
        <div class="checklist-item" style="border-left: 5px solid #ff9800;">
            <h4 style="margin-top:0; color: #ffb74d;">Profile C: High-Impact News Day Plan</h4>
            <ol>
                <li><strong>Phase I (Pre-News):</strong> Stand aside. Mark the **pre-news consolidation range**.</li>
                <li><strong>Phase II (The Tactic):</strong> Focus exclusively on the **post-news reaction**.</li>
                <li><strong>Phase III (The Setup):</strong>
                    <ul>
                        <li>Wait for the news release to cause a violent spike that **sweeps the liquidity** of the pre-news range.</li>
                    </ul>
                </li>
                <li><strong>Phase IV (The Entry):</strong>
                    <ul>
                        <li>After the sweep, wait for a clear **Market Structure Shift (MSS)** with displacement as price reverses.</li>
                        <li>Enter on a retracement into the **Fair Value Gap (FVG)** created by that reversal.</li>
                        <li><strong>Stop Loss:</strong> Place just beyond the peak of the news-driven volatility spike.</li>
                    </ul>
                </li>
            </ol>
        </div>
        """, unsafe_allow_html=True)
    
    if plan == "No Trade Day":
        st.markdown("""
        <div class="checklist-item" style="border-left: 5px solid #f44336;">
            <h4 style="margin-top:0; color: #ff6b6b;">📴 No Trade Day</h4>
            <p>Today's risk environment is not conducive to high-probability trading. Capital preservation is the priority.</p>
        </div>
        """, unsafe_allow_html=True)

def display_timeline_events(events, title, ccy1, ccy2):
    if not events:
        return
    st.markdown(f"### {title}")
    
    relevant_events = [e for e in events if e.get('currency') in [ccy1, ccy2]]
    
    if not relevant_events:
        st.info(f"No timed events for {ccy1} or {ccy2} today.")
        return

    sorted_events = sorted([e for e in relevant_events if e.get('parsed_time')], key=lambda x: x['parsed_time'])
    
    for event in sorted_events:
        impact_str = event.get('impact', 'Low')
        currency = event.get('currency', 'N/A')
        event_name = event.get('event', 'Unnamed Event')
        parsed_time = event.get('parsed_time')

        impact = parse_impact(impact_str)
        impact_class = "event-high" if "High" == impact else ("event-medium" if "Medium" == impact else "event-low")
        emoji = "🔴" if "High" == impact else ("🟠" if "Medium" == impact else "🟡")
        
        event_time_str = parsed_time.strftime('%I:%M %p') if parsed_time else "All Day"

        st.markdown(f'<div class="event-timeline {impact_class}"><div style="min-width: 80px; font-weight: bold;">{event_time_str}</div><div style="min-width: 30px; text-align: center;">{emoji}</div><div style="min-width: 50px; font-weight: bold;">{currency}</div><div style="flex: 1; margin-left: 10px;">{event_name}</div></div>', unsafe_allow_html=True)

def get_current_session(current_time):
    current = current_time.time()
    if LONDON_KILLZONE_START <= current < LONDON_KILLZONE_END: return "London Killzone"
    elif time(9, 30) <= current < time(12, 0): return "NY Morning"
    elif time(12, 0) <= current < time(13, 30): return "NY Lunch"
    elif time(13, 30) <= current < time(16, 0): return "NY Afternoon"
    else: return "Inter-Session"

def display_market_status():
    current_time = get_current_market_time()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Current NY Time</div><div class="metric-value">{current_time.strftime("%I:%M %p")}</div></div>', unsafe_allow_html=True)
    with col2:
        session = get_current_session(current_time)
        st.markdown(f'<div class="metric-card"><div class="metric-label">Current Session</div><div class="metric-value">{session}</div></div>', unsafe_allow_html=True)

# --- MAIN APP ---
def main():
    st.title("🌍 Forex Majors Trading Plan")
    display_market_status()

    pair_options = {"GBP/USD": ("GBP", "USD"), "EUR/USD": ("EUR", "USD")}
    selected_pair = st.selectbox(
        "Select Forex Pair to Analyze",
        options=list(pair_options.keys())
    )
    CCY1, CCY2 = pair_options[selected_pair]
    
    if st.button("🔄 Fetch & Update Live Economic Data", type="primary"):
        st.info("This would run the scraper and update the database.") # Placeholder for actual scraper logic

    selected_date = st.date_input("📅 Analysis Date", value=date.today())
    st.markdown("---")

    if selected_date.weekday() >= 5:
        st.markdown('<div class="main-plan-card no-trade"><h1>📴 FOREX MARKET CLOSED</h1><p>Major pairs have minimal volume on weekends. Use this time for study and review.</p></div>', unsafe_allow_html=True)
        return

    df = get_events_from_db()
    
    if not df.empty:
        with st.expander("🕵️‍♂️ Database Content & Data Types (Debugger)"):
            st.write("First 5 rows of raw data from database:")
            st.dataframe(df.head())
            st.write("Data types of each column:")
            st.code(str(df.dtypes))

    if df.empty:
        st.warning("👋 No economic data found. Click the **Fetch & Update** button to load data.")
        return

    if 'parsed_date' not in df.columns:
        st.error("Data processing failed. 'parsed_date' column not found.")
        return

    events_today_df = df[df['parsed_date'] == selected_date]
    events_today = events_today_df.to_dict('records')

    if not events_today:
        plan, reason = "Standard Day Plan", f"No economic events found for {CCY1} or {CCY2}. Proceed with Standard Day Plan."
    else:
        plan, reason = analyze_day_events_forex(events_today, CCY1, CCY2)
    
    display_plan_card(plan, reason)
    display_action_checklist_forex(plan, selected_pair)
    display_forex_trade_idea(plan)

    st.markdown("---")
    st.markdown("## 🕒 Today's Event Timeline")
    display_timeline_events(events_today, "All Timed Events", CCY1, CCY2)

if __name__ == "__main__":
    main()
