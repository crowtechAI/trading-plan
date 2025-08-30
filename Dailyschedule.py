# Enhanced functions to handle month-end issues in your main dashboard

import streamlit as st
import pandas as pd
import subprocess
import sys
from datetime import datetime, date, timedelta
import time
import requests

# Enhanced data fetching with better error handling
def enhanced_fetch_economic_data():
    """
    Improved economic data fetching with better error handling and diagnostics
    """
    if st.sidebar.button("🔄 Fetch Economic Data", type="primary"):
        with st.spinner("Fetching data from Forex Factory..."):
            try:
                # Show current date context
                today = date.today()
                st.sidebar.info(f"📅 Fetching events from {today} onwards")
                
                # Check if we're near month-end (last 3 days of month)
                next_month = today.replace(day=28) + timedelta(days=4)
                month_end = next_month - timedelta(days=next_month.day)
                days_to_month_end = (month_end - today).days
                
                if days_to_month_end <= 3:
                    st.sidebar.warning("⚠️ Near month-end - this may take longer than usual")
                
                # Run the scraper with detailed output capture
                result = subprocess.run(
                    [sys.executable, "ffscraper.py"], 
                    check=False,  # Don't raise exception on non-zero exit
                    capture_output=True, 
                    text=True,
                    timeout=120  # 2-minute timeout
                )
                
                # Display detailed results
                if result.returncode == 0:
                    st.sidebar.success("✅ Economic Data Fetched!")
                    if result.stdout:
                        with st.sidebar.expander("📊 Scraper Output"):
                            st.code(result.stdout)
                else:
                    st.sidebar.error(f"❌ Scraper failed (Exit code: {result.returncode})")
                    if result.stderr:
                        with st.sidebar.expander("🔍 Error Details"):
                            st.code(result.stderr)
                    if result.stdout:
                        with st.sidebar.expander("📊 Partial Output"):
                            st.code(result.stdout)
                
                # Clear cache and reload regardless of exit code
                st.cache_data.clear()
                time.sleep(1)  # Brief pause before rerun
                st.rerun()
                
            except subprocess.TimeoutExpired:
                st.sidebar.error("⏱️ Scraper timed out - Forex Factory may be slow")
            except FileNotFoundError:
                st.sidebar.error("📁 ffscraper.py not found - check file location")
            except Exception as e:
                st.sidebar.error(f"💥 Unexpected error: {e}")

# Enhanced data validation
@st.cache_data(ttl=300)  # Cache for 5 minutes only
def get_events_from_db_enhanced():
    """
    Enhanced version with better error handling and data validation
    """
    client = init_connection()
    if client is None:
        return pd.DataFrame(), "No database connection"
    
    try:
        db = client[PLANNER_DB_NAME]
        collection = db[PLANNER_COLLECTION_NAME]
        
        # Get document count first
        doc_count = collection.count_documents({})
        
        if doc_count == 0:
            return pd.DataFrame(), f"Database connected but no events found (0 documents)"
        
        # Fetch with date filter to ensure we get relevant events
        today = datetime.now()
        week_ago = today - timedelta(days=7)
        week_ahead = today + timedelta(days=14)
        
        # Try to find events with recent dates
        recent_query = {
            "$or": [
                {"date": {"$exists": True}},  # Any document with date field
                {"_id": {"$exists": True}}     # Fallback to any document
            ]
        }
        
        items = list(collection.find(recent_query, {'_id': 0}).limit(1000))
        
        if not items:
            return pd.DataFrame(), f"Database has {doc_count} documents but query returned no results"
        
        df = pd.DataFrame(items)
        
        # Data quality checks
        quality_info = []
        if 'date' in df.columns:
            valid_dates = df['date'].notna().sum()
            quality_info.append(f"{valid_dates}/{len(df)} events have valid dates")
        
        if 'event' in df.columns:
            valid_events = df['event'].notna().sum()
            quality_info.append(f"{valid_events}/{len(df)} events have names")
        
        quality_msg = f"Loaded {len(df)} events. " + " | ".join(quality_info)
        
        return df, quality_msg
        
    except Exception as e:
        return pd.DataFrame(), f"Database error: {str(e)}"

