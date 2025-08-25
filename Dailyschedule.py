import streamlit as st
import pandas as pd
import yfinance as yf
import csv
from datetime import datetime, time, date, timedelta
import pytz
import subprocess
import sys
import os
import pymongo
import requests # Added for earnings data

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
MORNING_CUTOFF = time(12, 0)
AFTERNOON_NO_TRADE_START = time(13, 55)
NO_TRADE_KEYWORDS = ['FOMC Statement', 'FOMC Press Conference', 'Interest Rate Decision', 'Monetary Policy Report']
FORCED_HIGH_IMPACT_KEYWORDS = ['Powell Speaks', 'Fed Chair', 'Non-Farm', 'NFP', 'CPI', 'Consumer Price Index', 'PPI', 'Producer Price Index', 'GDP']
WIN_STREAK_THRESHOLD = 5

# --- ENHANCED CSS STYLES ---
st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%); }
    .trading-dashboard { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }
    .main-plan-card { grid-column: span 2; padding: 1rem; border-radius: 12px; text-align: center; margin: 0.5rem 0; border: 2px solid; box-shadow: 0 4px 16px rgba(0,0,0,0.3); backdrop-filter: blur(10px); position: relative; overflow: hidden; }
    .main-plan-card::before { content: ''; position: absolute; top: 0; left: -100%; width: 100%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent); transition: left 0.5s; }
    .main-plan-card:hover::before { left: 100%; }
    .no-trade { background: linear-gradient(135deg, rgba(244, 67, 54, 0.15), rgba(183, 28, 28, 0.08)); border-color: #f44336; color: #ffcdd2; }
    .news-day { background: linear-gradient(135deg, rgba(255, 152, 0, 0.15), rgba(239, 108, 0, 0.08)); border-color: #ff9800; color: #ffcc02; }
    .standard-day { background: linear-gradient(135deg, rgba(76, 175, 80, 0.15), rgba(56, 142, 60, 0.08)); border-color: #4caf50; color: #a5d6a7; }
    .quick-info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
    .info-card { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 1rem; text-align: center; backdrop-filter: blur(10px); transition: all 0.3s ease; box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
    .info-card:hover { transform: translateY(-5px); box-shadow: 0 8px 25px rgba(0,0,0,0.3); border-color: rgba(255, 255, 255, 0.2); }
    .info-card .metric-label { color: #94a3b8; font-size: 0.85rem; font-weight: 500; margin-bottom: 8px; }
    .info-card .metric-value { color: #ffffff; font-size: 1.4rem; font-weight: 700; text-shadow: 0 2px 4px rgba(0,0,0,0.3); }
    .risk-section { background: linear-gradient(135deg, rgba(30, 41, 59, 0.6), rgba(15, 23, 42, 0.4)); border: 1px solid rgba(59, 130, 246, 0.2); border-radius: 12px; padding: 1rem; margin: 15px 0; box-shadow: 0 4px 16px rgba(59, 130, 246, 0.08); }
    .risk-output { padding: 0.8rem; border-radius: 8px; text-align: center; color: white; font-weight: bold; font-size: 1.1rem; margin: 10px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.2); transition: all 0.3s ease; }
    .risk-output:hover { transform: scale(1.02); }
    .risk-normal { background: linear-gradient(135deg, #3182CE, #2c5aa0); }
    .risk-defensive { background: linear-gradient(135deg, #DD6B20, #c05621); }
    .risk-minimum { background: linear-gradient(135deg, #E53E3E, #c53030); }
    .risk-passed { background: linear-gradient(135deg, #38A169, #2f855a); }
    .event-compact { display: flex; align-items: center; padding: 0.5rem 0.75rem; margin: 0.25rem 0; border-radius: 8px; background: rgba(255, 255, 255, 0.03); border-left: 4px solid; font-size: 0.9rem; transition: all 0.2s ease; }
    .event-compact:hover { background: rgba(255, 255, 255, 0.08); transform: translateX(5px); }
    .event-high { border-left-color: #ef4444; background: rgba(239, 68, 68, 0.1); }
    .event-medium { border-left-color: #f59e0b; background: rgba(245, 158, 11, 0.1); }
    .event-low { border-left-color: #10b981; background: rgba(16, 185, 129, 0.1); }
    .event-time { min-width: 80px; font-weight: 600; color: #60a5fa; }
    .event-currency { min-width: 45px; font-weight: 700; text-align: center; }
    .event-currency.usd { color: #fbbf24; text-shadow: 0 0 10px rgba(251, 191, 36, 0.5); }
    .action-section { background: linear-gradient(135deg, rgba(17, 24, 39, 0.8), rgba(31, 41, 55, 0.6)); border: 1px solid rgba(75, 85, 99, 0.3); border-radius: 12px; padding: 1.5rem; margin: 20px 0; }
    .action-item { display: flex; align-items: center; padding: 0.75rem; margin: 0.5rem 0; background: rgba(255, 255, 255, 0.03); border-left: 4px solid #06b6d4; border-radius: 8px; transition: all 0.3s ease; }
    .action-item:hover { background: rgba(255, 255, 255, 0.08); border-left-color: #0891b2; }
    .action-emoji { font-size: 1.2rem; margin-right: 12px; min-width: 30px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background: rgba(30, 41, 59, 0.5); border-radius: 12px; padding: 4px; }
    .stTabs [data-baseweb="tab"] { background: rgba(255, 255, 255, 0.05); border-radius: 8px; color: #94a3b8; border: none; padding: 0.75rem 1.5rem; }
    .stTabs [aria-selected="true"] { background: linear-gradient(135deg, #3b82f6, #1e40af) !important; color: white !important; }
    .stButton button { background: linear-gradient(135deg, #3b82f6, #1e40af); border: none; border-radius: 12px; color: white; font-weight: 600; padding: 0.75rem 2rem; transition: all 0.3s ease; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3); }
    .stButton button:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(59, 130, 246, 0.4); }
    h1 { color: #f1f5f9; text-shadow: 0 2px 4px rgba(0,0,0,0.3); }
    h2 { color: #e2e8f0; margin-bottom: 1rem; }
    h3 { color: #cbd5e1; }
    .weekend-notice { background: linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(67, 56, 202, 0.1)); border: 2px solid #6366f1; border-radius: 16px; padding: 2rem; text-align: center; color: #c7d2fe; }
    .pill { padding: 4px 10px; border-radius: 999px; font-weight: 700; font-size: 12px; display: inline-block; }
    .pill-ok { background: rgba(16,185,129,.15); border:1px solid rgba(16,185,129,.4); color:#a7f3d0; }
    .pill-warn { background: rgba(245,158,11,.15); border:1px solid rgba(245,158,11,.4); color:#fde68a; }
    .pill-bad { background: rgba(239,68,68,.15); border:1px solid rgba(239,68,68,.4); color:#fecaca; }
    .week-day-card { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 1rem; margin: 0.5rem 0; }
</style>
""", unsafe_allow_html=True)

# --- EARNINGS DATA FUNCTIONS ---
def get_earnings_data(date):
    """
    Fetch earnings data for a specific date from earningswhispers.com
    
    Args:
        date (str): Date in YYYYMMDD format (e.g., '20250827')
    
    Returns:
        requests.Response: The response object
    """
    url = f"https://www.earningswhispers.com/api/caldata/{date}"
    
    # NOTE: This hardcoded cookie may expire, causing the request to fail.
    # If it fails, you'll need to get a new cookie from your browser's developer tools
    # while visiting earningswhispers.com and update it here.
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Sec-Fetch-Site': 'same-origin',
        'Cookie': '*ga=GA1.1.1871602727.1756109420; *ga_7LKB78MJRT=GS2.1.s1756109419$o1$g1$t1756109620$j53$l0$h0; FCNEC=%5B%5B%22AKsRol_D5LIb-C0BGokGRcHYSh8w3v-ZEVrhem9PxvFXEEHpDKl5LYpIIQUNPvc4KPLFbvvN6OSTTLoB2Oh0G8jHxNO_vMxDS3D3LmDUImtm8Fln_JZV44PpjBKu9Ry2_4AlXsKSvZDLivP1jc-MWXlCXxQPsGYEAA%3D%3D%22%5D%5D; *gid=GA1.2.208076863.1756109420; hidenonconfirmed=1; *gat_gtag_UA_59314727_1=1; showlistview=1; **eoi=ID=f39c0aada87a4aa0:T=1756109428:RT=1756109428:S=AA-AfjZ8WXuqYya3nHB6hyravhQu; **gads=ID=421932e821d1cb4e:T=1756109428:RT=1756109428:S=ALNI_Mbrc1a7GzE5c_L1E0ZJGBtxjTBwWw; __gpi=UID=00001269ff9d6435:T=1756109428:RT=1756109428:S=ALNI_MZrujMeF0a8t7ZfZc_92dh0iYNyUw; FCCDCF=%5Bnull%2Cnull%2Cnull%2C%5B%22CQWtIsAQWtIsAEsACBENB5FoAP_gAEPgACiQK1IB_C7EbCFCiDp3IKMEMAhHABBAYsAwAAYBAwAADBIQIAQCgkEYBASAFCACCAAAKASBAAAgCAAAAUAAIAAVAABAAAwAIBAIIAAAgAAAAEAIAAAACIAAEQCAAAAEAEAAkAgAAAIASAAAAAAAAACBAAAAAAAAAAAAAAAABAAAAQAAQAAAAAAAiAAAAAAAABAIAAAAAAAAAAAAAAAAAAAAAAgAAAAAAAAAABAAAAAAAQR2QD-F2I2EKFEHCuQUYIYBCuACAAxYBgAAwCBgAAGCQgQAgFJIIkCAEAIEAAEAAAQAgCAABQEBAAAIAAAAAqAACAABgAQCAQQIABAAAAgIAAAAAAEQAAIgEAAAAIAIABABAAAAQAkAAAAAAAAAECAAAAAAAAAAAAAAAAAAAAAEABgAAAAAABEAAAAAAAACAQIAAA%22%2C%222~61.89.122.184.196.230.314.442.445.494.550.576.827.1029.1033.1046.1047.1051.1097.1126.1166.1301.1342.1415.1725.1765.1942.1958.1987.2068.2072.2074.2107.2213.2219.2223.2224.2328.2331.2387.2416.2501.2567.2568.2575.2657.2686.2778.2869.2878.2908.2920.2963.3005.3023.3100.3126.3219.3234.3235.3253.3309.3731.6931.8931.13731.15731~dv.%22%2C%22D60C93C9-4C28-4544-9A14-F87EF64351F6%22%5D%5D; .AspNet.Consent=yes; .AspNetCore.Antiforgery.gLLQ8_-gK9o=CfDJ8NaHMTcqVNhIs_-sI2gPc4rtFnuS2j4Z0rDD5AjasjQisQ8vY2jogB9UpGs7fiwdzp8iQkdfDS2HKCptETwvOfWR7PpfXHHUcxUqw42oQL-rgXtXj7SfSAxQMJbXb5ncWigO-9fGhBRvUqOX59M6JSA',
        'Referer': f'https://www.earningswhispers.com/calendar/{date}',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Accept-Language': 'en-GB,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15',
        'X-Requested-With': 'XMLHttpRequest',
        'Priority': 'u=3, i'
    }
    
    response = requests.get(url, headers=headers)
    return response

def format_earnings_data(data):
    """Extract and format company name from earnings data"""
    results = []
    for item in data:
        company = item.get('company', 'N/A')
        results.append({'company': company})
    return results

@st.cache_data(ttl=3600)  # Cache for 1 hour
def fetch_and_format_earnings(target_date):
    """Fetches and formats earnings data for a given date, with caching."""
    date_str = target_date.strftime('%Y%m%d')
    try:
        response = get_earnings_data(date_str)
        if response.status_code == 200:
            data = response.json()
            return format_earnings_data(data)
        else:
            return []
    except requests.exceptions.RequestException:
        return []
    except Exception:
        return []

# --- DATABASE AND UTILITY FUNCTIONS ---
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

# --- TIME/DATE HELPERS ---
def get_current_market_time():
    et = pytz.timezone('US/Eastern')
    return datetime.now(et)

def time_until_market_open():
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now.time() > time(16, 0):
        market_open += timedelta(days=1)
    if now.weekday() >= 5:
        market_open += timedelta(days=7 - now.weekday())
    return market_open - now

def parse_time(time_str):
    if not time_str or pd.isna(time_str) or str(time_str).lower() in ['empty', '']:
        return None
    for fmt in ('%I:%M%p', '%I:%M %p', '%H:%M'):
        try:
            return datetime.strptime(str(time_str).strip(), fmt).time()
        except ValueError:
            continue
    return None

def parse_date(date_str):
    try:
        return datetime.strptime(str(date_str).strip(), '%d/%m/%Y').date()
    except (ValueError, TypeError):
        return None

def parse_impact(impact_str):
    if not impact_str or pd.isna(impact_str):
        return "Low"
    lower = str(impact_str).lower()
    if 'high' in lower:
        return "High"
    if 'medium' in lower:
        return "Medium"
    if 'low' in lower:
        return "Low"
    return "Low"

# =======================================================
# --- SEASONALITY ANALYSIS MODULE ---
# =======================================================

@st.cache_data(ttl=3600)
def analyze_seasonal_bias(symbol: str, target_date_str: str, lookback_years: int = 25):
    try:
        target_date = pd.to_datetime(target_date_str)
        target_week_num = target_date.isocalendar().week
        end_date = datetime.now()
        start_date = end_date - pd.DateOffset(years=lookback_years)
        data = yf.download(symbol, start=start_date, end=end_date, interval='1wk', progress=False, auto_adjust=True)
        if data.empty:
            return None, None
        last_week_monday = data.index[-1]
        if (datetime.now() - last_week_monday).days < 6:
            data = data.iloc[:-1]
        data['Year'] = data.index.year
        data['Week'] = data.index.isocalendar().week
        week_data = data[data['Week'] == target_week_num].copy()
        if week_data.empty:
            return None, None
        week_data['Return'] = (week_data['Close'] - week_data['Open']) / week_data['Open']
        results = []
        for lookback in [lookback_years, 10]:
            start_year_for_lookback = datetime.now().year - lookback
            subset = week_data[week_data['Year'] >= start_year_for_lookback]
            if len(subset) == 0:
                continue
            avg_return = subset['Return'].mean()
            std_dev = subset['Return'].std()
            positive_weeks = (subset['Return'] > 0).sum()
            total_weeks = len(subset)
            percent_positive = positive_weeks / total_weeks if total_weeks > 0 else 0
            bias = get_seasonal_bias_label(avg_return, percent_positive, std_dev)
            results.append({
                'Lookback': f'Last {lookback} Years',
                'Years': f"{subset['Year'].min()}-{subset['Year'].max()}",
                'Seasonal Bias': bias,
                'Avg Weekly Return': avg_return,
                '% Positive Weeks': percent_positive,
                'Observations': f"{positive_weeks}/{total_weeks}"
            })
        if not results:
            return None, None
        summary_df = pd.DataFrame(results).set_index('Lookback')
        summary_df['Avg Weekly Return'] = summary_df['Avg Weekly Return'].map('{:.2%}'.format)
        summary_df['% Positive Weeks'] = summary_df['% Positive Weeks'].map('{:.2%}'.format)
        summary_df = summary_df[['Years', 'Seasonal Bias', 'Avg Weekly Return', '% Positive Weeks', 'Observations']]
        detailed_df = week_data[['Return']].copy()
        detailed_df.index = week_data['Year']
        detailed_df['Return'] = detailed_df['Return'].map('{:.2%}'.format)
        return summary_df, detailed_df
    except Exception:
        return None, None

def get_seasonal_bias_label(avg_return: float, percent_positive: float, std_dev: float) -> str:
    if pd.isna(std_dev) or std_dev == 0: std_dev = 0.01
    STRONG_RETURN_THRESHOLD, STRONG_WIN_RATE, WEAK_WIN_RATE = std_dev, 0.66, 0.33
    NEUTRAL_BAND_UPPER, NEUTRAL_BAND_LOWER = 0.55, 0.45
    if avg_return > STRONG_RETURN_THRESHOLD and percent_positive >= STRONG_WIN_RATE: return "Strongly Bullish"
    elif avg_return < -STRONG_RETURN_THRESHOLD and percent_positive <= WEAK_WIN_RATE: return "Strongly Bearish"
    elif avg_return > 0 and percent_positive > NEUTRAL_BAND_UPPER: return "Bullish"
    elif avg_return < 0 and percent_positive < NEUTRAL_BAND_LOWER: return "Bearish"
    else: return "Neutral / Inconclusive"

# --- CALENDAR ANALYSIS ---
def analyze_day_events(target_date, events):
    plan, reason = "Standard Day Plan", "No high-impact USD news found. Proceed with the Standard Day Plan."
    has_high_impact_usd_event, morning_events, afternoon_events, all_day_events = False, [], [], []
    for event in events:
        event_time = parse_time(event.get('time', ''))
        event_name, currency = event.get('event', ''), event.get('currency', '').strip().upper()
        parsed_impact = parse_impact(event.get('impact', ''))
        is_forced_high = any(k.lower() in event_name.lower() for k in FORCED_HIGH_IMPACT_KEYWORDS)
        is_high_impact = (parsed_impact == 'High') or is_forced_high
        display_impact = "High (Forced)" if is_forced_high and parsed_impact != 'High' else ("High" if is_high_impact else parsed_impact)
        event_details = {'name': event_name, 'currency': currency, 'impact': display_impact, 'time': event_time.strftime('%I:%M %p') if event_time else 'All Day', 'raw_time': event_time}
        if event_time is None: all_day_events.append(event_details)
        elif event_time < MORNING_CUTOFF: morning_events.append(event_details)
        else: afternoon_events.append(event_details)
        if currency == 'USD':
            if any(k.lower() in event_name.lower() for k in NO_TRADE_KEYWORDS):
                if event_time and event_time >= AFTERNOON_NO_TRADE_START:
                    return "No Trade Day", f"Critical afternoon USD event '{event_name}' at {event_time.strftime('%I:%M %p')}.", morning_events, afternoon_events, all_day_events
            if is_high_impact and event_time: has_high_impact_usd_event = True
    if has_high_impact_usd_event:
        plan, reason = "News Day Plan", "High-impact USD news detected. The News Day Plan is active."
    return plan, reason, morning_events, afternoon_events, all_day_events

# --- SESSION HELPER ---
def get_current_session(current_time):
    current = current_time.time()
    if time(2, 0) <= current < time(5, 0): return "London"
    elif time(9, 30) <= current < time(12, 0): return "NY Morning"
    elif time(12, 0) <= current < time(13, 30): return "NY Lunch"
    elif time(13, 30) <= current < time(16, 0): return "NY Afternoon"
    else: return "Pre-Market"

# --- UI COMPONENTS ---
def display_header_dashboard():
    current_time, time_to_open, session = get_current_market_time(), time_until_market_open(), get_current_session(get_current_market_time())
    st.markdown('<div class="quick-info-grid">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.markdown(f'<div class="info-card"><div class="metric-label">Current ET Time</div><div class="metric-value">{current_time.strftime("%I:%M %p")}</div></div>', unsafe_allow_html=True)
    with col2:
        if time_to_open.total_seconds() > 0:
            h, rem = divmod(int(time_to_open.total_seconds()), 3600); m, _ = divmod(rem, 60)
            display, label = f"{h}h {m}m", "Time to Open"
        else: display, label = ("OPEN" if current_time.time() < time(16, 0) else "CLOSED"), "Market Status"
        st.markdown(f'<div class="info-card"><div class="metric-label">{label}</div><div class="metric-value">{display}</div></div>', unsafe_allow_html=True)
    with col3: st.markdown(f'<div class="info-card"><div class="metric-label">Current Session</div><div class="metric-value">{session}</div></div>', unsafe_allow_html=True)
    with col4: st.markdown(f'<div class="info-card"><div class="metric-label">Trading Day</div><div class="metric-value">{date.today().strftime("%A")}</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

def display_risk_management():
    st.markdown('<div class="risk-section"><h2>🧠 Risk Management</h2>', unsafe_allow_html=True)
    if 'standard_risk' not in st.session_state: st.session_state.standard_risk = 300
    if 'current_balance' not in st.session_state: st.session_state.current_balance = 2800
    if 'streak' not in st.session_state: st.session_state.streak = 5
    if 'eval_target' not in st.session_state: st.session_state.eval_target = 6000
    col1, col2, col3 = st.columns(3)
    with col1: st.session_state.current_balance = st.number_input("Current Profit ($)", value=st.session_state.current_balance, step=50, key="risk_balance")
    with col2: st.session_state.streak = st.number_input("Win/Loss Streak", value=st.session_state.streak, step=1, key="risk_streak")
    with col3: st.session_state.standard_risk = st.number_input("Standard Risk ($)", value=st.session_state.standard_risk, step=10, key="risk_standard")
    profit_loss = st.session_state.current_balance
    if profit_loss <= 0: suggested_risk, reason, risk_class = st.session_state.standard_risk / 2, "Account in drawdown. Minimum Risk.", "risk-minimum"
    elif st.session_state.streak < 0: suggested_risk, reason, risk_class = st.session_state.standard_risk / 2, f"{abs(st.session_state.streak)}-trade losing streak. Minimum Risk.", "risk-minimum"
    elif st.session_state.streak >= WIN_STREAK_THRESHOLD: suggested_risk, reason, risk_class = st.session_state.standard_risk / 2, f"{st.session_state.streak}-win streak. Defensive Risk.", "risk-defensive"
    elif profit_loss >= st.session_state.eval_target: suggested_risk, reason, risk_class = 0, "Target reached! Stop trading.", "risk-passed"
    else: suggested_risk, reason, risk_class = st.session_state.standard_risk, "Standard operating conditions.", "risk-normal"
    st.markdown(f'<div class="risk-output {risk_class}"><strong>Next Trade Risk: ${int(suggested_risk)}</strong><br><small>{reason}</small></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

def display_main_plan_card(plan, reason):
    if plan == "No Trade Day": card_class, icon, title = "no-trade", "🚫", "NO TRADE DAY"
    elif plan == "News Day Plan": card_class, icon, title = "news-day", "📰", "NEWS DAY PLAN"
    else: card_class, icon, title = "standard-day", "✅", "STANDARD DAY PLAN"
    st.markdown(f'<div class="main-plan-card {card_class}"><h1 style="font-size: 1.8rem; margin: 0;">{icon}</h1><h2 style="margin: 0.3rem 0; font-size: 1.4rem;">{title}</h2><p style="font-size: 1rem; margin: 0.5rem 0 0 0; opacity: 0.9;">{reason}</p></div>', unsafe_allow_html=True)

def display_compact_events(morning_events, afternoon_events, all_day_events):
    if not any([morning_events, afternoon_events, all_day_events]): st.info("📅 No economic events scheduled for today."); return
    tabs = st.tabs(["🌅 Morning", "🌇 Afternoon", "📅 All Day"] if all_day_events else ["🌅 Morning", "🌇 Afternoon"])
    with tabs[0]:
        if morning_events:
            for e in sorted([ev for ev in morning_events if ev['raw_time']], key=lambda x: x['raw_time']):
                impact_class = "event-high" if "High" in e['impact'] else "event-medium" if "Medium" in e['impact'] else "event-low"
                currency_class = "usd" if e['currency'] == 'USD' else ""
                st.markdown(f'<div class="event-compact {impact_class}"><div class="event-time">{e["time"]}</div><div class="event-currency {currency_class}">{e["currency"]}</div><div style="flex: 1; margin-left: 15px;">{e["name"]}</div></div>', unsafe_allow_html=True)
        else: st.markdown("*No morning events*")
    with tabs[1]:
        if afternoon_events:
            for e in sorted([ev for ev in afternoon_events if ev['raw_time']], key=lambda x: x['raw_time']):
                impact_class = "event-high" if "High" in e['impact'] else "event-medium" if "Medium" in e['impact'] else "event-low"
                currency_class = "usd" if e['currency'] == 'USD' else ""
                st.markdown(f'<div class="event-compact {impact_class}"><div class="event-time">{e["time"]}</div><div class="event-currency {currency_class}">{e["currency"]}</div><div style="flex: 1; margin-left: 15px;">{e["name"]}</div></div>', unsafe_allow_html=True)
        else: st.markdown("*No afternoon events*")
    if all_day_events and len(tabs) > 2:
        with tabs[2]:
            for e in all_day_events:
                impact_class = "event-high" if "High" in e['impact'] else "event-medium" if "Medium" in e['impact'] else "event-low"
                currency_class = "usd" if e['currency'] == 'USD' else ""
                st.markdown(f'<div class="event-compact {impact_class}"><div class="event-time">All Day</div><div class="event-currency {currency_class}">{e["currency"]}</div><div style="flex: 1; margin-left: 15px;">{e["name"]}</div></div>', unsafe_allow_html=True)

def display_action_checklist(plan):
    st.markdown('<div class="action-section"><h3>🎯 Action Items</h3>', unsafe_allow_html=True)
    if plan == "News Day Plan": actions = [("🚫", "DO NOT trade morning session"), ("📊", "Mark NY Lunch Range"), ("👀", "Wait for liquidity raid after news"), ("🎯", "Prime entry: 2:00 PM - 3:00 PM"), ("✅", "Enter on MSS + FVG confirmation")]
    elif plan == "Standard Day Plan": actions = [("📈", "Mark Previous Day PM Range"), ("🌍", "Mark London Session Range"), ("👀", "Watch NY Open Judas Swing"), ("🎯", "Prime entry: 10:00 AM - 11:00 AM"), ("✅", "Enter after sweep with MSS + FVG")]
    else: actions = [("🚫", "Stand aside completely"), ("💰", "Preserve capital"), ("📚", "Journal and review"), ("🧘", "Prepare for next trading day")]
    for emoji, text in actions: st.markdown(f'<div class="action-item"><div class="action-emoji">{emoji}</div><div>{text}</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

def display_friday_alert(plan):
    if date.today().weekday() != 4: return
    with st.expander("🎯 T.G.I.F. Setup Alert", expanded=False):
        st.info("Friday T.G.I.F. Setup might be in play - retracement back into weekly range.")
        if plan == "Standard Day Plan": st.success("**Perfect alignment:** Watch for morning Judas swing peak then target weekly retracement.")
        elif plan == "News Day Plan": st.warning("**Adjusted timing:** Look for afternoon peak formation after news.")
        else: st.error("**Observe only:** No trading today.")

def display_seasonality_analysis(symbol, target_date):
    st.markdown("### 🗓️ Weekly Seasonal Bias")
    summary_df, detailed_df = analyze_seasonal_bias(symbol=symbol, target_date_str=target_date.strftime('%Y-%m-%d'))
    if summary_df is not None:
        st.markdown(f"Historical performance for the calendar week of **{target_date.strftime('%B %d')}** for **${symbol}**.")
        st.dataframe(summary_df, use_container_width=True)
        with st.expander("Show Detailed Yearly Returns"): st.dataframe(detailed_df, use_container_width=True, height=400)
    else: st.info(f"Could not retrieve seasonal data for {symbol}.")

def display_week_view(selected_date, records):
    st.markdown("### 📅 Week Overview")
    start_of_week = selected_date - timedelta(days=selected_date.weekday())
    week_days = [start_of_week + timedelta(days=i) for i in range(5)] # Mon-Fri
    for day in week_days:
        day_events = [row for row in records if parse_date(row.get('date', '')) == day]
        plan, reason, _, _, _ = analyze_day_events(day, day_events) if day_events else ("Standard Day Plan", "No economic events scheduled", [], [], [])
        if plan == "No Trade Day": card_style, plan_emoji = "border-left: 4px solid #f44336; background: rgba(244, 67, 54, 0.1);", "🚫"
        elif plan == "News Day Plan": card_style, plan_emoji = "border-left: 4px solid #ff9800; background: rgba(255, 152, 0, 0.1);", "📰"
        else: card_style, plan_emoji = "border-left: 4px solid #4caf50; background: rgba(76, 175, 80, 0.1);", "✅"
        st.markdown(f'<div class="week-day-card" style="{card_style}"><h4>{plan_emoji} {day.strftime("%A, %B %d")} - {plan}</h4><p style="margin: 0.5rem 0; font-size: 0.9rem; opacity: 0.8;">{reason}</p></div>', unsafe_allow_html=True)
        
        # --- NEW: Fetch and Display Earnings Data for the day ---
        earnings_results = fetch_and_format_earnings(day)
        if earnings_results:
            with st.expander(f"💰 Earnings Reports for {day.strftime('%A')} ({len(earnings_results)})"):
                companies = ", ".join([item['company'] for item in earnings_results])
                st.write(companies)
        
        high_impact_events = [e for e in day_events if parse_impact(e.get('impact', '')) == 'High' or any(k.lower() in e.get('event', '').lower() for k in FORCED_HIGH_IMPACT_KEYWORDS)]
        if high_impact_events:
            with st.expander(f"🚨 High Impact Events ({len(high_impact_events)})"):
                for event in high_impact_events:
                    time_str = parse_time(event.get('time', '')).strftime('%I:%M %p') if parse_time(event.get('time', '')) else 'All Day'
                    st.markdown(f"• **{time_str}** - {event.get('currency', '')} - {event.get('event', '')}")

def display_payout_planner():
    st.markdown("### 💰 Payout Planner")
    if 'payout_balance' not in st.session_state: st.session_state.payout_balance = 10000
    if 'payout_target' not in st.session_state: st.session_state.payout_target = 15000
    if 'monthly_payout' not in st.session_state: st.session_state.monthly_payout = 2000
    col1, col2, col3 = st.columns(3)
    with col1: st.session_state.payout_balance = st.number_input("Current Balance ($)", value=st.session_state.payout_balance, step=100)
    with col2: st.session_state.payout_target = st.number_input("Next Payout Target ($)", value=st.session_state.payout_target, step=500)
    with col3: st.session_state.monthly_payout = st.number_input("Monthly Payout Goal ($)", value=st.session_state.monthly_payout, step=100)
    remaining, progress_pct = st.session_state.payout_target - st.session_state.payout_balance, (st.session_state.payout_balance / st.session_state.payout_target) * 100
    st.progress(min(progress_pct / 100, 1.0))
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Remaining to Target", f"${remaining:,.0f}")
    with col2: st.metric("Progress", f"{progress_pct:.1f}%")
    with col3: st.metric("Daily Target", f"${st.session_state.monthly_payout / 22:.0f}")

# --- MAIN APPLICATION ---
def main():
    st.title("📈 US Index Trading Plan")
    display_header_dashboard()

    if st.button("🔄 Fetch Live Data", type="primary"):
        with st.spinner("Fetching data..."):
            try:
                subprocess.run([sys.executable, "ffscraper.py"], check=True)
                upserted, modified = update_db_from_csv(SCRAPED_DATA_PATH)
                st.success(f"✅ Updated! {upserted} new, {modified} modified")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"❌ Update failed: {str(e)}")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1: selected_date = st.date_input("📅 Analysis Date", value=date.today())
    with col2: view_mode = st.selectbox("View", ["Today", "Week"], index=0)
    with col3: show_payout = st.toggle("Show Payout Planner", value=True)
    st.markdown("---")

    if selected_date.weekday() >= 5:
        st.markdown('<div class="weekend-notice"><h2>🏖️ Weekend Mode</h2><p>Markets are closed. Time to relax, review your trades, and prepare for the upcoming week!</p></div>', unsafe_allow_html=True)
        return

    df = get_events_from_db()
    if df.empty:
        st.warning("👋 No economic data found. Click **Fetch Live Data** to load current events.")
        return
    records = df.to_dict('records')

    def get_events_for(d):
        return [row for row in records if parse_date(row.get('date', '')) == d]

    if view_mode == "Today":
        display_risk_management()
        events = get_events_for(selected_date)
        plan, reason, morning, afternoon, allday = analyze_day_events(selected_date, events) if events else ("Standard Day Plan", "No economic events. Standard plan.", [], [], [])
        display_main_plan_card(plan, reason)
        display_friday_alert(plan)
        st.markdown("---")
        display_seasonality_analysis('QQQ', selected_date)
        
        col1, col2 = st.columns([1, 1])
        with col1:
            display_action_checklist(plan)
        with col2:
            st.markdown("### 📅 Today's Events")
            display_compact_events(morning, afternoon, allday)
            
            # --- NEW: Display Today's Earnings ---
            st.markdown("### 💰 Today's Earnings Reports")
            earnings_today = fetch_and_format_earnings(selected_date)
            if earnings_today:
                with st.container(height=250):
                    for item in earnings_today:
                        st.markdown(f"• **{item['company']}**")
            else:
                st.markdown("*No major earnings reports scheduled.*")

        if show_payout:
            st.markdown("---")
            display_payout_planner()
    else:
        display_week_view(selected_date, records)
        if show_payout:
            st.markdown("---")
            display_payout_planner()

if __name__ == "__main__":
    main()
