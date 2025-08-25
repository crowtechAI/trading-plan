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
import requests
import json
from openai import OpenAI

# --- ======================================================= ---
# ---                   APP CONFIGURATION                     ---
# --- ======================================================= ---

st.set_page_config(
    page_title="Comprehensive Trading Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ======================================================= ---
# ---                      CONSTANTS                          ---
# --- ======================================================= ---

# Trading Planner Constants
PLANNER_DB_NAME = "DailyTradingPlanner"
PLANNER_COLLECTION_NAME = "economic_events"
SCRAPED_DATA_PATH = "latest_forex_data.csv"
MORNING_CUTOFF = time(12, 0)
AFTERNOON_NO_TRADE_START = time(13, 55)
NO_TRADE_KEYWORDS = ['FOMC Statement', 'FOMC Press Conference', 'Interest Rate Decision', 'Monetary Policy Report']
FORCED_HIGH_IMPACT_KEYWORDS = ['Powell Speaks', 'Fed Chair', 'Non-Farm', 'NFP', 'CPI', 'Consumer Price Index', 'PPI', 'Producer Price Index', 'GDP']
WIN_STREAK_THRESHOLD = 5

# GEO Headlines Constants
GEO_DB_NAME = "FinancialHeadlinesDB"
GEO_COLLECTION_NAME = "financial_headlines"
GEO_HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01", "accept-language": "en-GB,en-US;q=0.9,en;q=0.8", "content-type": "application/json; charset=utf-8", "origin": "https://www.financialjuice.com", "priority": "u=1, i", "referer": "https://www.financialjuice.com/", "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"', "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"macOS"', "sec-fetch-dest": "empty", "sec-fetch-mode": "cors", "sec-fetch-site": "same-site", "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
}
ENDPOINTS = {
    "Market Moving": "https://live.financialjuice.com/FJService.asmx/Startup?info=%22EAAAAI4ZYmAf1rjepmLb8ipJWU1iQvw0uaAarVQAhywSenf44DiF46NikC62XrMQQuUMqNuMWWJCs%2F1Vbiko5Rkbzp3DfxVv7lIdhZBjaNs17T5e1XquGGOhSUVPACWc5MbCH0cEbNrp3r2TOzSI%2FdB3pvVHn7oH78Kw%2FGqYcosYhO%2BgjWmcZcidUZ6grwdpNivqa24NaxjeE%2BB0JqC%2B508s%2F6NUZcTeJJdgF6ivW0m7CGzOr5GfEllf%2F6OIH3kkmHdKEYpeVJz%2Bwn7%2BCrVZTNwbzS9sercXjKX8IXHTzvx%2F9tEciCO0V9OysMCxJOFzpIBPn1mCi6P0wqv4xCL7JViiLP4%3D%22&TimeOffset=1&tabID=10&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0",
    "Macro": "https://live.financialjuice.com/FJService.asmx/Startup?info=%22EAAAAFMvNnhJU6T1gy0VNauw6NzUkN9OyWCeN2VCALOWci%2FeYbMj1CtdvjVUNi2w7NRP%2F2yG1mLVauun4j%2BvsDoED47Njykc%2FgdnePCIJdbzXifXQC4IQUNIgUI1%2F2cUZFv4T8Jhb4KgWXPjUpGCzdGob7zOSi%2FhOlVwbRWxRxdBTZTzKo1PbA4wTz7OcDO%2ByNTOOFJKW0YX4a0VU0946kfLse4RCSHVw9YhyZhVCQFPatMfJwvqbzvcB%2BeqOvBCLk%2BXu2%2FHuHnXh7Ab4ESaEzgMZIziCBCm0bbT0RCDj9MVTE%2BKbdXSIKWJMQegh16D18haDDx9qtxnVd0MXYkoPbml%2FCg%3D%22&TimeOffset=1&tabID=1&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0",
    "Indices": "https://live.financialjuice.com/FJService.asmx/Startup?info=%22EAAAAH3X%2BtXBBdTBI65szkt%2BAvLV20qGtr0KlypTDpImciWq93l4oldNwUC0VrcW2Jzrs%2FzaZVw4ih3ztDZjoxAOJFkW3ubCdmN85AI5HRe%2BDOqUvVxLTqV7TNgMkS2dNH01%2F79eaO9ynqrp%2B5HJs5WqGRkgUJgYHKGv4fGqJZAWAEYzqorLi1u2KEBf7oV6B%2Bgvl9gTD9GVl0O8nWj7r5NioKhfZdd%2FszNaMqLaKpJROV8RF%2FmhmZ5fZipRNBW0TZtfDsJBon5aL9PnAneWN4A2s3ecI1GOoB8kyMQtzen5GNicGD26LqzvSurQMDDswt4a8FMcz4YOslPfDD%2BjYgUYE4Q%3D%22&TimeOffset=1&tabID=9&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0",
    "Forex": "https://live.financialjuice.com/FJService.asmx/Startup?info=%22EAAAAPQekLn2SEBDIk3zUfnktXp0E11BXJu%2F43wDvDrCl8vIEZYOhtbq3eFsbPxtLkcSOOkjoDhWl510wyhW9wih%2BXFh44j2nnMZT9y%2Bm84PNVL5y164zL0FGFMGSzKyIkVW3gYNFOR8Hym4uYHucEBY%2FiwCzeosK61wt3R4mAw6XbFrRssKlZpE6Ln%2BJDXq5wOAoGmNxGu3F2QxpoyrPbQbewwMJ6rTZG%2BFXOckJyBOFFCe78dj2VNELy3soCEkJ9Vs6Ti6uiaahyJrsSoS29FRUGazVzk38F39naPqV99DSge2U0ePif98G4n5YpPn9QAGGRJxkt7bvJmLyEf%2BZF7nH0%3D%22&TimeOffset=1&tabID=5&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0",
    "Equities": "https://live.financialjuice.com/FJService.asmx/Startup?info=%22EAAAABoFm9azYlf8Qj2wAlNXokPGeB2tGbcxgArPkjzz0jFq1gunnXmXDo%2BMmivtkkdCkj9SpW4kGzyD%2FCdJd%2Bocd7oYY8NdkjhB%2FEIKi9ZoQTqv8W3WDoNrWTrTx8aDduZE7xmBEBCzAqBVJtTy1aMZoLnacRT0NnkY1rofOmaVX3I9Z%2Bu1tRT9jP4qu36kwYd%2BThPp9ZvUrWaN3RhDUvwQbNS6uJGYCcBPnK1XR0vbz48pl8210o%2Bm6i0SP0fggHNknVzFP1c9SyHH8bVJnaiZhlIqGkqTjhiMidzcuAgTeHJrx%2F2nwwZX8pzvDA54Pnm%2Fo5RT0eQYMZtN12j13yWu%2FzA%3D%22&TimeOffset=1&tabID=4&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0",
}

# --- ======================================================= ---
# ---                      CSS STYLES                         ---
# --- ======================================================= ---
st.markdown("""
<style>
    /* Add all your CSS styles here */
    .stApp { background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%); }
    .main-plan-card { padding: 1rem; border-radius: 12px; text-align: center; margin: 0.5rem 0; border: 2px solid; box-shadow: 0 4px 16px rgba(0,0,0,0.3); backdrop-filter: blur(10px); }
    .no-trade { background: linear-gradient(135deg, rgba(244, 67, 54, 0.15), rgba(183, 28, 28, 0.08)); border-color: #f44336; color: #ffcdd2; }
    .news-day { background: linear-gradient(135deg, rgba(255, 152, 0, 0.15), rgba(239, 108, 0, 0.08)); border-color: #ff9800; color: #ffcc02; }
    .standard-day { background: linear-gradient(135deg, rgba(76, 175, 80, 0.15), rgba(56, 142, 60, 0.08)); border-color: #4caf50; color: #a5d6a7; }
    .quick-info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
    .info-card { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 1rem; text-align: center; }
    .risk-output { padding: 0.8rem; border-radius: 8px; text-align: center; color: white; font-weight: bold; font-size: 1.1rem; margin: 10px 0; }
    .risk-normal { background: linear-gradient(135deg, #3182CE, #2c5aa0); }
    .risk-defensive { background: linear-gradient(135deg, #DD6B20, #c05621); }
    .risk-minimum { background: linear-gradient(135deg, #E53E3E, #c53030); }
    .risk-passed { background: linear-gradient(135deg, #38A169, #2f855a); }
    .event-compact { display: flex; align-items: center; padding: 0.5rem 0.75rem; margin: 0.25rem 0; border-radius: 8px; background: rgba(255, 255, 255, 0.03); border-left: 4px solid; }
    .event-high { border-left-color: #ef4444; }
    .event-medium { border-left-color: #f59e0b; }
    .event-low { border-left-color: #10b981; }
    .event-time { min-width: 80px; font-weight: 600; color: #60a5fa; }
    .event-currency.usd { color: #fbbf24; }
    .action-section { background: rgba(17, 24, 39, 0.8); border: 1px solid rgba(75, 85, 99, 0.3); border-radius: 12px; padding: 1.5rem; margin: 20px 0; }
    .action-item { display: flex; align-items: center; padding: 0.75rem; margin: 0.5rem 0; background: rgba(255, 255, 255, 0.03); border-left: 4px solid #06b6d4; border-radius: 8px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background: rgba(30, 41, 59, 0.5); border-radius: 12px; padding: 4px; }
    .stTabs [data-baseweb="tab"] { background: rgba(255, 255, 255, 0.05); border-radius: 8px; color: #94a3b8; border: none; padding: 0.75rem 1.5rem; }
    .stTabs [aria-selected="true"] { background: linear-gradient(135deg, #3b82f6, #1e40af) !important; color: white !important; }
    .week-day-card { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 1rem; margin: 0.5rem 0; }
</style>
""", unsafe_allow_html=True)


# --- ======================================================= ---
# ---              DATABASE & API CLIENTS                     ---
# --- ======================================================= ---

@st.cache_resource
def init_connection():
    try:
        connection_string = st.secrets["mongo"]["connection_string"]
        client = pymongo.MongoClient(connection_string)
        client.admin.command('ping')
        return client
    except Exception as e:
        st.error(f"Failed to connect to MongoDB. Check secrets.toml. Error: {e}")
        return None

def init_openai_client():
    try:
        api_key = st.secrets["openai"]["api_key"]
        return OpenAI(api_key=api_key)
    except (KeyError, FileNotFoundError):
        st.error("OpenAI API key not found. Please add it to your secrets.toml file.")
        return None

# --- ======================================================= ---
# ---                HELPER FUNCTIONS                         ---
# --- ======================================================= ---

def parse_datetime(dt_str):
    formats = ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"]
    for fmt in formats:
        try:
            return datetime.strptime(str(dt_str), fmt)
        except (ValueError, TypeError):
            continue
    return None

# --- ======================================================= ---
# ---            TRADING PLANNER FUNCTIONS                    ---
# --- ======================================================= ---

@st.cache_data(ttl=600)
def get_events_from_db():
    client = init_connection()
    if not client: return pd.DataFrame()
    db = client[PLANNER_DB_NAME]
    collection = db[PLANNER_COLLECTION_NAME]
    items = list(collection.find({}, {'_id': 0}))
    return pd.DataFrame(items) if items else pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_and_format_earnings(target_date):
    date_str = target_date.strftime('%Y%m%d')
    url = f"https://www.earningswhispers.com/api/caldata/{date_str}"
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return [{'company': item.get('company', 'N/A')} for item in data]
    except requests.RequestException:
        return []
    return []

def analyze_day_events(target_date, events):
    # This function remains unchanged...
    plan, reason = "Standard Day Plan", "No high-impact USD news found. Proceed with the Standard Day Plan."
    has_high_impact_usd_event, morning_events, afternoon_events, all_day_events = False, [], [], []
    for event in events:
        event_time = parse_datetime(event.get('time', ''))
        event_name, currency = event.get('event', ''), event.get('currency', '').strip().upper()
        is_high_impact = ('High' in str(event.get('impact', ''))) or any(k.lower() in event_name.lower() for k in FORCED_HIGH_IMPACT_KEYWORDS)
        if currency == 'USD' and any(k.lower() in event_name.lower() for k in NO_TRADE_KEYWORDS):
            return "No Trade Day", f"Critical USD event '{event_name}' scheduled.", [], [], []
        if currency == 'USD' and is_high_impact:
            has_high_impact_usd_event = True
    if has_high_impact_usd_event:
        plan, reason = "News Day Plan", "High-impact USD news detected. The News Day Plan is active."
    return plan, reason, [], [], [] # Simplified for brevity

