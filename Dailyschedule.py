# Month-end monitoring and backup data system

import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, date, timedelta
import requests
import json
import time

class BackupDataProvider:
    """
    Provides backup economic data when primary sources fail
    """
    
    def __init__(self):
        self.backup_events = self.get_static_recurring_events()
    
    def get_static_recurring_events(self):
        """
        Static list of recurring high-impact events that happen monthly
        """
        return [
            {
                'event': 'Non-Farm Payrolls',
                'currency': 'USD',
                'impact': 'High',
                'typical_day': 'First Friday',
                'typical_time': '08:30',
                'description': 'Monthly employment data release'
            },
            {
                'event': 'CPI (Consumer Price Index)',
                'currency': 'USD', 
                'impact': 'High',
                'typical_day': 'Mid-month (10th-15th)',
                'typical_time': '08:30',
                'description': 'Monthly inflation data'
            },
            {
                'event': 'FOMC Meeting Minutes',
                'currency': 'USD',
                'impact': 'High', 
                'typical_day': '3 weeks after FOMC',
                'typical_time': '14:00',
                'description': 'Federal Reserve meeting minutes'
            },
            {
                'event': 'Retail Sales',
                'currency': 'USD',
                'impact': 'Medium',
                'typical_day': 'Mid-month (13th-17th)',
                'typical_time': '08:30',
                'description': 'Monthly consumer spending data'
            },
            {
                'event': 'PPI (Producer Price Index)',
                'currency': 'USD',
                'impact': 'Medium',
                'typical_day': 'Day after CPI',
                'typical_time': '08:30',
                'description': 'Monthly wholesale inflation data'
            }
        ]
    
    def estimate_next_nfp_date(self, from_date=None):
        """
        Calculate the next Non-Farm Payrolls date (First Friday of month)
        """
        if from_date is None:
            from_date = date.today()
        
        # Start with first day of next month
        if from_date.day == 1:
            target_month = from_date
        else:
            if from_date.month == 12:
                target_month = from_date.replace(year=from_date.year + 1, month=1, day=1)
            else:
                target_month = from_date.replace(month=from_date.month + 1, day=1)
        
        # Find first Friday
        days_to_friday = (4 - target_month.weekday()) % 7
        first_friday = target_month + timedelta(days=days_to_friday)
        
        return first_friday
    
    def estimate_next_cpi_date(self, from_date=None):
        """
        Estimate next CPI date (usually around 13th of month)
        """
        if from_date is None:
            from_date = date.today()
        
        # Target day is usually 13th, but can vary
        target_day = 13
        
        if from_date.day <= target_day and from_date.month != 12:
            target_date = from_date.replace(day=target_day)
        else:
            # Next month
            if from_date.month == 12:
                target_date = from_date.replace(year=from_date.year + 1, month=1, day=target_day)
            else:
                target_date = from_date.replace(month=from_date.month + 1, day=target_day)
        
        # Adjust if it falls on weekend
        if target_date.weekday() >= 5:  # Saturday or Sunday
            # Move to next Tuesday (common adjustment)
            days_to_add = (7 - target_date.weekday()) + 1
            target_date += timedelta(days=days_to_add)
        
        return target_date
    
    def generate_emergency_calendar(self, days_ahead=14):
        """
        Generate emergency calendar when scraping fails
        """
        events = []
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)
        
        # NFP
        nfp_date = self.estimate_next_nfp_date(start_date)
        if start_date <= nfp_date <= end_date:
            events.append({
                'date': nfp_date.strftime('%d/%m/%Y'),
                'time': '8:30AM',
                'currency': 'USD',
                'impact': 'High',
                'event': 'Non-Farm Payrolls',
                'actual': '',
                'forecast': '',
                'previous': '',
                'source': 'Emergency Calendar'
            })
        
        # CPI
        cpi_date = self.estimate_next_cpi_date(start_date)
        if start_date <= cpi_date <= end_date:
            events.append({
                'date': cpi_date.strftime('%d/%m/%Y'),
                'time': '8:30AM', 
                'currency': 'USD',
                'impact': 'High',
                'event': 'Consumer Price Index (CPI)',
                'actual': '',
                'forecast': '',
                'previous': '',
                'source': 'Emergency Calendar'
            })
        
        return events

