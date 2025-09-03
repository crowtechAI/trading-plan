import streamlit as st
import pandas as pd
import yfinance as yf
import csv
from datetime import datetime, time, date, timedelta
import pytz
import requests
import json
import pymongo
from openai import OpenAI

# --- CONFIGURATION ---
st.set_page_config(
    page_title="US Index Trading Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize OpenAI client
try:
    client = OpenAI(api_key=st.secrets["openai"]["api_key"])
except (KeyError, FileNotFoundError):
    st.error("OpenAI API key not found. Please add it to your Streamlit secrets.", icon="🚨")
    client = None

# --- CONSTANTS ---
SCRAPED_DATA_PATH = "latest_forex_data.csv"
PLANNER_DB_NAME = "DailyTradingPlanner"
PLANNER_COLLECTION_NAME = "economic_events"
MORNING_CUTOFF = time(12, 0)
AFTERNOON_NO_TRADE_START = time(13, 55)
NO_TRADE_KEYWORDS = ['FOMC Statement', 'FOMC Press Conference', 'Interest Rate Decision', 'Monetary Policy Report']
FORCED_HIGH_IMPACT_KEYWORDS = ['Powell Speaks', 'Fed Chair', 'Non-Farm', 'NFP', 'CPI', 'Consumer Price Index', 'PPI', 'Producer Price Index', 'GDP']
WIN_STREAK_THRESHOLD = 5

HEADLINES_DB_NAME = "FinancialHeadlinesDB"
HEADLINES_COLLECTION_NAME = "financial_headlines"
FJ_HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "content-type": "application/json; charset=utf-8",
    "origin": "https://www.financialjuice.com",
    "referer": "https://www.financialjuice.com/",
    "user-agent": "Mozilla/5.0"
}
ENDPOINTS = {
    "Market Moving": "https://live.financialjuice.com/FJService.asmx/Startup?info=market_moving",
    "Macro": "https://live.financialjuice.com/FJService.asmx/Startup?info=macro",
    "Forex": "https://live.financialjuice.com/FJService.asmx/Startup?info=forex",
    "Indices": "https://live.financialjuice.com/FJService.asmx/Startup?info=indices"
}

# --- CSS STYLES ---
st.markdown("""
<style>
/* Your enhanced CSS here (from the previous snippet) */
</style>
""", unsafe_allow_html=True)

# --- DATABASE CONNECTION ---
@st.cache_resource
def init_connection():
    try:
        connection_string = st.secrets["mongo"]["connection_string"]
        client = pymongo.MongoClient(connection_string)
        client.admin.command('ping')
        return client
    except Exception as e:
        st.error(f"Failed to connect to MongoDB: {e}")
        return None

# --- TIME HELPERS ---
def get_current_market_time(): return datetime.now(pytz.timezone('US/Eastern'))
def parse_date(date_str):
    try: return datetime.strptime(str(date_str).strip(), '%d/%m/%Y').date()
    except (ValueError, TypeError): return None
def parse_time(time_str):
    if not time_str or pd.isna(time_str): return None
    for fmt in ('%I:%M%p', '%I:%M %p', '%H:%M'):
        try: return datetime.strptime(str(time_str).strip(), fmt).time()
        except ValueError: continue
    return None
def parse_impact(impact_str):
    if not impact_str or pd.isna(impact_str): return "Low"
    lower = str(impact_str).lower()
    if 'high' in lower: return "High"
    if 'medium' in lower: return "Medium"
    return "Low"

# --- HEADLINES FUNCTIONS ---
@st.cache_data(ttl=300)
def summarize_headline(text):
    if not text or not client: return "OpenAI client not available."
    prompt = f"Summarize this financial headline in one sentence with sentiment and primary affected assets: \"{text}\""
    try:
        response = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=100, temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception as e: return f"Error: {e}"

def store_headline_in_mongodb(item, summary):
    mongo_client = init_connection()
    if not mongo_client: return
    db = mongo_client[HEADLINES_DB_NAME]
    collection = db[HEADLINES_COLLECTION_NAME]
    headline_doc = {
        "newsId": item.get("NewsID"), "title": item.get("Title"),
        "fullText": item.get("HeadlineText"), "publishedDate": item.get("DatePublished"),
        "category": item.get("Category", "Unknown"), "url": item.get("EURL"), "summary": summary,
        "lastUpdated": datetime.utcnow()
    }
    try:
        collection.update_one({"newsId": headline_doc["newsId"]}, {"$set": headline_doc}, upsert=True)
    except: pass

def fetch_headlines_from_endpoint(category, url, limit=5):
    headlines = []
    try:
        response = requests.get(url, headers=FJ_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, str): data = json.loads(data)
        news_data = data.get("d", {})
        if isinstance(news_data, str): news_data = json.loads(news_data)
        for item in news_data.get("News", []):
            item["Category"] = category
            headlines.append(item)
            if len(headlines) >= limit: break
    except: pass
    return headlines

def fetch_and_process_all_headlines(headlines_per_endpoint=5):
    all_headlines = []
    for category, url in ENDPOINTS.items():
        headlines = fetch_headlines_from_endpoint(category, url, headlines_per_endpoint)
        for item in headlines:
            summary = summarize_headline(item.get("HeadlineText") or item.get("Title") or "")
            store_headline_in_mongodb(item, summary)
            all_headlines.append({**item, "Summary": summary})
    return all_headlines

@st.cache_data(ttl=600)
def get_headlines_from_db(limit=50):
    client = init_connection()
    if client is None: return []
    db = client[HEADLINES_DB_NAME]
    collection = db[HEADLINES_COLLECTION_NAME]
    return list(collection.find({}, {'_id': 0}).sort("publishedDate", -1).limit(limit))

# --- TRADING PLAN FUNCTIONS ---
def get_current_session(current_time):
    current = current_time.time()
    if time(2, 0) <= current < time(5, 0): return "London"
    elif time(9, 30) <= current < time(12, 0): return "NY Morning"
    elif time(12, 0) <= current < time(13, 30): return "NY Lunch"
    elif time(13, 30) <= current < time(16, 0): return "NY Afternoon"
    else: return "Pre-Market"

# Analyze day events (simplified)
def analyze_day_events(target_date, events):
    plan, reason = "Standard Day Plan", "No high-impact USD news found."
    for event in events:
        event_name = event.get('event', '')
        currency = event.get('currency', '').upper()
        if currency == 'USD' and parse_impact(event.get('impact', '')) == 'High':
            plan, reason = "News Day Plan", f"High-impact USD news: {event_name}"
    return plan, reason

# --- UI COMPONENTS ---
def display_header_dashboard():
    current_time = get_current_market_time()
    st.markdown(f"**Current ET Time:** {current_time.strftime('%I:%M %p')}  |  **Session:** {get_current_session(current_time)}")

def display_headlines_tab():
    st.header("🌍 Financial Headlines")
    if st.button("📡 Fetch & Summarize Latest Headlines"):
        with st.spinner("Fetching..."):
            headlines = fetch_and_process_all_headlines()
            st.session_state.headlines = headlines
    headlines = st.session_state.get('headlines', get_headlines_from_db(20))
    for h in headlines:
        st.markdown(f"**{h.get('title', '')}**  \n{h.get('Summary', '')}  \n[{h.get('url', '#')}]")

# --- MAIN APP ---
display_header_dashboard()

tab1, tab2 = st.tabs(["📊 Trading Plan", "📰 Headlines"])
with tab1:
