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
# Trading Plan Constants
SCRAPED_DATA_PATH = "latest_forex_data.csv"
PLANNER_DB_NAME = "DailyTradingPlanner"
PLANNER_COLLECTION_NAME = "economic_events"
MORNING_CUTOFF = time(12, 0)
AFTERNOON_NO_TRADE_START = time(13, 55)
NO_TRADE_KEYWORDS = ['FOMC Statement', 'FOMC Press Conference', 'Interest Rate Decision', 'Monetary Policy Report']
FORCED_HIGH_IMPACT_KEYWORDS = ['Powell Speaks', 'Fed Chair', 'Non-Farm', 'NFP', 'CPI', 'Consumer Price Index', 'PPI', 'Producer Price Index', 'GDP']
WIN_STREAK_THRESHOLD = 5

# Headline Fetcher Constants
HEADLINES_DB_NAME = "FinancialHeadlinesDB"
HEADLINES_COLLECTION_NAME = "financial_headlines"
FJ_HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8", "content-type": "application/json; charset=utf-8",
    "origin": "https://www.financialjuice.com", "referer": "https://www.financialjuice.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}
ENDPOINTS = {
    "Indices": "https://live.financialjuice.com/FJService.asmx/Startup?info=%22EAAAAH3X%2BtXBBdTBI65szkt%2BAvLV20qGtr0KlypTDpImciWq93l4oldNwUC0VrcW2Jzrs%2FzaZVw4ih3ztDZjoxAOJFkW3ubCdmN85AI5HRe%2BDOqUvVxLTqV7TNgMkS2dNH01%2F79eaO9ynqrp%2B5HJs5WqGRkgUJgYHKGv4fGqJZAWAEYzqorLi1u2KEBf7oV6B%2Bgvl9gTD9GVl0O8nWj7r5NioKhfZdd%2FszNaMqLaKpJROV8RF%2FmhmZ5fZipRNBW0TZtfDsJBon5aL9PnAneWN4A2s3ecI1GOoB8kyMQtzen5GNicGD26LqzvSurQMDDswt4a8FMcz4YOslPfDD%2BjYgUYE4Q%3D%22&TimeOffset=1&tabID=9&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0",
    "Bonds": "https://live.financialjuice.com/FJService.asmx/Startup?info=%22EAAAAEqM%2Fmzge7J83z2rALxsQJx5luetJ%2BgnkH23Cw2XJDl%2FNrsqaRIEiLTDBNb%2B9Vde%2F5q6FlTS%2B1oNFvX%2Bh2tFuhiHgbJqSCmoMZ1%2Bef%2BeICf3sO9uvFiDuvx3JiYZGGjMlCSIdPOV3rbPd9ENAkgdnLxY%2Bg%2BQEU887BqNnijum0c9p4p1RbhXOMGm1Wr0ReiP31G%2BJ%2B7P%2FAQpewsI4DDvqPCpCkTYSjVBbQ6QgCZl3UtGaB456tEj%2BSi3sY8LCvFjfU3wma3tW6JiM8Ir1RkMnJON8B%2FpFS9OEk1p%2BnA%2BZvd1Cc5iZFgKQv83uyOAS%2FC%2Fbp52YepwgdthI9npFCYoQ08%3D%22&TimeOffset=1&tabID=3&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0",
    "Commodities": "https://live.financialjuice.com/FJService.asmx/Startup?info=%22EAAAADtUPzfsxoQaZySeoBXGPmT%2BxISvTQ2ZAeJw1ouh9DdNO3JqJO0KBRRm05iPkk3dCrEpd4sbHS%2B6KQVlr1LFPdl0FU1JQcq4o8OGq6wXJ1M0dapfchr841WOcr%2ByydW98JKDieIm1il3V%2FtlpB5Qa0bOf5DkVWcBodx6zu0khKJ2SU5bu3qJbcjPx%2BrWigxox1LrlLUE9eB8%2BvFZ1gZe682FKcmo8KQ7fyCRg4JhQiM4y4ojcdGpXRF19vpPT9UUuD3tRCwkWzbgCrzVJ7BH3vhK8h%2F%2F%2BdLeGwz%2B338Nu0hZ1e%2B7G%2Fy%2Fhb5ZzCafBP2ZDmDyLyA%2FDpGkU7tZ7CZpGR8%3D%22&TimeOffset=1&tabID=2&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0",
    "Crypto": "https://live.financialjuice.com/FJService.asmx/Startup?info=%22EAAAAFEUasdm5ecnw12vuaTp6OKjaaRgwrFNOCvxGJSs67NqcMg%2Fyz3Sl9aQbm93gXz0q8VV%2FFfrckk%2BkKmPLhBIT0K8cn03AIVdr2zL84IveU1kmSJudc8R4u9oyjmhjL6Y2AAlHNUXw0X%2FzFUpx3yv5U%2Foweu6HVigtj8PxUlXtpWa9S%2FDxYePqFzM%2BmzoViQKljwImbnN6g6YBTmTX8YjCqHYxd5ToHA3CPuPsAZ5%2Btw%2FFdsRxydEUu3Ts3wFc7%2FMRYJFG8nXMfgPkjxjg2gu9wWSCruwGZ0VNIBEhbQqfPVFS1FvMkw4eieRARyT41v%2FljWbK9g%2F65sN0fO3tAreM1Q%3D%22&TimeOffset=1&tabID=8&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0",
    "Equities": "https://live.financialjuice.com/FJService.asmx/Startup?info=%22EAAAABoFm9azYlf8Qj2wAlNXokPGeB2tGbcxgArPkjzz0jFq1gunnXmXDo%2BMmivtkkdCkj9SpW4kGzyD%2FCdJd%2Bocd7oYY8NdkjhB%2FEIKi9ZoQTqv8W3WDoNrWTrTx8aDduZE7xmBEBCzAqBVJtTy1aMZoLnacRT0NnkY1rofOmaVX3I9Z%2Bu1tRT9jP4qu36kwYd%2BThPp9ZvUrWaN3RhDUvwQbNS6uJGYCcBPnK1XR0vbz48pl8210o%2Bm6i0SP0fggHNknVzFP1c9SyHH8bVJnaiZhlIqGkqTjhiMidzcuAgTeHJrx%2F2nwwZX8pzvDA54Pnm%2Fo5RT0eQYMZtN12j13yWu%2FzA%3D%22&TimeOffset=1&tabID=4&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0",
    "Forex": "https://live.financialjuice.com/FJService.asmx/Startup?info=%22EAAAAPQekLn2SEBDIk3zUfnktXp0E11BXJu%2F43wDvDrCl8vIEZYOhtbq3eFsbPxtLkcSOOkjoDhWl510wyhW9wih%2BXFh44j2nnMZT9y%2Bm84PNVL5y164zL0FGFMGSzKyIkVW3gYNFOR8Hym4uYHucEBY%2FiwCzeosK61wt3R4mAw6XbFrRssKlZpE6Ln%2BJDXq5wOAoGmNxGu3F2QxpoyrPbQbewwMJ6rTZG%2BFXOckJyBOFFCe78dj2VNELy3soCEkJ9Vs6Ti6uiaahyJrsSoS29FRUGazVzk38F39naPqV99DSge2U0ePif98G4n5YpPn9QAGGRJxkt7bvJmLyEf%2BZF7nH0%3D%22&TimeOffset=1&tabID=5&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0",
    "Macro": "https://live.financialjuice.com/FJService.asmx/Startup?info=%22EAAAAFMvNnhJU6T1gy0VNauw6NzUkN9OyWCeN2VCALOWci%2FeYbMj1CtdvjVUNi2w7NRP%2F2yG1mLVauun4j%2BvsDoED47Njykc%2FgdnePCIJdbzXifXQC4IQUNIgUI1%2F2cUZFv4T8Jhb4KgWXPjUpGCzdGob7zOSi%2FhOlVwbRWxRxdBTZTzKo1PbA4wTz7OcDO%2ByNTOOFJKW0YX4a0VU0946kfLse4RCSHVw9YhyZhVCQFPatMfJwvqbzvcB%2BeqOvBCLk%2BXu2%2FHuHnXh7Ab4ESaEzgMZIziCBCm0bbT0RCDj9MVTE%2BKbdXSIKWJMQegh16D18haDDx9qtxnVd0MXYkoPbml%2FCg%3D%22&TimeOffset=1&tabID=1&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0",
    "Market Moving": "https://live.financialjuice.com/FJService.asmx/Startup?info=%22EAAAAI4ZYmAf1rjepmLb8ipJWU1iQvw0uaAarVQAhywSenf44DiF46NikC62XrMQQuUMqNuMWWJCs%2F1Vbiko5Rkbzp3DfxVv7lIdhZBjaNs17T5e1XquGGOhSUVPACWc5MbCH0cEbNrp3r2TOzSI%2FdB3pvVHn7oH78Kw%2FGqYcosYhO%2BgjWmcZcidUZ6grwdpNivqa24NaxjeE%2BB0JqC%2B508s%2F6NUZcTeJJdgF6ivW0m7CGzOr5GfEllf%2F6OIH3kkmHdKEYpeVJz%2Bwn7%2BCrVZTNwbzS9sercXjKX8IXHTzvx%2F9tEciCO0V9OysMCxJOFzpIBPn1mCi6P0wqv4xCL7JViiLP4%3D%22&TimeOffset=1&tabID=10&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0"
}