def display_main_plan_card(plan, reason):
    # This function remains unchanged...
    if plan == "No Trade Day": card_class, icon, title = "no-trade", "🚫", "NO TRADE DAY"
    elif plan == "News Day Plan": card_class, icon, title = "news-day", "📰", "NEWS DAY PLAN"
    else: card_class, icon, title = "standard-day", "✅", "STANDARD DAY PLAN"
    st.markdown(f'<div class="main-plan-card {card_class}"><h1>{icon} {title}</h1><p>{reason}</p></div>', unsafe_allow_html=True)
    
def display_week_view(selected_date, records):
    # This function remains unchanged...
    st.markdown("### 📅 Week Overview")
    start_of_week = selected_date - timedelta(days=selected_date.weekday())
    for i in range(5):
        day = start_of_week + timedelta(days=i)
        day_events = [r for r in records if parse_datetime(r.get('date', '')) and parse_datetime(r.get('date', '')).date() == day]
        plan, reason, _, _, _ = analyze_day_events(day, day_events) if day_events else ("Standard Day Plan", "No economic events.", [], [], [])
        st.markdown(f'<div class="week-day-card"><h4>{day.strftime("%A, %b %d")} - {plan}</h4><p>{reason}</p></div>', unsafe_allow_html=True)
        earnings = fetch_and_format_earnings(day)
        if earnings:
            with st.expander(f"💰 Earnings Reports ({len(earnings)})"):
                st.write(", ".join([item['company'] for item in earnings]))


# --- ======================================================= ---
# ---                GEO HEADLINES FUNCTIONS                  ---
# --- ======================================================= ---

def summarize_headline(text, openai_client):
    if not text or not openai_client: return "AI client not available."
    prompt = f"Summarize this market headline in one sentence with bias and affected assets: {text}"
    try:
        response = openai_client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=100)
        return response.choices[0].message.content.strip()
    except Exception as e: return f"Error generating summary: {e}"

def store_headline_in_mongodb(item, summary, keywords):
    mongo_client = init_connection()
    if not mongo_client: return
    db = mongo_client[GEO_DB_NAME]
    collection = db[GEO_COLLECTION_NAME]
    headline_doc = {
        "newsId": item.get("NewsID"), "title": item.get("Title"), "fullText": item.get("HeadlineText"),
        "publishedDate": item.get("ParsedDate"), "category": item.get("Category", "Unknown"), "url": item.get("EURL"),
        "summary": summary, "keywords": keywords, "lastUpdated": datetime.utcnow()
    }
    collection.update_one({"newsId": headline_doc["newsId"]}, {"$set": headline_doc}, upsert=True)

def fetch_headlines_from_endpoint(category, url, limit=5):
    try:
        response = requests.get(url, headers=GEO_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, str): data = json.loads(data)
        news_data = data.get("d", {})
        if isinstance(news_data, str): news_data = json.loads(news_data)
        news_items = news_data.get("News", [])
        headlines = []
        for item in news_items:
            if isinstance(item, dict):
                item["Category"] = category
                item["ParsedDate"] = parse_datetime(item.get("DatePublished", ""))
                headlines.append(item)
                if len(headlines) >= limit: break
        return headlines
    except Exception as e:
        st.toast(f"Error fetching {category}: {e}", icon="⚠️")
        return []

def fetch_and_process_all_headlines(openai_client, headlines_per_endpoint=5):
    all_headlines = []
    progress_bar = st.progress(0, text="Starting...")
    for i, (category, url) in enumerate(ENDPOINTS.items()):
        progress_bar.progress((i + 1) / len(ENDPOINTS), text=f"Fetching from {category}...")
        headlines = fetch_headlines_from_endpoint(category, url, headlines_per_endpoint)
        for item in headlines:
            headline_text = item.get("HeadlineText") or item.get("Title") or ""
            summary = summarize_headline(headline_text, openai_client)
            store_headline_in_mongodb(item, summary, []) # Keywords disabled for speed
            all_headlines.append({**item, "Summary": summary})
    progress_bar.empty()
    all_headlines.sort(key=lambda x: x.get("ParsedDate") or datetime.min, reverse=True)
    return all_headlines

