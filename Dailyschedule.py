# --- MAIN APPLICATION (WITH DEBUGGING) ---
def main():
    st.write("DEBUG: Starting main() function.") # <-- ADD THIS
    st.title("📊 US Index Trading Dashboard")

    # --- Sidebar ---
    st.sidebar.title("Controls & Planning")
    if st.sidebar.button("🔄 Fetch Economic Data", type="primary"):
        with st.spinner("Fetching data from Forex Factory..."):
            try:
                # Ensure ffscraper.py is in the same directory or provide a full path
                subprocess.run([sys.executable, "ffscraper.py"], check=True, capture_output=True, text=True)
                st.sidebar.success("✅ Economic Data Fetched!")
                st.cache_data.clear() # Clear all cached data
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"❌ Update failed: {e}")
    
    display_sidebar_risk_management()
    st.sidebar.markdown("---")
    display_sidebar_payout_planner()

    # --- Main Page ---
    display_header_dashboard()

    tab1, tab2 = st.tabs(["📈 Daily Plan", "🌍 Headlines"])

    with tab1:
        st.write("DEBUG: Inside Tab 1.") # <-- ADD THIS
        col1, col2 = st.columns([2, 1])
        with col1:
            selected_date = st.date_input("📅 Analysis Date", value=date.today())
        with col2:
            view_mode = st.selectbox("View Mode", ["Today", "Week"], index=0)
        
        st.markdown("---")

        st.write(f"DEBUG: Selected date is {selected_date}, weekday is {selected_date.weekday()}.") # <-- ADD THIS
        if selected_date.weekday() >= 5:
            st.write("DEBUG: It's a weekend. Displaying notice and returning.") # <-- ADD THIS
            st.markdown('<div class="weekend-notice"><h2>🏖️ Weekend Mode</h2><p>Markets are closed. Relax, review, and prepare for the week ahead!</p></div>', unsafe_allow_html=True)
            return

        st.write("DEBUG: Attempting to get events from DB.") # <-- ADD THIS
        df = get_events_from_db()
        
        if df.empty:
            st.write("DEBUG: The dataframe is empty. Displaying warning and returning.") # <-- ADD THIS
            st.warning("👋 No economic data found. Click **Fetch Economic Data** in the sidebar to load events.")
            return

        st.write(f"DEBUG: Dataframe loaded successfully with {len(df)} rows.") # <-- ADD THIS
        st.dataframe(df.head()) # Let's see the first few rows of the data

        records = df.to_dict('records')
        get_events_for = lambda d: [row for row in records if parse_date(row.get('date', '')) == d]

        if view_mode == "Today":
            st.write("DEBUG: In 'Today' view.") # <-- ADD THIS
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
            st.write("DEBUG: In 'Week' view.") # <-- ADD THIS
            display_week_view(selected_date, records)
    
    with tab2:
        st.write("DEBUG: Inside Tab 2.") # <-- ADD THIS
        display_headlines_tab()

if __name__ == "__main__":
    main()