# Enhanced display function with diagnostics
def display_enhanced_data_status():
    """
    Display detailed information about data status and quality
    """
    df, status_msg = get_events_from_db_enhanced()
    
    # Create an info box with detailed status
    if df.empty:
        st.warning(f"📭 {status_msg}")
        
        # Provide actionable guidance
        st.markdown("""
        **Possible solutions:**
        1. 🔄 Click **Fetch Economic Data** to scrape fresh data
        2. 🕐 If it's month-end, try again in a few hours
        3. 🔍 Check the error details in the sidebar after fetching
        4. 💾 Verify your MongoDB connection is working
        """)
        
        # Quick database test
        if st.button("🏥 Test Database Connection"):
            client = init_connection()
            if client:
                try:
                    # Test basic connectivity
                    client.admin.command('ping')
                    st.success("✅ Database connection is working")
                    
                    # Check collections
                    db = client[PLANNER_DB_NAME]
                    collections = db.list_collection_names()
                    st.info(f"📂 Available collections: {collections}")
                    
                    # Check specific collection
                    if PLANNER_COLLECTION_NAME in collections:
                        collection = db[PLANNER_COLLECTION_NAME]
                        sample_doc = collection.find_one()
                        if sample_doc:
                            st.success("✅ Economic events collection exists with data")
                            with st.expander("📄 Sample Document"):
                                st.json(sample_doc)
                        else:
                            st.warning("⚠️ Collection exists but is empty")
                    else:
                        st.warning(f"⚠️ Collection '{PLANNER_COLLECTION_NAME}' does not exist")
                        
                except Exception as e:
                    st.error(f"❌ Database test failed: {e}")
            else:
                st.error("❌ Cannot connect to database")
    else:
        st.success(f"✅ {status_msg}")
        
        # Show data freshness
        if 'date' in df.columns:
            try:
                # Parse dates and find the range
                df['parsed_date'] = df['date'].apply(parse_date)
                valid_dates = df['parsed_date'].dropna()
                
                if not valid_dates.empty:
                    min_date = valid_dates.min()
                    max_date = valid_dates.max()
                    today = date.today()
                    
                    # Check data freshness
                    if max_date >= today:
                        days_ahead = (max_date - today).days
                        st.info(f"📅 Events available through {max_date} ({days_ahead} days ahead)")
                    else:
                        days_behind = (today - max_date).days
                        st.warning(f"⚠️ Data is {days_behind} days old (latest: {max_date})")
                        
            except Exception as e:
                st.warning(f"⚠️ Could not parse date information: {e}")

# Enhanced month-end detection
def is_month_end_period():
    """
    Detect if we're in a problematic month-end period
    """
    today = date.today()
    
    # Last 3 days of current month
    next_month = today.replace(day=28) + timedelta(days=4)
    month_end = next_month - timedelta(days=next_month.day)
    days_to_month_end = (month_end - today).days
    
    # First 2 days of new month
    first_of_month = today.replace(day=1)
    days_from_month_start = (today - first_of_month).days
    
    return days_to_month_end <= 3 or days_from_month_start <= 2

def display_month_end_warning():
    """
    Display special warning during problematic periods
    """
    if is_month_end_period():
        st.warning("""
        🗓️ **Month-End Period Notice**
        
        You're currently in a month-end transition period. This can cause:
        - Slower data fetching from financial websites
        - Temporary API token expiration issues  
        - Increased anti-bot measures on financial sites
        
        If data fetching fails, try again in a few hours or use cached data.
        """)

# Enhanced main application updates
def enhanced_main():
    """
    Enhanced main function with better error handling
    """
    st.title("📊 US Index Trading Dashboard")

    # Show month-end warning if applicable
    display_month_end_warning()

    # --- Enhanced Sidebar ---
    st.sidebar.title("Controls & Planning")
    
    # Enhanced data fetching
    enhanced_fetch_economic_data()
    
    # Show detailed data status
    with st.sidebar.expander("📊 Data Status", expanded=False):
        display_enhanced_data_status()
    
    # Rest of your sidebar components remain the same
    display_sidebar_risk_management()
    st.sidebar.markdown("---")
    display_sidebar_payout_planner()

    # --- Enhanced Main Page ---
    display_header_dashboard()

    tab1, tab2 = st.tabs(["📈 Daily Plan", "🌍 Headlines"])

    with tab1:
        col1, col2 = st.columns([2, 1])
        with col1:
            selected_date = st.date_input("📅 Analysis Date", value=date.today())
        with col2:
            view_mode = st.selectbox("View Mode", ["Today", "Week"], index=0)
        
        st.markdown("---")

        if selected_date.weekday() >= 5:
            st.markdown('<div class="weekend-notice"><h2>🏖️ Weekend Mode</h2><p>Markets are closed. Relax, review, and prepare for the week ahead!</p></div>', unsafe_allow_html=True)
            return

        # Enhanced data loading with better error messages
        df, status_msg = get_events_from_db_enhanced()
        
        if df.empty:
            st.error(f"📭 **No Economic Data Available**")
            st.info(status_msg)
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Try Fetching Data Now", type="primary"):
                    enhanced_fetch_economic_data()
            
            with col2:
                if st.button("📊 Show Sample Analysis", type="secondary"):
                    st.info("Showing analysis with sample data structure...")
                    # You could show a demo with placeholder data here
            
            return

        # Continue with your existing logic...
        records = df.to_dict('records')
        get_events_for = lambda d: [row for row in records if parse_date(row.get('date', '')) == d]

        # Rest of your main logic remains the same
        if view_mode == "Today":
            events = get_events_for(selected_date)
            plan, reason, morning, afternoon, allday = analyze_day_events(selected_date, events) if events else ("Standard Day Plan", "No economic events found.", [], [], [])
            display_main_plan_card(plan, reason)
            st.markdown("---")
            display_seasonality_analysis('QQQ', selected_date)
            
            col1, col2 = st.columns([1, 1])
            with col1:
                display_action_checklist(plan)
            with col2:
                st.markdown("### 📅 Today's Events")
                display_compact_events(morning, afternoon, allday)
                st.markdown("### 💰 Today's Earnings")
                earnings_today = fetch_and_format_earnings(selected_date)
                if earnings_today:
                    with st.container(height=250):
                        for item in earnings_today: st.markdown(f"• **{item['company']}**")
                else:
                    st.markdown("*No major earnings reports scheduled.*")
        else: # Week view
            display_week_view(selected_date, records)
    
    with tab2:
        display_headlines_tab()