# --- ENHANCED CSS STYLES ---
st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%); }
    .main-plan-card { grid-column: span 2; padding: 1rem; border-radius: 12px; text-align: center; margin: 0.5rem 0; border: 2px solid; box-shadow: 0 4px 16px rgba(0,0,0,0.3); backdrop-filter: blur(10px); }
    .main-plan-card::before { content: ''; position: absolute; top: 0; left: -100%; width: 100%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent); transition: left 0.6s cubic-bezier(0.4,0,0.2,1); }
    .main-plan-card:hover::before { left: 100%; }
    .no-trade { background: linear-gradient(135deg, rgba(244, 67, 54, 0.15), rgba(183, 28, 28, 0.08)); border-color: #f44336; color: #ffcdd2; }
    .news-day { background: linear-gradient(135deg, rgba(255, 152, 0, 0.15), rgba(239, 108, 0, 0.08)); border-color: #ff9800; color: #ffcc02; }
    .standard-day { background: linear-gradient(135deg, rgba(76, 175, 80, 0.15), rgba(56, 142, 60, 0.08)); border-color: #4caf50; color: #a5d6a7; }
    .quick-info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
    .info-card { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 1rem; text-align: center; backdrop-filter: blur(10px); transition: all 0.3s ease; }
    .info-card:hover { transform: translateY(-5px); box-shadow: 0 8px 25px rgba(0,0,0,0.3); border-color: rgba(255, 255, 255, 0.2); }
    .info-card .metric-label { color: #94a3b8; font-size: 0.85rem; font-weight: 500; margin-bottom: 8px; }
    .info-card .metric-value { color: #ffffff; font-size: 1.4rem; font-weight: 700; text-shadow: 0 2px 4px rgba(0,0,0,0.3); }
    .risk-output { padding: 0.8rem; border-radius: 8px; text-align: center; color: white; font-weight: bold; font-size: 1.1rem; margin: 10px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.2); transition: all 0.3s ease; }
    .risk-output:hover { transform: scale(1.02); }
    .risk-normal { background: linear-gradient(135deg, #3182CE, #2c5aa0); }
    .risk-defensive { background: linear-gradient(135deg, #DD6B20, #c05621); }
    .risk-minimum { background: linear-gradient(135deg, #E53E3E, #c53030); }
    .risk-passed { background: linear-gradient(135deg, #38A169, #2f855a); }
    .event-compact { display: flex; align-items: center; padding: 0.5rem 0.75rem; margin: 0.25rem 0; border-radius: 8px; background: rgba(255, 255, 255, 0.03); border-left: 4px solid; font-size: 0.9rem; }
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
    .stButton button { background: linear-gradient(135deg, #3b82f6, #1e40af); border: none; border-radius: 12px; color: white; font-weight: 600; padding: 0.75rem 2rem; transition: all 0.3s ease; box-shadow: 0 4px 16px rgba(59, 130, 246, 0.4); }
    .stButton button:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(59, 130, 246, 0.4); }
    h1 { color: #f1f5f9; text-shadow: 0 2px 4px rgba(0,0,0,0.3); }
    h2 { color: #e2e8f0; margin-bottom: 1rem; }
    h3 { color: #cbd5e1; }
    .weekend-notice { background: linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(67, 56, 202, 0.1)); border: 2px solid #6366f1; border-radius: 16px; padding: 2rem; text-align: center; color: #c7d2fe; }
    .week-day-card { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 1rem; margin: 0.5rem 0; }
</style>
""", unsafe_allow_html=True)


# --- DATABASE & UTILITY FUNCTIONS (SHARED) ---
@st.cache_resource
def init_connection():
    try:
        connection_string = st.secrets["mongo"]["connection_string"]
        client = pymongo.MongoClient(connection_string)
        client.admin.command('ping') # Test connection
        return client
    except Exception as e:
        st.error(f"Failed to connect to MongoDB. Error: {e}", icon="🔥")
        return None

# --- TIME/DATE HELPERS ---
def get_current_market_time(): return datetime.now(pytz.timezone('US/Eastern'))
def parse_date(date_str):
    try: return datetime.strptime(str(date_str).strip(), '%d/%m/%Y').date()
    except (ValueError, TypeError): return None
def time_until_market_open():
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now.time() > time(16, 0): market_open += timedelta(days=1)
    if now.weekday() >= 5: market_open += timedelta(days=(7 - now.weekday()))
    return market_open - now
def parse_time(time_str):
    if not time_str or pd.isna(time_str) or str(time_str).lower() in ['empty', '']: return None
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
def parse_headline_datetime(dt_str):
    formats = ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"]
    for fmt in formats:
        try: return datetime.strptime(dt_str, fmt)
        except (ValueError, TypeError): continue
    return None

# --- HEADLINE FETCHER FUNCTIONS ---
@st.cache_data(ttl=300)
def summarize_headline(text):
    if not text or not client: return "OpenAI client not available."
    prompt = f"You are a financial news analyst. Summarize this headline in one sentence, highlighting the market sentiment (e.g., bullish, bearish, hawkish, dovish) and naming the primary assets affected: \"{text}\""
    try:
        response = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=100, temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception as e: return f"Error generating summary: {e}"

def store_headline_in_mongodb(item, summary):
    mongo_client = init_connection()
    if not mongo_client: return
    db = mongo_client[HEADLINES_DB_NAME]
    collection = db[HEADLINES_COLLECTION_NAME]
    headline_doc = {
        "newsId": item.get("NewsID"), "title": item.get("Title"),
        "fullText": item.get("HeadlineText"), "publishedDate": parse_headline_datetime(item.get("DatePublished", "")),
        "category": item.get("Category", "Unknown"), "url": item.get("EURL"), "summary": summary,
        "lastUpdated": datetime.utcnow()
    }
    try:
        collection.update_one({"newsId": headline_doc["newsId"]}, {"$set": headline_doc}, upsert=True)
    except Exception as e: st.error(f"Failed to write headline to MongoDB: {e}")

def fetch_headlines_from_endpoint(category, url, limit=5):
    headlines = []
    try:
        response = requests.get(url, headers=FJ_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, str): data = json.loads(data)
        news_data = data.get("d", {});
        if isinstance(news_data, str): news_data = json.loads(news_data)
        for item in news_data.get("News", []):
            if isinstance(item, dict):
                item["Category"] = category
                item["ParsedDate"] = parse_headline_datetime(item.get("DatePublished", ""))
                headlines.append(item)
                if len(headlines) >= limit: break
    except Exception as e: st.toast(f"Could not fetch data for {category}: {e}", icon="⚠️")
    return headlines

def fetch_and_process_all_headlines(headlines_per_endpoint=5):
    all_headlines = []
    progress_bar = st.progress(0, text="Initializing...")
    total_endpoints = len(ENDPOINTS)
    for i, (category, url) in enumerate(ENDPOINTS.items()):
        progress_bar.progress((i + 1) / total_endpoints, text=f"Fetching {category} headlines...")
        headlines = fetch_headlines_from_endpoint(category, url, headlines_per_endpoint)
        for item in headlines:
            headline_text = item.get("HeadlineText") or item.get("Title") or ""
            summary = summarize_headline(headline_text)
            store_headline_in_mongodb(item, summary)
            all_headlines.append({**item, "Summary": summary})
    progress_bar.empty()
    all_headlines.sort(key=lambda x: x.get("ParsedDate", datetime.min) or datetime.min, reverse=True)
    return all_headlines

@st.cache_data(ttl=600)
def get_headlines_from_db(limit=50):
    client = init_connection();
    if client is None: return []
    db = client[HEADLINES_DB_NAME]
    collection = db[HEADLINES_COLLECTION_NAME]
    items = list(collection.find({}, {'_id': 0}).sort("publishedDate", -1).limit(limit))
    return items

# --- TRADING PLAN FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_earnings_data(date_str):
    url = f"https://www.earningswhispers.com/api/caldata/{date_str}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError): return None

@st.cache_data(ttl=3600)
def fetch_and_format_earnings(target_date):
    date_str = target_date.strftime('%Y%m%d')
    data = get_earnings_data(date_str)
    if data: return [{'company': item.get('company', 'N/A')} for item in data]
    return []

@st.cache_data(ttl=600)
def get_events_from_db():
    client = init_connection()
    if client is None: return pd.DataFrame()
    db = client[PLANNER_DB_NAME]
    collection = db[PLANNER_COLLECTION_NAME]
    items = list(collection.find({}, {'_id': 0}))
    return pd.DataFrame(items) if items else pd.DataFrame()

@st.cache_data(ttl=3600)
def analyze_seasonal_bias(symbol: str, target_date_str: str, lookback_years: int = 25):
    # This function remains unchanged from original script
    try:
        target_date = pd.to_datetime(target_date_str)
        data = yf.download(symbol, start=target_date - pd.DateOffset(years=lookback_years), end=datetime.now(), interval='1wk', progress=False, auto_adjust=True)
        if data.empty: return None, None
        data['Week'] = data.index.isocalendar().week
        week_data = data[data['Week'] == target_date.isocalendar().week].copy()
        if week_data.empty: return None, None
        week_data['Return'] = (week_data['Close'] - week_data['Open']) / week_data['Open']
        results = []
        for lookback in [lookback_years, 10]:
            subset = week_data.last(f'{lookback}Y')
            if subset.empty: continue
            avg_return = subset['Return'].mean()
            std_dev = subset['Return'].std()
            positive_weeks = (subset['Return'] > 0).sum()
            total_weeks = len(subset)
            percent_positive = positive_weeks / total_weeks if total_weeks > 0 else 0
            results.append({
                'Lookback': f'Last {lookback} Years', 'Seasonal Bias': get_seasonal_bias_label(avg_return, percent_positive, std_dev),
                'Avg Weekly Return': f"{avg_return:.2%}", '% Positive Weeks': f"{percent_positive:.2%}", 'Observations': f"{positive_weeks}/{total_weeks}"
            })
        return pd.DataFrame(results).set_index('Lookback'), week_data[['Return']].rename(columns={'Return': 'Weekly Return'})
    except Exception: return None, None
def get_seasonal_bias_label(avg_return: float, percent_positive: float, std_dev: float) -> str:
    # This function remains unchanged
    if pd.isna(std_dev) or std_dev == 0: std_dev = 0.01
    STRONG_RETURN, STRONG_WIN, WEAK_WIN, NEUTRAL_UP, NEUTRAL_LOW = std_dev, 0.66, 0.33, 0.55, 0.45
    if avg_return > STRONG_RETURN and percent_positive >= STRONG_WIN: return "Strongly Bullish"
    if avg_return < -STRONG_RETURN and percent_positive <= WEAK_WIN: return "Strongly Bearish"
    if avg_return > 0 and percent_positive > NEUTRAL_UP: return "Bullish"
    if avg_return < 0 and percent_positive < NEUTRAL_LOW: return "Bearish"
    return "Neutral / Inconclusive"
def analyze_day_events(target_date, events):
    # This function remains unchanged
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

# --- UI COMPONENTS ---
def display_header_dashboard():
    # This function remains unchanged
    current_time, time_to_open = get_current_market_time(), time_until_market_open()
    st.markdown('<div class="quick-info-grid">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.markdown(f'<div class="info-card"><div class="metric-label">Current ET Time</div><div class="metric-value">{current_time.strftime("%I:%M %p")}</div></div>', unsafe_allow_html=True)
    with col2:
        if time_to_open.total_seconds() > 0:
            h, rem = divmod(int(time_to_open.total_seconds()), 3600); m, _ = divmod(rem, 60)
            display, label = f"{h}h {m}m", "Time to Open"
        else: display, label = ("OPEN" if current_time.time() < time(16, 0) else "CLOSED"), "Market Status"
        st.markdown(f'<div class="info-card"><div class="metric-label">{label}</div><div class="metric-value">{display}</div></div>', unsafe_allow_html=True)
    with col3: st.markdown(f'<div class="info-card"><div class="metric-label">Current Session</div><div class="metric-value">{get_current_session(current_time)}</div></div>', unsafe_allow_html=True)
    with col4: st.markdown(f'<div class="info-card"><div class="metric-label">Trading Day</div><div class="metric-value">{date.today().strftime("%A")}</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
def get_current_session(current_time):
    # This function remains unchanged
    current = current_time.time()
    if time(2, 0) <= current < time(5, 0): return "London"
    elif time(9, 30) <= current < time(12, 0): return "NY Morning"
    elif time(12, 0) <= current < time(13, 30): return "NY Lunch"
    elif time(13, 30) <= current < time(16, 0): return "NY Afternoon"
    else: return "Pre-Market"
def display_sidebar_risk_management():
    # This function remains unchanged
    st.sidebar.header("🧠 Risk Management")

    if 'standard_risk' not in st.session_state: st.session_state.standard_risk = 300
    if 'current_balance' not in st.session_state: st.session_state.current_balance = 2800
    if 'streak' not in st.session_state: st.session_state.streak = 5
    if 'eval_target' not in st.session_state: st.session_state.eval_target = 6000

    st.session_state.current_balance = st.sidebar.number_input("Current Profit ($)", value=st.session_state.current_balance, step=50, key="risk_balance")
    st.session_state.streak = st.sidebar.number_input("Win/Loss Streak", value=st.session_state.streak, step=1, key="risk_streak")
    st.session_state.standard_risk = st.sidebar.number_input("Standard Risk ($)", value=st.session_state.standard_risk, step=10, key="risk_standard")

    profit_loss = st.session_state.current_balance
    if profit_loss <= 0: suggested_risk, reason, risk_class = st.session_state.standard_risk / 2, "Account in drawdown. Minimum Risk.", "risk-minimum"
    elif st.session_state.streak < 0: suggested_risk, reason, risk_class = st.session_state.standard_risk / 2, f"{abs(st.session_state.streak)}-trade losing streak. Minimum Risk.", "risk-minimum"
    elif st.session_state.streak >= WIN_STREAK_THRESHOLD: suggested_risk, reason, risk_class = st.session_state.standard_risk / 2, f"{st.session_state.streak}-win streak. Defensive Risk.", "risk-defensive"
    elif profit_loss >= st.session_state.eval_target: suggested_risk, reason, risk_class = 0, "Target reached! Stop trading.", "risk-passed"
    else: suggested_risk, reason, risk_class = st.session_state.standard_risk, "Standard operating conditions.", "risk-normal"

    st.sidebar.markdown(f'<div class="risk-output {risk_class}"><strong>Next Trade Risk: ${int(suggested_risk)}</strong><br><small>{reason}</small></div>', unsafe_allow_html=True)
def display_sidebar_payout_planner():
    # This function remains unchanged
    st.sidebar.header("💰 Payout Planner")
    
    if 'payout_balance' not in st.session_state: st.session_state.payout_balance = 10000
    if 'payout_target' not in st.session_state: st.session_state.payout_target = 15000
    if 'monthly_payout' not in st.session_state: st.session_state.monthly_payout = 2000
    
    st.session_state.payout_balance = st.sidebar.number_input("Current Balance ($)", value=st.session_state.payout_balance, step=100)
    st.session_state.payout_target = st.sidebar.number_input("Next Payout Target ($)", value=st.session_state.payout_target, step=500)
    st.session_state.monthly_payout = st.sidebar.number_input("Monthly Payout Goal ($)", value=st.session_state.monthly_payout, step=100)
    
    remaining = st.session_state.payout_target - st.session_state.payout_balance
    progress_pct = (st.session_state.payout_balance / st.session_state.payout_target) * 100 if st.session_state.payout_target > 0 else 0
    
    st.sidebar.progress(min(progress_pct / 100, 1.0))
    
    col1, col2, col3 = st.sidebar.columns(3)
    col1.metric("Remaining", f"${remaining:,.0f}")
    col2.metric("Progress", f"{progress_pct:.1f}%")
    col3.metric("Daily Target", f"${st.session_state.monthly_payout / 22:.0f}")
def display_main_plan_card(plan, reason):
    # This function remains unchanged
    if plan == "No Trade Day": card_class, icon, title = "no-trade", "🚫", "NO TRADE DAY"
    elif plan == "News Day Plan": card_class, icon, title = "news-day", "📰", "NEWS DAY PLAN"
    else: card_class, icon, title = "standard-day", "✅", "STANDARD DAY PLAN"
    st.markdown(f'<div class="main-plan-card {card_class}"><h1 style="font-size: 1.8rem; margin: 0;">{icon}</h1><h2 style="margin: 0.3rem 0; font-size: 1.4rem;">{title}</h2><p style="font-size: 1rem; margin: 0.5rem 0 0 0; opacity: 0.9;">{reason}</p></div>', unsafe_allow_html=True)
def display_compact_events(morning_events, afternoon_events, all_day_events):
    # This function remains unchanged
    if not any([morning_events, afternoon_events, all_day_events]): st.info("📅 No economic events scheduled for today."); return
    tabs = st.tabs(["🌅 Morning", "🌇 Afternoon", "📅 All Day"] if all_day_events else ["🌅 Morning", "🌇 Afternoon"])
    with tabs[0]:
        if morning_events:
            for e in sorted([ev for ev in morning_events if ev['raw_time']], key=lambda x: x['raw_time']):
                impact_class = "event-high" if "High" in e['impact'] else "event-medium" if "Medium" in e['impact'] else "event-low"
                st.markdown(f'<div class="event-compact {impact_class}"><div class="event-time">{e["time"]}</div><div class="event-currency { "usd" if e["currency"] == "USD" else ""}">{e["currency"]}</div><div style="flex: 1; margin-left: 15px;">{e["name"]}</div></div>', unsafe_allow_html=True)
        else: st.markdown("*No morning events*")
    with tabs[1]:
        if afternoon_events:
            for e in sorted([ev for ev in afternoon_events if ev['raw_time']], key=lambda x: x['raw_time']):
                impact_class = "event-high" if "High" in e['impact'] else "event-medium" if "Medium" in e['impact'] else "event-low"
                st.markdown(f'<div class="event-compact {impact_class}"><div class="event-time">{e["time"]}</div><div class="event-currency { "usd" if e["currency"] == "USD" else ""}">{e["currency"]}</div><div style="flex: 1; margin-left: 15px;">{e["name"]}</div></div>', unsafe_allow_html=True)
        else: st.markdown("*No afternoon events*")
def display_action_checklist(plan):
    # This function remains unchanged
    st.markdown('<div class="action-section"><h3>🎯 Action Items</h3>', unsafe_allow_html=True)
    if plan == "News Day Plan": actions = [("🚫", "DO NOT trade morning session"), ("📊", "Mark NY Lunch Range"), ("👀", "Wait for liquidity raid after news"), ("🎯", "Prime entry: 2:00 PM - 3:00 PM"), ("✅", "Enter on MSS + FVG confirmation")]
    elif plan == "Standard Day Plan": actions = [("📈", "Mark Previous Day PM Range"), ("🌍", "Mark London Session Range"), ("👀", "Watch NY Open Judas Swing"), ("🎯", "Prime entry: 10:00 AM - 11:00 AM"), ("✅", "Enter after sweep with MSS + FVG")]
    else: actions = [("🚫", "Stand aside completely"), ("💰", "Preserve capital"), ("📚", "Journal and review"), ("🧘", "Prepare for next trading day")]
    for emoji, text in actions: st.markdown(f'<div class="action-item"><div class="action-emoji">{emoji}</div><div>{text}</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
def display_seasonality_analysis(symbol, target_date):
    # This function remains unchanged
    st.markdown("### 🗓️ Weekly Seasonal Bias")
    summary_df, detailed_df = analyze_seasonal_bias(symbol=symbol, target_date_str=target_date.strftime('%Y-%m-%d'))
    if summary_df is not None:
        st.markdown(f"Historical performance for the calendar week of **{target_date.strftime('%B %d')}** for **${symbol}**.")
        st.dataframe(summary_df, use_container_width=True)
        with st.expander("Show Detailed Yearly Returns"): st.dataframe(detailed_df, use_container_width=True, height=400)
    else: st.info(f"Could not retrieve seasonal data for {symbol}.")
def display_week_view(selected_date, records):
    # This function remains unchanged
    st.markdown("### 📅 Week Overview")
    start_of_week = selected_date - timedelta(days=selected_date.weekday())
    week_days = [start_of_week + timedelta(days=i) for i in range(5)]
    for day in week_days:
        day_events = [row for row in records if parse_date(row.get('date', '')) == day]
        plan, reason, _, _, _ = analyze_day_events(day, day_events) if day_events else ("Standard Day Plan", "No economic events scheduled", [], [], [])
        if plan == "No Trade Day": card_style, emoji = "border-left: 4px solid #f44336; background: rgba(244, 67, 54, 0.1);", "🚫"
        elif plan == "News Day Plan": card_style, emoji = "border-left: 4px solid #ff9800; background: rgba(255, 152, 0, 0.1);", "📰"
        else: card_style, emoji = "border-left: 4px solid #4caf50; background: rgba(76, 175, 80, 0.1);", "✅"
        st.markdown(f'<div class="week-day-card" style="{card_style}"><h4>{emoji} {day.strftime("%A, %B %d")} - {plan}</h4><p style="margin:0.5rem 0; font-size:0.9rem; opacity:0.8;">{reason}</p></div>', unsafe_allow_html=True)
        earnings = fetch_and_format_earnings(day)
        if earnings:
            with st.expander(f"💰 Earnings Reports ({len(earnings)})"): st.write(", ".join([item['company'] for item in earnings]))
        high_impact = [e for e in day_events if parse_impact(e.get('impact', '')) == 'High' or any(k.lower() in e.get('event', '').lower() for k in FORCED_HIGH_IMPACT_KEYWORDS)]
        if high_impact:
            with st.expander(f"🚨 High Impact Events ({len(high_impact)})"):
                for event in high_impact: st.markdown(f"• **{parse_time(event.get('time', '')).strftime('%I:%M %p') if parse_time(event.get('time', '')) else 'All Day'}** - {event.get('currency', '')} - {event.get('event', '')}")

# --- NEW: HEADLINES TAB UI ---
def display_headlines_tab():
    st.header("🌍 GEO: Financial Headlines Aggregator")
    st.write("Fetches and summarizes the latest market-moving news with AI.")
    
    if st.button("📡 Fetch & Summarize Latest Headlines", type="primary"):
        with st.spinner("Fetching headlines, this may take a moment..."):
            st.session_state.headlines = fetch_and_process_all_headlines()

    # Load initial headlines from DB if not already fetched
    if 'headlines' not in st.session_state:
        st.session_state.headlines = get_headlines_from_db()

    # Display logic
    if st.session_state.get('headlines'):
        st.success(f"Displaying {len(st.session_state.headlines)} headlines.")
        st.markdown("---")
        for item in st.session_state.headlines:
            title = item.get("title", "No Title")
            summary = item.get("summary", "No summary available.")
            url = item.get("url", "")
            category = item.get("category", "N/A")
            # Handle both datetime objects and string dates from DB
            published_date = item.get("publishedDate") or item.get("ParsedDate")

            with st.container(border=True):
                st.markdown(f"##### {title}")
                st.caption(f"**Category:** `{category}` | **Published:** {published_date.strftime('%Y-%m-%d %H:%M ET') if published_date else 'N/A'}")
                st.info(f"**AI Summary:** {summary}")
                if url:
                    st.link_button("Read Full Article ↗️", url)
    else:
        st.info("No headlines loaded. Click the button to fetch the latest news.")


# --- MAIN APPLICATION ---
def main():
    """Main function to run the scraper."""
    parser = argparse.ArgumentParser(description="Scrape Forex Factory calendar.")
    parser.add_argument("--month", type=str, help="Target month (e.g. June, July). Defaults to current month.")
    parser.add_argument("--week", action="store_true", help="Only scrape current trading week (Mon-Fri).")
    parser.add_argument("--output", default="latest_forex_data.csv", help="Output CSV filename.")
    args = parser.parse_args()

    # --- REVISED LOGIC TO HANDLE MULTI-MONTH WEEKS ---

    months_to_scrape = []
    
    if args.week:
        # If --week is specified, we determine the exact month(s) to scrape.
        week_start, week_end = get_current_week_range()
        print(f"Targeting trading week: {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}")

        # Add the starting month's parameter (e.g., 'jul')
        months_to_scrape.append(week_start.strftime("%b").lower())
        
        # If the week spans two different months, add the ending month's parameter too.
        if week_start.month != week_end.month:
            print("Week spans two months. Will scrape both calendar pages.")
            months_to_scrape.append(week_end.strftime("%b").lower())

    elif args.month:
        # If a specific month is given, just use that.
        months_to_scrape.append(args.month.lower())
    else:
        # Default behavior: scrape the current month.
        months_to_scrape.append("this")

    print(f"Calendar pages to scrape: {months_to_scrape}")

    all_events = []
    driver = None
    try:
        driver = init_driver()
        
        # Loop through each required month and scrape its page
        for month_param in months_to_scrape:
            url = f"https://www.forexfactory.com/calendar?month={month_param}"
            print(f"\nScraping URL: {url}")
            
            driver.get(url)
            scroll_to_end(driver)
            
            # The week_filter flag ensures we only keep events from the target week,
            # even when scraping a full month's page.
            events_from_page = parse_table(driver, week_filter=args.week)
            all_events.extend(events_from_page)
        
        if all_events:
            # Remove potential duplicates if an event is somehow captured on both pages (unlikely but safe)
            # This is more robustly handled by converting to a list of tuples, then back to a list of dicts.
            unique_events = [dict(t) for t in {tuple(d.items()) for d in all_events}]
            # Sort events chronologically, as combining pages can mix them up
            unique_events.sort(key=lambda x: datetime.strptime(x['date'], "%d/%m/%Y"))

            save_to_csv(unique_events, args.output)
            print("\n=== Scraping completed successfully ===")
        else:
            print("\n--- No events were scraped. ---")

    except KeyboardInterrupt:
        print("\nScraping interrupted by user.")
    except Exception as e:
        print(f"\nAn unrecoverable error occurred: {str(e)}")
    finally:
        if driver:
            driver.quit()
            print("WebDriver closed successfully.")

if __name__ == "__main__":
    main()