class DataHealthMonitor:
    """
    Monitors data health and provides fallback strategies
    """
    
    def __init__(self):
        self.backup_provider = BackupDataProvider()
        self.health_checks = []
    
    def check_forex_factory_health(self):
        """Check if Forex Factory is accessible"""
        try:
            response = requests.get('https://www.forexfactory.com', timeout=10)
            if response.status_code == 200:
                return True, "Forex Factory accessible"
            else:
                return False, f"Forex Factory returned {response.status_code}"
        except Exception as e:
            return False, f"Forex Factory unreachable: {e}"
    
    def check_financial_juice_health(self):
        """Check if Financial Juice is accessible"""
        try:
            response = requests.get('https://www.financialjuice.com', timeout=10)
            if response.status_code == 200:
                return True, "Financial Juice accessible"
            else:
                return False, f"Financial Juice returned {response.status_code}"
        except Exception as e:
            return False, f"Financial Juice unreachable: {e}"
    
    def check_data_freshness(self, df):
        """Check if data is fresh enough"""
        if df.empty:
            return False, "No data available"
        
        if 'date' not in df.columns:
            return False, "No date column in data"
        
        try:
            # Parse dates and find the most recent
            df['parsed_date'] = df['date'].apply(lambda x: self.parse_date_safe(x))
            valid_dates = df['parsed_date'].dropna()
            
            if valid_dates.empty:
                return False, "No valid dates in data"
            
            most_recent = valid_dates.max()
            days_old = (date.today() - most_recent).days
            
            if days_old <= 7:
                return True, f"Data is {days_old} days old (acceptable)"
            else:
                return False, f"Data is {days_old} days old (stale)"
                
        except Exception as e:
            return False, f"Error checking data freshness: {e}"
    
    def parse_date_safe(self, date_str):
        """Safely parse date strings"""
        try:
            return datetime.strptime(str(date_str).strip(), '%d/%m/%Y').date()
        except (ValueError, TypeError):
            return None
    
    def run_full_health_check(self, current_data=None):
        """Run comprehensive health check"""
        results = {
            'timestamp': datetime.now(),
            'overall_health': 'unknown',
            'checks': {},
            'recommendations': []
        }
        
        # Check external services
        ff_healthy, ff_msg = self.check_forex_factory_health()
        results['checks']['forex_factory'] = {'healthy': ff_healthy, 'message': ff_msg}
        
        fj_healthy, fj_msg = self.check_financial_juice_health()
        results['checks']['financial_juice'] = {'healthy': fj_healthy, 'message': fj_msg}
        
        # Check data freshness
        if current_data is not None:
            fresh_healthy, fresh_msg = self.check_data_freshness(current_data)
            results['checks']['data_freshness'] = {'healthy': fresh_healthy, 'message': fresh_msg}
        
        # Determine overall health
        healthy_count = sum(1 for check in results['checks'].values() if check['healthy'])
        total_checks = len(results['checks'])
        
        if healthy_count == total_checks:
            results['overall_health'] = 'good'
        elif healthy_count >= total_checks // 2:
            results['overall_health'] = 'degraded'
        else:
            results['overall_health'] = 'poor'
        
        # Generate recommendations
        if not ff_healthy:
            results['recommendations'].append("🔄 Retry Forex Factory scraping in 1 hour")
        
        if not fj_healthy:
            results['recommendations'].append("🔑 Update Financial Juice API tokens")
        
        if current_data is not None and not fresh_healthy:
            results['recommendations'].append("📅 Use emergency calendar for critical events")
            results['recommendations'].append("🔄 Force refresh economic data")
        
        if results['overall_health'] == 'poor':
            results['recommendations'].append("⚠️ Consider using backup data sources")
            results['recommendations'].append("📞 Check financial news websites manually")
        
        return results

