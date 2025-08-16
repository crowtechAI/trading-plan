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

# --- MORNING_CUTOFF and other constants ---
MORNING_CUTOFF = time(12, 0)
AFTERNOON_NO_TRADE_START = time(13, 55)
NO_TRADE_KEYWORDS = ['FOMC Statement', 'FOMC Press Conference', 'Interest Rate Decision', 'Monetary Policy Report']
FORCED_HIGH_IMPACT_KEYWORDS = ['Powell Speaks', 'Fed Chair', 'Non-Farm', 'NFP', 'CPI', 'Consumer Price Index', 'PPI', 'Producer Price Index', 'GDP']
WIN_STREAK_THRESHOLD = 5

# --- ENHANCED CSS STYLES ---
st.markdown("""
<style>
    /* Base styling */
    .stApp { background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%); }
    
    /* Quick scan dashboard layout */
    .trading-dashboard {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 20px;
        margin-bottom: 30px;
    }
    
    /* Main trading plan - large, prominent */
    .main-plan-card {
        grid-column: span 2;
        padding: 2rem;
        border-radius: 16px;
        text-align: center;
        margin: 1rem 0;
        border: 4px solid;
        box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        backdrop-filter: blur(20px);
        position: relative;
        overflow: hidden;
    }
    
    .main-plan-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
        transition: left 0.5s;
    }
    
    .main-plan-card:hover::before {
        left: 100%;
    }
    
    .no-trade { 
        background: linear-gradient(135deg, rgba(244, 67, 54, 0.2), rgba(183, 28, 28, 0.1)); 
        border-color: #f44336; 
        color: #ffcdd2;
    }
    .news-day { 
        background: linear-gradient(135deg, rgba(255, 152, 0, 0.2), rgba(239, 108, 0, 0.1)); 
        border-color: #ff9800; 
        color: #ffcc02;
    }
    .standard-day { 
        background: linear-gradient(135deg, rgba(76, 175, 80, 0.2), rgba(56, 142, 60, 0.1)); 
        border-color: #4caf50; 
        color: #a5d6a7;
    }
    
    /* Quick info cards */
    .quick-info-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 15px;
        margin: 20px 0;
    }
    
    .info-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    
    .info-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.3);
        border-color: rgba(255, 255, 255, 0.2);
    }
    
    .info-card .metric-label { 
        color: #94a3b8; 
        font-size: 0.85rem; 
        font-weight: 500;
        margin-bottom: 8px;
    }
    .info-card .metric-value { 
        color: #ffffff; 
        font-size: 1.4rem; 
        font-weight: 700;
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }
    
    /* Risk management - prominently displayed */
    .risk-section {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.6));
        border: 2px solid rgba(59, 130, 246, 0.3);
        border-radius: 16px;
        padding: 1.5rem;
        margin: 20px 0;
        box-shadow: 0 8px 32px rgba(59, 130, 246, 0.1);
    }
    
    .risk-output {
        padding: 1.2rem;
        border-radius: 12px;
        text-align: center;
        color: white;
        font-weight: bold;
        font-size: 1.3rem;
        margin: 15px 0;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        transition: all 0.3s ease;
    }
    
    .risk-output:hover {
        transform: scale(1.02);
    }
    
    .risk-normal { background: linear-gradient(135deg, #3182CE, #2c5aa0); }
    .risk-defensive { background: linear-gradient(135deg, #DD6B20, #c05621); }
    .risk-minimum { background: linear-gradient(135deg, #E53E3E, #c53030); }
    .risk-passed { background: linear-gradient(135deg, #38A169, #2f855a); }
    
    /* Compact event timeline */
    .event-compact {
        display: flex;
        align-items: center;
        padding: 0.5rem 0.75rem;
        margin: 0.25rem 0;
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.03);
        border-left: 4px solid;
        font-size: 0.9rem;
        transition: all 0.2s ease;
    }
    
    .event-compact:hover {
        background: rgba(255, 255, 255, 0.08);
        transform: translateX(5px);
    }
    
    .event-high { border-left-color: #ef4444; background: rgba(239, 68, 68, 0.1); }
    .event-medium { border-left-color: #f59e0b; background: rgba(245, 158, 11, 0.1); }
    .event-low { border-left-color: #10b981; background: rgba(16, 185, 129, 0.1); }
    
    .event-time {
        min-width: 80px;
        font-weight: 600;
        color: #60a5fa;
    }
    
    .event-currency {
        min-width: 45px;
        font-weight: 700;
        text-align: center;
    }
    
    .event-currency.usd {
        color: #fbbf24;
        text-shadow: 0 0 10px rgba(251, 191, 36, 0.5);
    }
    
    /* Action items - scannable checklist */
    .action-section {
        background: linear-gradient(135deg, rgba(17, 24, 39, 0.8), rgba(31, 41, 55, 0.6));
        border: 1px solid rgba(75, 85, 99, 0.3);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 20px 0;
    }
    
    .action-item {
        display: flex;
        align-items: center;
        padding: 0.75rem;
        margin: 0.5rem 0;
        background: rgba(255, 255, 255, 0.03);
        border-left: 4px solid #06b6d4;
        border-radius: 8px;
        transition: all 0.3s ease;
    }
    
    .action-item:hover {
        background: rgba(255, 255, 255, 0.08);
        border-left-color: #0891b2;
    }
    
    .action-emoji {
        font-size: 1.2rem;
        margin-right: 12px;
        min-width: 30px;
    }
    
    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(30, 41, 59, 0.5);
        border-radius: 12px;
        padding: 4px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 8px;
        color: #94a3b8;
        border: none;
        padding: 0.75rem 1.5rem;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #3b82f6, #1e40af) !important;
        color: white !important;
    }
    
    /* Buttons */
    .stButton button {
        background: linear-gradient(135deg, #3b82f6, #1e40af);
        border: none;
        border-radius: 12px;
        color: white;
        font-weight: 600;
        padding: 0.75rem 2rem;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3);
    }
    
    .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(59, 130, 246, 0.4);
    }
    
    /* Typography improvements */
    h1 { color: #f1f5f9; text-shadow: 0 2px 4px rgba(0,0,0,0.3); }
    h2 { color: #e2e8f0; margin-bottom: 1rem; }
    h3 { color: #cbd5e1; }
    
    /* Weekend styling */
    .weekend-notice {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(67, 56, 202, 0.1));
        border: 2px solid #6366f1;
        border-radius: 16px;
        padding: 2rem;
        text-align: center;
        color: #c7d2fe;
    }
</style>
""", unsafe_allow_html=True)

# --- DATABASE AND UTILITY FUNCTIONS (keeping existing ones) ---
@st.cache_resource
def init_connection():
    try:
        connection_string = st.secrets["mongo"]["connection_string"]
        client = pymongo.MongoClient(connection_string)
        return client
    except (KeyError, pymongo.errors.ConfigurationError) as e:
        st.error(f"Failed to connect to MongoDB. Please check your secrets.toml file. Error: {e}")
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
        st.info("Database is currently empty. Please fetch live economic data.")
        return pd.DataFrame()
    return pd.DataFrame(items)

def update_db_from_csv(file_path):
    client = init_connection()
    if client is None:
        return 0, 0
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    try:
        df = pd.read_csv(file_path)
        events = df.to_dict('records')
    except FileNotFoundError:
        st.error(f"Scraped data file not found at: {file_path}")
        return 0, 0
    upserted_count = 0
    modified_count = 0
    for event in events:
        query = {
            'date': event.get('date'),
            'time': event.get('time'),
            'event': event.get('event'),
            'currency': event.get('currency')
        }
        result = collection.update_one(query, {"$set": event}, upsert=True)
        if result.upserted_id:
            upserted_count += 1
        elif result.modified_count > 0:
            modified_count += 1
    return upserted_count, modified_count

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

def analyze_day_events(target_date, events):
    plan = "Standard Day Plan"
    reason = "No high-impact USD news found. Proceed with the Standard Day Plan and your directional bias."
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
                    return "No Trade Day", f"Critical afternoon USD event '{event_name}' at {event_time.strftime('%I:%M %p')}. Capital preservation is the priority.", morning_events, afternoon_events, all_day_events
            if is_high_impact and event_time:
                has_high_impact_usd_event = True
    
    if has_high_impact_usd_event:
        plan = "News Day Plan"
        reason = "High-impact USD news detected. The News Day Plan is active. Be patient and wait for the news-driven liquidity sweep."
    
    return plan, reason, morning_events, afternoon_events, all_day_events