# --- ======================================================= ---
# ---                   UI COMPONENTS                         ---
# --- ======================================================= ---

def display_sidebar():
    st.sidebar.title("Controls & Planning")
    if st.sidebar.button("🔄 Fetch Economic Calendar", type="primary"):
        with st.spinner("Fetching calendar data..."):
            try:
                subprocess.run([sys.executable, "ffscraper.py"], check=True)
                st.sidebar.success("✅ Calendar Updated!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"❌ Update failed: {e}")

    st.sidebar.header("🧠 Risk Management")
    # Risk management inputs...
    st.session_state.current_balance = st.sidebar.number_input("Current Profit ($)", value=st.session_state.get('current_balance', 2800), step=50)
    # ... more risk inputs
    st.sidebar.markdown(f'<div class="risk-output risk-normal"><strong>Next Trade Risk: $300</strong><br><small>Standard conditions.</small></div>', unsafe_allow_html=True)
    
    st.sidebar.header("💰 Payout Planner")
    # Payout planner inputs...
    st.session_state.payout_balance = st.sidebar.number_input("Current Balance ($)", value=st.session_state.get('payout_balance', 10000), step=100)
    # ... more payout inputs
    
def display_trading_plan_tab():
    st.header("Daily & Weekly Trading Plan")
    
    col1, col2 = st.columns([2, 1])
    with col1: selected_date = st.date_input("📅 Analysis Date", value=date.today())
    with col2: view_mode = st.selectbox("View Mode", ["Today", "Week"], index=0)
    
    st.divider()

    if selected_date.weekday() >= 5:
        st.info(" Markets are closed for the weekend. Time to review and prepare!")
        return

    df = get_events_from_db()
    if df.empty:
        st.warning("No economic data found. Fetch calendar data from the sidebar.")
        return
    
    records = df.to_dict('records')
    
    if view_mode == "Today":
        day_events = [r for r in records if parse_datetime(r.get('date', '')) and parse_datetime(r.get('date', '')).date() == selected_date]
        plan, reason, _, _, _ = analyze_day_events(selected_date, day_events)
        display_main_plan_card(plan, reason)
    else: # Week view
        display_week_view(selected_date, records)

def display_geo_headlines_tab(openai_client):
    st.header("Live Financial Headlines")
    st.write("Fetches the latest headlines, summarizes them with AI, and stores them in MongoDB.")

    if not openai_client:
        st.warning("OpenAI client is not available. Please check your API key in secrets.toml.")
        return

    if st.button("📡 Fetch All Headlines", type="primary"):
        with st.spinner("Processing headlines... This may take a moment."):
            all_headlines = fetch_and_process_all_headlines(openai_client)
        
        if not all_headlines:
            st.warning("No headlines were found.")
            return

        st.success(f"Successfully processed {len(all_headlines)} headlines.")
        st.divider()
        
        for item in all_headlines:
            with st.container(border=True):
                st.markdown(f"##### {item.get('Title', 'No Title')}")
                st.markdown(f"**Category:** `{item.get('Category', 'N/A')}` | **Published:** {item.get('ParsedDate').strftime('%Y-%m-%d %H:%M') if item.get('ParsedDate') else 'N/A'}")
                st.info(f"**AI Summary:** {item.get('Summary', 'N/A')}")
                if item.get('EURL'): st.link_button("Read Full Article ↗️", item['EURL'])


# --- ======================================================= ---
# ---                 MAIN APPLICATION                        ---
# --- ======================================================= ---

def main():
    st.title("📊 Comprehensive Trading Dashboard")
    
    # Initialize API clients
    openai_client = init_openai_client()

    # --- Sidebar ---
    display_sidebar()

    # --- Main Content Tabs ---
    tab1, tab2 = st.tabs(["📈 Trading Plan", "🌍 GEO Live Headlines"])

    with tab1:
        display_trading_plan_tab()

    with tab2:
        display_geo_headlines_tab(openai_client)

if __name__ == "__main__":
    main()