def display_health_dashboard():
    """Display system health dashboard"""
    st.header("🏥 System Health Dashboard")
    
    monitor = DataHealthMonitor()
    
    if st.button("🔍 Run Health Check"):
        with st.spinner("Running comprehensive health check..."):
            # Get current data for freshness check
            df = get_events_from_db() if 'get_events_from_db' in globals() else pd.DataFrame()
            health_results = monitor.run_full_health_check(df)
            
            # Display overall status
            if health_results['overall_health'] == 'good':
                st.success("✅ All systems operational")
            elif health_results['overall_health'] == 'degraded':
                st.warning("⚠️ Some systems experiencing issues")
            else:
                st.error("❌ Multiple system failures detected")
            
            # Display individual checks
            st.subheader("🔍 Service Status")
            for service, result in health_results['checks'].items():
                status_icon = "✅" if result['healthy'] else "❌"
                service_name = service.replace('_', ' ').title()
                st.markdown(f"{status_icon} **{service_name}**: {result['message']}")
            
            # Display recommendations
            if health_results['recommendations']:
                st.subheader("💡 Recommended Actions")
                for rec in health_results['recommendations']:
                    st.markdown(f"- {rec}")
            
            # Emergency calendar option
            if health_results['overall_health'] == 'poor':
                st.subheader("🚨 Emergency Options")
                if st.button("📅 Generate Emergency Calendar"):
                    emergency_events = monitor.backup_provider.generate_emergency_calendar()
                    if emergency_events:
                        st.success(f"Generated {len(emergency_events)} emergency events")
                        df = pd.DataFrame(emergency_events)
                        st.dataframe(df)
                        
                        # Option to save emergency data
                        if st.button("💾 Use Emergency Calendar"):
                            # Save to session state or database
                            st.session_state['emergency_calendar'] = emergency_events
                            st.success("Emergency calendar activated!")
                    else:
                        st.warning("No emergency events for the next 2 weeks")

def display_month_end_status():
    """Display month-end specific status and warnings"""
    today = date.today()
    
    # Calculate month-end metrics
    next_month = today.replace(day=28) + timedelta(days=4)
    month_end = next_month - timedelta(days=next_month.day)
    days_to_month_end = (month_end - today).days
    
    first_of_month = today.replace(day=1)
    days_from_month_start = (today - first_of_month).days
    
    st.sidebar.subheader("📅 Month-End Status")
    
    if days_to_month_end <= 3:
        st.sidebar.error(f"⚠️ {days_to_month_end} days to month-end")
        st.sidebar.markdown("**Expected Issues:**")
        st.sidebar.markdown("- API token expiration")
        st.sidebar.markdown("- Slower website responses") 
        st.sidebar.markdown("- Increased anti-bot measures")
        
    elif days_from_month_start <= 2:
        st.sidebar.warning(f"⚠️ {days_from_month_start} days into new month")
        st.sidebar.markdown("**Potential Issues:**")
        st.sidebar.markdown("- Calendar pagination changes")
        st.sidebar.markdown("- New API rate limits")
        
    else:
        st.sidebar.success("✅ Normal period")
    
    # Show next critical dates
    monitor = DataHealthMonitor()
    next_nfp = monitor.backup_provider.estimate_next_nfp_date()
    next_cpi = monitor.backup_provider.estimate_next_cpi_date()
    
    st.sidebar.markdown("**Next Key Events:**")
    st.sidebar.markdown(f"📊 NFP: {next_nfp.strftime('%b %d')}")
    st.sidebar.markdown(f"📈 CPI: {next_cpi.strftime('%b %d')}")

# Integration function for your main app
def enhanced_main_with_monitoring():
    """
    Enhanced main function with health monitoring
    """
    st.title("📊 US Index Trading Dashboard")
    
    # Add health monitoring tab
    tab1, tab2, tab3, tab4 = st.tabs(["📈 Daily Plan", "🌍 Headlines", "🏥 Health", "📅 Emergency"])
    
    with tab1:
        # Your existing daily plan code
        display_month_end_status()  # Add to sidebar
        # ... rest of your existing code
        pass
    
    with tab2:
        # Your existing headlines code
        pass
    
    with tab3:
        display_health_dashboard()
    
    with tab4:
        st.header("🚨 Emergency Calendar")
        st.write("Use this when primary data sources are unavailable")
        
        backup_provider = BackupDataProvider()
        emergency_events = backup_provider.generate_emergency_calendar()
        
        if emergency_events:
            st.dataframe(pd.DataFrame(emergency_events))
            
            if st.button("🔄 Use Emergency Data"):
                # Save emergency data to your database or session
                st.session_state['using_emergency_data'] = True
                st.success("Emergency calendar is now active!")
        else:
            st.info("No critical events in the next 2 weeks")