def get_current_session(current_time):
    current = current_time.time()
    if time(2, 0) <= current < time(5, 0): return "London"
    elif time(9, 30) <= current < time(12, 0): return "NY Morning"
    elif time(12, 0) <= current < time(13, 30): return "NY Lunch"
    elif time(13, 30) <= current < time(16, 0): return "NY Afternoon"
    else: return "Pre-Market"

# --- ENHANCED UI COMPONENTS ---

def display_header_dashboard():
    """Quick scan header with essential info"""
    current_time = get_current_market_time()
    time_to_open = time_until_market_open()
    session = get_current_session(current_time)
    
    st.markdown('<div class="quick-info-grid">', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f'''
        <div class="info-card">
            <div class="metric-label">Current ET Time</div>
            <div class="metric-value">{current_time.strftime("%I:%M %p")}</div>
        </div>
        ''', unsafe_allow_html=True)
    
    with col2:
        if time_to_open.total_seconds() > 0:
            hours, rem = divmod(int(time_to_open.total_seconds()), 3600)
            mins, _ = divmod(rem, 60)
            display = f"{hours}h {mins}m"
            label = "Time to Open"
        else:
            display = "OPEN" if current_time.time() < time(16, 0) else "CLOSED"
            label = "Market Status"
        
        st.markdown(f'''
        <div class="info-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{display}</div>
        </div>
        ''', unsafe_allow_html=True)
    
    with col3:
        st.markdown(f'''
        <div class="info-card">
            <div class="metric-label">Current Session</div>
            <div class="metric-value">{session}</div>
        </div>
        ''', unsafe_allow_html=True)
    
    with col4:
        today = date.today()
        day_name = today.strftime("%A")
        st.markdown(f'''
        <div class="info-card">
            <div class="metric-label">Trading Day</div>
            <div class="metric-value">{day_name}</div>
        </div>
        ''', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

def display_risk_management():
    """Compact risk management display"""
    st.markdown('<div class="risk-section">', unsafe_allow_html=True)
    st.markdown("## 🧠 Risk Management")
    
    # Initialize session state
    if 'standard_risk' not in st.session_state: st.session_state.standard_risk = 300
    if 'current_balance' not in st.session_state: st.session_state.current_balance = 2800
    if 'streak' not in st.session_state: st.session_state.streak = 5
    if 'eval_target' not in st.session_state: st.session_state.eval_target = 6000
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.session_state.current_balance = st.number_input("Current Profit ($)", value=st.session_state.current_balance, step=50)
    with col2:
        st.session_state.streak = st.number_input("Win/Loss Streak", value=st.session_state.streak, step=1)
    with col3:
        st.session_state.standard_risk = st.number_input("Standard Risk ($)", value=st.session_state.standard_risk, step=10)
    
    # Risk calculation logic
    profit_loss = st.session_state.current_balance
    is_in_profit = profit_loss > 0
    
    if not is_in_profit:
        suggested_risk = st.session_state.standard_risk / 2
        reason = "Account in drawdown. Use Minimum Risk."
        risk_class = "risk-minimum"
    elif st.session_state.streak < 0:
        suggested_risk = st.session_state.standard_risk / 2
        reason = f"{abs(st.session_state.streak)}-trade losing streak. Minimum Risk."
        risk_class = "risk-minimum"
    elif st.session_state.streak >= WIN_STREAK_THRESHOLD:
        suggested_risk = st.session_state.standard_risk / 2
        reason = f"{st.session_state.streak}-win streak. Defensive Risk."
        risk_class = "risk-defensive"
    elif profit_loss >= st.session_state.eval_target:
        suggested_risk = 0
        reason = "Target reached! Stop trading."
        risk_class = "risk-passed"
    else:
        suggested_risk = st.session_state.standard_risk
        reason = "Standard operating conditions."
        risk_class = "risk-normal"
    
    st.markdown(f'''
    <div class="risk-output {risk_class}">
        <strong>Next Trade Risk: ${int(suggested_risk)}</strong><br>
        <small>{reason}</small>
    </div>
    ''', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

def display_main_plan_card(plan, reason):
    """Large, prominent plan display"""
    if plan == "No Trade Day": 
        card_class, icon, title = "no-trade", "🚫", "NO TRADE DAY"
    elif plan == "News Day Plan": 
        card_class, icon, title = "news-day", "📰", "NEWS DAY PLAN"
    else: 
        card_class, icon, title = "standard-day", "✅", "STANDARD DAY PLAN"
    
    st.markdown(f'''
    <div class="main-plan-card {card_class}">
        <h1 style="font-size: 2.5rem; margin: 0;">{icon}</h1>
        <h1 style="margin: 0.5rem 0;">{title}</h1>
        <p style="font-size: 1.2rem; margin: 1rem 0 0 0; opacity: 0.9;">{reason}</p>
    </div>
    ''', unsafe_allow_html=True)

def display_compact_events(morning_events, afternoon_events, all_day_events):
    """Streamlined event display"""
    if not any([morning_events, afternoon_events, all_day_events]):
        st.info("📅 No economic events scheduled for today.")
        return
    
    tabs = st.tabs(["🌅 Morning", "🌇 Afternoon", "📅 All Day"] if all_day_events else ["🌅 Morning", "🌇 Afternoon"])
    
    with tabs[0]:  # Morning
        if morning_events:
            for event in sorted([e for e in morning_events if e['raw_time']], key=lambda x: x['raw_time']):
                impact_class = "event-high" if "High" in event['impact'] else ("event-medium" if "Medium" in event['impact'] else "event-low")
                currency_class = "usd" if event['currency'] == 'USD' else ""
                
                st.markdown(f'''
                <div class="event-compact {impact_class}">
                    <div class="event-time">{event["time"]}</div>
                    <div class="event-currency {currency_class}">{event["currency"]}</div>
                    <div style="flex: 1; margin-left: 15px;">{event["name"]}</div>
                </div>
                ''', unsafe_allow_html=True)
        else:
            st.markdown("*No morning events*")
    
    with tabs[1]:  # Afternoon
        if afternoon_events:
            for event in sorted([e for e in afternoon_events if e['raw_time']], key=lambda x: x['raw_time']):
                impact_class = "event-high" if "High" in event['impact'] else ("event-medium" if "Medium" in event['impact'] else "event-low")
                currency_class = "usd" if event['currency'] == 'USD' else ""
                
                st.markdown(f'''
                <div class="event-compact {impact_class}">
                    <div class="event-time">{event["time"]}</div>
                    <div class="event-currency {currency_class}">{event["currency"]}</div>
                    <div style="flex: 1; margin-left: 15px;">{event["name"]}</div>
                </div>
                ''', unsafe_allow_html=True)
        else:
            st.markdown("*No afternoon events*")
    
    if all_day_events and len(tabs) > 2:
        with tabs[2]:  # All Day
            for event in all_day_events:
                impact_class = "event-high" if "High" in event['impact'] else ("event-medium" if "Medium" in event['impact'] else "event-low")
                currency_class = "usd" if event['currency'] == 'USD' else ""
                
                st.markdown(f'''
                <div class="event-compact {impact_class}">
                    <div class="event-time">All Day</div>
                    <div class="event-currency {currency_class}">{event["currency"]}</div>
                    <div style="flex: 1; margin-left: 15px;">{event["name"]}</div>
                </div>
                ''', unsafe_allow_html=True)

def display_action_checklist(plan):
    """Quick-scan action items"""
    st.markdown('<div class="action-section">', unsafe_allow_html=True)
    st.markdown("### 🎯 Action Items")
    
    if plan == "News Day Plan":
        actions = [
            ("🚫", "DO NOT trade the morning session"),
            ("📊", "Mark NY Lunch Range (12:00 PM - 1:30 PM)"),
            ("👀", "Wait for liquidity raid after news"),
            ("🎯", "Prime entry: 2:00 PM - 3:00 PM"),
            ("✅", "Enter on MSS + FVG confirmation")
        ]
    elif plan == "Standard Day Plan":
        actions = [
            ("📈", "Mark Previous Day PM Range"),
            ("🌍", "Mark London Session Range"),
            ("👀", "Watch NY Open Judas Swing (9:30-10:30)"),
            ("🎯", "Prime entry: 10:00 AM - 11:00 AM"),
            ("✅", "Enter after sweep with MSS + FVG")
        ]
    else:
        actions = [
            ("🚫", "Stand aside completely"),
            ("💰", "Preserve capital"),
            ("📚", "Journal and review"),
            ("🧘", "Prepare for next trading day")
        ]
    
    for emoji, text in actions:
        st.markdown(f'''
        <div class="action-item">
            <div class="action-emoji">{emoji}</div>
            <div>{text}</div>
        </div>
        ''', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

def display_friday_alert(plan):
    """T.G.I.F. setup alert for Fridays"""
    if date.today().weekday() != 4:  # Only show on Fridays
        return
        
    with st.expander("🎯 T.G.I.F. Setup Alert", expanded=False):
        st.info("Friday T.G.I.F. Setup might be in play - retracement back into weekly range.")
        
        st.markdown("**Pre-conditions:**")
        st.markdown("✓ Strong weekly trend established")
        st.markdown("✓ Higher timeframe level hit (premium/discount array)")
        
        if plan == "Standard Day Plan":
            st.success("**Perfect alignment:** Watch for morning Judas swing peak (9:30-10:30 AM) then target 20-30% weekly retracement.")
        elif plan == "News Day Plan":
            st.warning("**Adjusted timing:** Look for afternoon peak formation (1:30-2:00 PM) after news releases.")
        else:
            st.error("**Observe only:** No trading today due to high-risk environment.")

# --- MAIN APPLICATION ---
def main():
    st.title("📈 US Index Trading Plan")
    
    # Header dashboard
    display_header_dashboard()
    
    # Data fetch button
    if st.button("🔄 Fetch Live Data", type="primary"):
        with st.spinner("Fetching data..."):
            try:
                result = subprocess.run([sys.executable, "ffscraper.py"], capture_output=True, check=True, text=True)
                upserted, modified = update_db_from_csv(SCRAPED_DATA_PATH)
                st.success(f"✅ Updated! {upserted} new, {modified} modified")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"❌ Update failed: {str(e)}")
    
    # Date selection
    col1, col2 = st.columns([3, 1])
    with col1:
        selected_date = st.date_input("📅 Analysis Date", value=date.today())
    with col2:
        view_mode = st.selectbox("View", ["Today", "Week"], index=0)
    
    st.markdown("---")
    
    # Weekend check
    if selected_date.weekday() >= 5:
        st.markdown('''
        <div class="weekend-notice">
            <h1>📴 MARKET CLOSED</h1>
            <p style="font-size: 1.2rem; margin-top: 1rem;">
                US indices do not trade on weekends.<br>
                📚 Use this time to journal, review trades, or recharge.
            </p>
        </div>
        ''', unsafe_allow_html=True)
        return
    
    # Get data
    df = get_events_from_db()
    if df.empty:
        st.warning("👋 No economic data found. Click **Fetch Live Data** to load current events.")
        return
    
    records = df.to_dict('records')
    
    def get_events_for(d): 
        return [row for row in records if parse_date(row.get('date', '')) == d]
    
    if view_mode == "Today":
        # Risk Management
        display_risk_management()
        
        # Get today's events and plan
        events = get_events_for(selected_date)
        if not events:
            plan, reason = "Standard Day Plan", "No economic events found. Proceed with Standard Day Plan."
            morning, afternoon, allday = [], [], []
        else:
            plan, reason, morning, afternoon, allday = analyze_day_events(selected_date, events)
        
        # Main plan display
        display_main_plan_card(plan, reason)
        
        # Friday T.G.I.F. alert
        display_friday_alert(plan)
        
        # Two column layout for actions and events
        col1, col2 = st.columns([1, 1])
        
        with col1:
            display_action_checklist(plan)
        
        with col2:
            st.markdown("### 📅 Today's Events")
            display_compact_events(morning, afternoon, allday)
        
        # Trade setup details in expandable section
        with st.expander("🎯 Detailed Trade Setups", expanded=False):
            if plan == "Standard Day Plan":
                st.markdown("""
                #### ✅ Standard Day Setup
                **Phase I:** Mark Previous Day PM High/Low + London Session Range
                
                **Phase II:** NY AM Silver Bullet (10-11 AM)
                
                **Phase III:** Watch for 9:30 AM sweep of short-term level
                
                **Phase IV:** Enter on MSS + FVG after sweep
                
                **Phase V:** Target opposing liquidity level
                """)
            
            elif plan == "News Day Plan":
                st.markdown("""
                #### 📰 News Day Setup  
                **Phase I:** Mark NY Lunch Range (12:00-1:30 PM)
                
                **Phase II:** NY PM Silver Bullet (2:00-3:00 PM) 
                
                **Phase III:** Wait for news-driven liquidity sweep
                
                **Phase IV:** Enter on MSS + FVG after news reversal
                
                **Phase V:** Target structural levels opposite the spike
                """)
            
            else:
                st.markdown("""
                #### 🚫 No Trade Day
                **Capital Preservation Mode**
                - Stand aside completely
                - Observe for educational purposes
                - Use time for analysis and preparation
                """)
    
    else:  # Week view
        st.markdown("## 🗓 Weekly Trading Outlook")
        
        start_of_week = selected_date - timedelta(days=selected_date.weekday())
        
        for i in range(5):
            d = start_of_week + timedelta(days=i)
            events_for_day = get_events_for(d)
            
            # Determine plan for the day
            if not events_for_day:
                plan, reason = "Standard Day Plan", "No economic events."
            else:
                plan, reason, *_ = analyze_day_events(d, events_for_day)
            
            # Plan styling
            if plan == "No Trade Day": 
                card_class, icon = "no-trade", "🚫"
            elif plan == "News Day Plan": 
                card_class, icon = "news-day", "📰"
            else: 
                card_class, icon = "standard-day", "✅"
            
            # Day card
            is_today = d == date.today()
            border_style = "border: 3px solid #3b82f6;" if is_today else ""
            
            st.markdown(f'''
            <div class="main-plan-card {card_class}" style="grid-column: span 1; padding: 1rem; margin: 0.5rem 0; {border_style}">
                <h3 style="margin: 0;">{icon} {d.strftime('%A, %b %d')}</h3>
                <h4 style="margin: 0.5rem 0;">{plan}</h4>
                <p style="margin: 0.5rem 0 0 0; font-size: 0.9rem;">{reason}</p>
                {"<small style='color: #3b82f6; font-weight: bold;'>← TODAY</small>" if is_today else ""}
            </div>
            ''', unsafe_allow_html=True)
            
            # Show key events for the day
            if events_for_day:
                high_impact_usd = [e for e in events_for_day if e.get('currency', '').upper() == 'USD' and 
                                 (parse_impact(e.get('impact', '')) == 'High' or 
                                  any(keyword.lower() in e.get('event', '').lower() for keyword in FORCED_HIGH_IMPACT_KEYWORDS))]
                
                if high_impact_usd:
                    with st.expander(f"Key Events - {d.strftime('%A')}", expanded=False):
                        for event in high_impact_usd[:3]:  # Show top 3
                            event_time = parse_time(event.get('time', ''))
                            time_display = event_time.strftime('%I:%M %p') if event_time else 'All Day'
                            st.markdown(f"🔴 **{time_display}** - {event.get('event', '')}")

if __name__ == "__main__":
    main()
