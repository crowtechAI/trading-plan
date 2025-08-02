import streamlit as st
import pandas as pd
import csv
from datetime import datetime, time, date, timedelta
from io import StringIO
import pytz
import subprocess
import sys
import os

# --- CONFIGURATION ---
st.set_page_config(
    page_title="US Index Trading Plan",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CONSTANTS ---
# The predictable filename that the scraper will generate and this app will read.
SCRAPED_DATA_PATH = "latest_forex_data.csv"

# Custom CSS optimized for dark theme
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
    .status-indicator {
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-weight: bold;
        margin: 0.25rem;
        display: inline-block;
    }
    .status-success { background: rgba(76, 175, 80, 0.2); color: #4caf50; border: 1px solid #4caf50; }
    .status-warning { background: rgba(255, 152, 0, 0.2); color: #ff9800; border: 1px solid #ff9800; }
    .status-error { background: rgba(244, 67, 54, 0.2); color: #f44336; border: 1px solid #f44336; }
    .status-info { background: rgba(33, 150, 243, 0.2); color: #2196f3; border: 1px solid #2196f3; }
</style>
""", unsafe_allow_html=True)

# --- STRATEGY RULES ---
MORNING_CUTOFF = time(12, 0)
AFTERNOON_NO_TRADE_START = time(13, 55)
NO_TRADE_KEYWORDS = ['FOMC Statement', 'FOMC Press Conference', 'Interest Rate Decision', 'Monetary Policy Report']
FORCED_HIGH_IMPACT_KEYWORDS = ['Powell Speaks', 'Fed Chair', 'Non-Farm', 'NFP', 'CPI', 'Consumer Price Index', 'PPI', 'Producer Price Index', 'GDP']

# --- UTILITY FUNCTIONS ---
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
    if not time_str or time_str.lower() in ['empty', '']: 
        return None
    for fmt in ('%I:%M%p', '%I:%M %p', '%H:%M'):
        try: 
            return datetime.strptime(time_str.strip(), fmt).time()
        except ValueError: 
            continue
    return None

def parse_date(date_str):
    try: 
        return datetime.strptime(date_str.strip(), '%d/%m/%Y').date()
    except (ValueError, TypeError): 
        return None

def parse_impact(impact_str):
    if not impact_str: 
        return "Low"
    lower = impact_str.lower()
    if 'high' in lower: 
        return "High"
    if 'medium' in lower: 
        return "Medium"
    if 'low' in lower: 
        return "Low"
    return "Low"

# --- ANALYSIS CORE ---
def analyze_day_events(target_date, events):
    plan, reason = "Standard Day Plan", "No high-impact USD morning news or critical USD afternoon events found."
    has_morning_high_impact_usd = False
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
                    return "No Trade Day", f"Critical afternoon USD event '{event_name}' at {event_time.strftime('%I:%M %p')}.", morning_events, afternoon_events, all_day_events
            
            if is_high_impact and event_time and event_time < MORNING_CUTOFF: 
                has_morning_high_impact_usd = True
    
    if has_morning_high_impact_usd: 
        plan, reason = "News Day Plan", "High-impact USD news detected in the morning session."
    
    return plan, reason, morning_events, afternoon_events, all_day_events

# --- UI COMPONENTS ---
def display_plan_card(plan, reason):
    if plan == "No Trade Day": 
        card_class, icon, title = "no-trade", "🚫", "NO TRADE DAY"
    elif plan == "News Day Plan": 
        card_class, icon, title = "news-day", "📰", "NEWS DAY PLAN"
    else: 
        card_class, icon, title = "standard-day", "✅", "STANDARD DAY PLAN"
    
    st.markdown(f'''
    <div class="main-plan-card {card_class}">
        <h1>{icon} {title}</h1>
        <p style="font-size: 1.1rem; margin-top: 1rem;">{reason}</p>
    </div>
    ''', unsafe_allow_html=True)

def display_action_checklist(plan):
    st.markdown("## 🎯 Action Checklist")
    
    if plan == "News Day Plan": 
        checklist = [
            "🚫 DO NOT trade the morning session",
            "📊 Mark NY Lunch Range (12:00 PM - 1:30 PM)",
            "👀 Wait for liquidity raid after 1:30 PM",
            "🎯 Prime entry window: 2:00 PM - 3:00 PM",
            "✅ Look for displacement/FVG confirmation"
        ]
    elif plan == "Standard Day Plan": 
        checklist = [
            "📈 Ready for morning open at 9:30 AM",
            "📊 Mark Previous Day PM Range (1:30 PM - 4:00 PM)",
            "🌍 Mark Today's London Range (2:00 AM - 5:00 AM)",
            "👀 Wait for Judas Swing at open",
            "✅ Enter after sweep with displacement/FVG"
        ]
    else: 
        checklist = [
            "🚫 Stand aside completely",
            "💰 Preserve capital",
            "📚 Use time for analysis",
            "⏰ Wait for next opportunity"
        ]
    
    for item in checklist: 
        st.markdown(f'<div class="checklist-item">{item}</div>', unsafe_allow_html=True)

def display_timeline_events(events, title):
    if not events: 
        return
    
    st.markdown(f"### {title}")
    sorted_events = sorted([e for e in events if e['raw_time']], key=lambda x: x['raw_time'])
    sorted_events.extend([e for e in events if not e['raw_time']])
    
    for event in sorted_events:
        impact_class = "event-high" if "High" in event['impact'] else ("event-medium" if "Medium" in event['impact'] else "event-low")
        emoji = "🔴" if "High" in event['impact'] else ("🟠" if "Medium" in event['impact'] else "🟡")
        currency_display = f"**{event['currency']}**" if event['currency'] == 'USD' else event['currency']
        
        st.markdown(f'''
        <div class="event-timeline {impact_class}">
            <div style="min-width: 80px; font-weight: bold;">{event["time"]}</div>
            <div style="min-width: 30px; text-align: center;">{emoji}</div>
            <div style="min-width: 50px; font-weight: bold;">{currency_display}</div>
            <div style="flex: 1; margin-left: 10px;">{event["name"]}</div>
        </div>
        ''', unsafe_allow_html=True)

def get_current_session(current_time):
    current = current_time.time()
    if time(2, 0) <= current < time(5, 0): 
        return "London"
    elif time(9, 30) <= current < time(12, 0): 
        return "NY Morning"
    elif time(12, 0) <= current < time(13, 30): 
        return "NY Lunch"
    elif time(13, 30) <= current < time(16, 0): 
        return "NY Afternoon"
    else: 
        return "Pre-Market"

def display_market_status():
    current_time = get_current_market_time()
    time_to_open = time_until_market_open()
    
    col1, col2, col3 = st.columns(3)
    
    with col1: 
        st.markdown(f'''
        <div class="metric-card">
            <div class="metric-label">Current ET Time</div>
            <div class="metric-value">{current_time.strftime("%I:%M %p")}</div>
        </div>
        ''', unsafe_allow_html=True)
    
    with col2:
        if time_to_open.total_seconds() > 0:
            hours, rem = divmod(int(time_to_open.total_seconds()), 3600)
            mins, _ = divmod(rem, 60)
            display, label = f"{hours}h {mins}m", "Time to Market Open"
        else:
            display = "OPEN" if current_time.time() < time(16, 0) else "CLOSED"
            label = "Market Status"
        
        st.markdown(f'''
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{display}</div>
        </div>
        ''', unsafe_allow_html=True)
    
    with col3:
        session = get_current_session(current_time)
        st.markdown(f'''
        <div class="metric-card">
            <div class="metric-label">Current Session</div>
            <div class="metric-value">{session}</div>
        </div>
        ''', unsafe_allow_html=True)

def display_scraper_status():
    """Display current status of scraped data"""
    if os.path.exists(SCRAPED_DATA_PATH):
        try:
            file_stats = os.stat(SCRAPED_DATA_PATH)
            file_size = file_stats.st_size
            modified_time = datetime.fromtimestamp(file_stats.st_mtime)
            time_since_update = datetime.now() - modified_time
            
            # Read CSV to get event count
            df = pd.read_csv(SCRAPED_DATA_PATH)
            event_count = len(df)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown(f'''
                <div class="status-indicator status-success">
                    📄 {event_count} Events Loaded
                </div>
                ''', unsafe_allow_html=True)
            
            with col2:
                if time_since_update.total_seconds() < 3600:  # Less than 1 hour
                    status_class = "status-success"
                    time_text = f"{int(time_since_update.total_seconds() / 60)}m ago"
                elif time_since_update.total_seconds() < 86400:  # Less than 1 day
                    status_class = "status-warning"
                    time_text = f"{int(time_since_update.total_seconds() / 3600)}h ago"
                else:
                    status_class = "status-error"
                    time_text = f"{int(time_since_update.days)}d ago"
                
                st.markdown(f'''
                <div class="status-indicator {status_class}">
                    🕒 Updated {time_text}
                </div>
                ''', unsafe_allow_html=True)
            
            with col3:
                size_mb = file_size / 1024 / 1024
                st.markdown(f'''
                <div class="status-indicator status-info">
                    💾 {size_mb:.1f}MB
                </div>
                ''', unsafe_allow_html=True)
                
        except Exception as e:
            st.markdown(f'''
            <div class="status-indicator status-error">
                ⚠️ Error reading data file
            </div>
            ''', unsafe_allow_html=True)
    else:
        st.markdown(f'''
        <div class="status-indicator status-warning">
            📄 No data file found
        </div>
        ''', unsafe_allow_html=True)

def run_scraper(scrape_option):
    """Run the scraper with proper error handling and environment setup"""
    args = ["--week"] if scrape_option == 'Current Trading Week' else []
    command = [sys.executable, "ffscraper.py"] + args
    
    with st.spinner(f"🔄 Running scraper for '{scrape_option}'... This may take a moment."):
        try:
            # Set environment variables for Streamlit Cloud detection
            env = os.environ.copy()
            env['STREAMLIT'] = 'true'
            env['STREAMLIT_SHARING_MODE'] = 'true'
            
            # Run scraper with timeout
            process = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                check=True, 
                encoding='utf-8',
                env=env,
                timeout=300  # 5 minute timeout
            )
            
            st.sidebar.success("✅ Scraper finished successfully!")
            
            # Show output if available
            if process.stdout:
                with st.sidebar.expander("📋 Show Scraper Log"):
                    st.code(process.stdout)
            
            # Check if the data file was created
            if os.path.exists(SCRAPED_DATA_PATH):
                st.sidebar.success(f"📄 Data file created: {SCRAPED_DATA_PATH}")
                return True
            else:
                st.sidebar.warning("⚠️ Scraper completed but no data file found")
                return False
                
        except subprocess.TimeoutExpired:
            st.sidebar.error("⏰ Scraper timed out after 5 minutes")
            st.sidebar.info("💡 **Troubleshooting tips:**\n" +
                          "- Try using 'Current Trading Week' for less data\n" +
                          "- Check your internet connection\n" +
                          "- Wait a few minutes and try again")
            return False
            
        except subprocess.CalledProcessError as e:
            st.sidebar.error("❌ The scraper script failed to run")
            
            # Show detailed error information
            with st.sidebar.expander("🔍 Show Error Details", expanded=True):
                st.text(f"Return code: {e.returncode}")
                if e.stderr:
                    st.text("Error output:")
                    st.code(e.stderr)
                if e.stdout:
                    st.text("Standard output:")
                    st.code(e.stdout)
            
            # Provide helpful suggestions based on error type
            error_text = str(e.stderr).lower() if e.stderr else ""
            if "webdriver" in error_text or "chrome" in error_text:
                st.sidebar.info("💡 **WebDriver Error Detected:**\n" +
                              "- This may be a temporary issue with the browser setup\n" +
                              "- Try again in a few minutes\n" +
                              "- If persistent, this may be a platform limitation")
            elif "timeout" in error_text or "connection" in error_text:
                st.sidebar.info("💡 **Connection Error:**\n" +
                              "- Check if forexfactory.com is accessible\n" +
                              "- Try the 'Current Trading Week' option\n" +
                              "- Wait a moment and retry")
            else:
                st.sidebar.info("💡 **General Troubleshooting:**\n" +
                              "- Wait a few minutes and try again\n" +
                              "- Try the 'Current Trading Week' option for less data\n" +
                              "- Check if the website is accessible")
            return False
                          
        except FileNotFoundError:
            st.sidebar.error("❌ Error: 'ffscraper.py' not found")
            st.sidebar.info("📁 **File Missing:**\n" +
                          "Ensure the scraper file is in the same directory as this app")
            return False
            
        except Exception as e:
            st.sidebar.error(f"❌ Unexpected error: {str(e)}")
            st.sidebar.info("🔄 **Unexpected Error:**\n" +
                          "Try refreshing the page and running again")
            return False

def main():
    st.title("📈 US Index Trading Plan ($NQ, $ES)")
    
    # Display market status
    display_market_status()
    st.markdown("---")
    
    # Display data status
    display_scraper_status()

    # --- Sidebar for Data Loading ---
    st.sidebar.header("⚙️ Data Controls")
    
    scrape_option = st.sidebar.radio(
        "Select Scrape Duration", 
        ('Current Trading Week', 'Current Month'), 
        help="Choose the time period for scraping economic events"
    )
    
    if st.sidebar.button("🚀 Fetch Live Data", type="primary", use_container_width=True):
        success = run_scraper(scrape_option)
        if success:
            st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.info("💡 **Tips:**\n" +
                   "- Use 'Current Trading Week' for faster scraping\n" +
                   "- Data updates automatically after successful scraping\n" +
                   "- Refresh if you encounter any issues")

    # --- Main Analysis Area ---
    col1, col2 = st.columns([2, 2])
    
    with col1: 
        selected_date = st.date_input("📅 Analysis Date", value=date.today())
    
    with col2: 
        view_option = st.radio("👁️ View", ["Today", "Week"], horizontal=True)

    # --- Data Analysis ---
    if os.path.exists(SCRAPED_DATA_PATH):
        try:
            df = pd.read_csv(SCRAPED_DATA_PATH)
            csv_data = df.to_dict('records')
            
            if not csv_data:
                st.warning("📄 Data file is empty. Please run the scraper again.")
                return

            get_events = lambda target: [row for row in csv_data if parse_date(row.get('date', '')) == target]
            
            if view_option == "Today":
                events = get_events(selected_date)
                
                if not events: 
                    st.warning(f"📅 No events found for {selected_date.strftime('%A, %B %d, %Y')}")
                    st.info("💡 Try running the scraper or selecting a different date")
                    return
                
                # Analyze and display
                plan, reason, morning, afternoon, all_day = analyze_day_events(selected_date, events)
                
                display_plan_card(plan, reason)
                display_action_checklist(plan)
                
                st.markdown("---")
                st.markdown("## 📅 Today's Events Timeline")
                
                c1, c2 = st.columns(2)
                with c1: 
                    display_timeline_events(morning, "🌅 Morning (Before 12:00 PM)")
                with c2: 
                    display_timeline_events(afternoon, "🌇 Afternoon (After 12:00 PM)")
                
                if all_day: 
                    display_timeline_events(all_day, "📅 All Day Events")
                    
            else:  # Week view
                st.markdown("## 🗓 Weekly Outlook")
                
                start_of_week = selected_date - timedelta(days=selected_date.weekday())
                
                for i in range(5):  # Monday to Friday
                    day = start_of_week + timedelta(days=i)
                    events = get_events(day)
                    
                    c1, c2, c3 = st.columns([2, 3, 2])
                    
                    with c1: 
                        st.markdown(f"**{day.strftime('%a %m/%d')}**")
                    
                    with c2:
                        if events:
                            plan, _, _, _, _ = analyze_day_events(day, events)
                            if plan == "No Trade Day": 
                                st.error("🚫 No Trade")
                            elif plan == "News Day Plan": 
                                st.warning("📰 News Day")
                            else: 
                                st.success("✅ Standard")
                        else: 
                            st.info("📅 No Events")
                    
                    with c3:
                        if events:
                            usd_high_count = sum(1 for e in events 
                                               if 'High' in parse_impact(e.get('impact', '')) 
                                               and e.get('currency', '').upper() == 'USD')
                            if usd_high_count > 0: 
                                st.markdown(f"🔴 {usd_high_count} High USD")
                            else:
                                st.markdown("🟡 Low Impact")
                        
        except Exception as e:
            st.error(f"❌ Error processing data file '{SCRAPED_DATA_PATH}': {str(e)}")
            st.info("💡 Try running the scraper again or check the data file")
            
    else:
        # Welcome screen when no data is available
        st.info("👋 **Welcome to the US Index Trading Plan!**")
        st.markdown("""
        **Get started:**
        1. Click **'Fetch Live Data'** in the sidebar to scrape the latest economic events
        2. Choose between 'Current Trading Week' (faster) or 'Current Month' (comprehensive)
        3. Analyze your trading plan based on upcoming USD news events
        
        **What this app does:**
        - Analyzes economic calendar events from Forex Factory
        - Identifies high-impact USD news that affects index trading
        - Provides specific trading plans based on news timing
        - Shows detailed event timelines and impact levels
        """)
        
        st.markdown("---")
        st.markdown("## 📋 Sample Action Checklist")
        display_action_checklist("Standard Day Plan")

if __name__ == "__main__":
    main()
