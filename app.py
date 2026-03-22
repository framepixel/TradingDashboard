import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import json
from datetime import datetime, timezone, time as dt_time
from data_fetcher import (
    fetch_tradfi_data, 
    fetch_top_binance_movers, 
    fetch_ohlcv_data,
    fetch_top_stock_movers,
    fetch_stock_ohlcv_data,
    fetch_market_news
)
from technical_analysis import calculate_indicators, analyze_strategy
from ai_agent import generate_ai_trade_idea

# ==========================================
# PAGE CONFIGURATION & INITIALIZATION
# ==========================================
st.set_page_config(page_title="Daily Trading Opportunity Dashboard", layout="wide")

# Try to import autorefresh for active traders
try:
    from streamlit_autorefresh import st_autorefresh
    # Auto-refresh every 60 seconds
    st_autorefresh(interval=60000, key="datarefresh")
except ImportError:
    pass

def get_market_status():
    """Check if US Markets are open"""
    now = datetime.now(timezone.utc)
    # US Market Hours (9:30 AM - 4:00 PM ET) roughly 13:30 to 20:00 UTC during daylight saving (or 14:30 to 21:00 std)
    # Simplified approximation for general awareness
    us_market_open = dt_time(13, 30)
    us_market_close = dt_time(20, 0)
    
    if us_market_open <= now.time() <= us_market_close and now.weekday() < 5:
        return "🟢 US Markets: OPEN"
    else:
        return "🔴 US Markets: CLOSED"

# ==========================================
# DASHBOARD UI
# ==========================================
def main():
    st.sidebar.title("⚙️ Settings")
    timeframe = st.sidebar.radio("Select Timeframe:", ["1m", "5m", "15m", "1h", "1d"], index=1)
    min_score = st.sidebar.slider("Minimum Confidence Score", 0, 100, 30, help="Filter setups by technical strength")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Status:** {get_market_status()}")
    st.sidebar.markdown("---")
    
    # -----------------------------
    # WEBHOOK SETTINGS
    # -----------------------------
    with st.sidebar.expander("🔔 Alert Settings"):
        webhook_url = st.text_input("Discord Webhook URL", value=st.session_state.get("discord_webhook", ""), type="password")
        if webhook_url != st.session_state.get("discord_webhook", ""):
            st.session_state.discord_webhook = webhook_url
        st.session_state.webhook_active = st.checkbox("Enable Discord Alerts", value=st.session_state.get("webhook_active", False))

    st.sidebar.markdown("---")
    
    # -----------------------------
    # WATCHLIST PERSISTENCE
    # -----------------------------
    if "watchlist" not in st.session_state:
        st.session_state.watchlist = ["AAPL", "BTC/USDT", "NVDA"]

    st.sidebar.title("⭐ My Watchlist")
    new_symbol = st.sidebar.text_input("Add Symbol", placeholder="ETH/USDT or TSLA").upper()
    if st.sidebar.button("➕ Add") and new_symbol:
        if new_symbol not in st.session_state.watchlist:
            st.session_state.watchlist.append(new_symbol)
            st.toast(f"Added {new_symbol} to Watchlist!")
    
    st.sidebar.markdown("### Current Watchlist")
    for sym in st.session_state.watchlist:
        cols = st.sidebar.columns([3, 1])
        cols[0].text(sym)
        if cols[1].button("✖", key=f"del_{sym}"):
            st.session_state.watchlist.remove(sym)
            st.rerun()

    # -----------------------------
    # TRADE JOURNAL INITIALIZATION
    # -----------------------------
    if "trades" not in st.session_state:
        st.session_state.trades = pd.DataFrame(columns=["Date", "Symbol", "Side", "Entry Price", "Exit Price", "P&L", "Notes"])

    # -----------------------------
    # AI IDEAS CACHE
    # -----------------------------
    if "ai_ideas" not in st.session_state:
        st.session_state.ai_ideas = {}

    st.title("🚀 Intraday Trading Dashboard")
    st.markdown("Scans the market for volume anomalies, breakouts, and pullbacks in real-time.")
    
    # Auto-refresh logic
    col1, col2 = st.columns([8, 1])
    with col2:
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()

    # --- 1. Market Overview ---
    st.header("📊 Market Overview")
    tradfi = fetch_tradfi_data()
    btc_df = calculate_indicators(fetch_ohlcv_data('BTC/USDT', timeframe))
    eth_df = calculate_indicators(fetch_ohlcv_data('ETH/USDT', timeframe))
    
    c1, c2, c3, c4 = st.columns(4)
    
    def get_trend(df):
        if df is None or len(df) == 0 or 'EMA50' not in df:
            return "Unknown"
        return "Bullish 📈" if df.iloc[-1]['close'] > df.iloc[-1]['EMA50'] else "-Bearish 📉"
        
    c1.metric("S&P 500", f"{tradfi.get('S&P 500', {}).get('close', 0):.2f}", f"{tradfi.get('S&P 500', {}).get('change', 0):.2f}%")
    c1.markdown("[📈 Chart](https://www.tradingview.com/chart/?symbol=SP%3ASPX)")
    
    c2.metric("NASDAQ", f"{tradfi.get('NASDAQ', {}).get('close', 0):.2f}", f"{tradfi.get('NASDAQ', {}).get('change', 0):.2f}%")
    c2.markdown("[📈 Chart](https://www.tradingview.com/chart/?symbol=NASDAQ%3AIXIC)")
    
    btc_price = f"${btc_df.iloc[-1]['close']:.2f}" if btc_df is not None and not btc_df.empty else "N/A"
    c3.metric("Bitcoin (BTC)", btc_price, get_trend(btc_df))
    c3.markdown("[📈 Chart](https://www.tradingview.com/chart/?symbol=BINANCE%3ABTCUSDT)")
    
    eth_price = f"${eth_df.iloc[-1]['close']:.2f}" if eth_df is not None and not eth_df.empty else "N/A"
    c4.metric("Ethereum (ETH)", eth_price, get_trend(eth_df))
    c4.markdown("[📈 Chart](https://www.tradingview.com/chart/?symbol=BINANCE%3AETHUSDT)")

    st.divider()

    # --- 2. Top Movers & Scans ---
    st.header("🔥 Top Movers & Setups (24h)")
    
    asset_tabs = st.tabs(["🪙 Crypto", "📈 Stocks"])
    
    def render_movers_section(fetch_movers_func, fetch_ohlcv_func, volume_label, is_crypto):
        with st.spinner(f"Fetching market data ({timeframe})..."):
            top_pairs = fetch_movers_func()
            
            scan_results = []
            detailed_data = {}

            if not top_pairs.empty:
                for _, row in top_pairs.iterrows():
                    try:
                        sym = row['Symbol']
                        df = fetch_ohlcv_func(sym, timeframe)
                        df_ta = calculate_indicators(df)
                        
                        if df_ta is not None and not df_ta.empty and 'EMA50' in df_ta.columns and 'RSI' in df_ta.columns:
                            detailed_data[sym] = df_ta
                            vol_anomaly, breakout, pullback, score, patterns = analyze_strategy(df_ta)
                            last = df_ta.iloc[-1]
                            
                            chart_link = f"https://www.tradingview.com/chart/?symbol={'BINANCE:' + sym.replace('/', '') if is_crypto else sym}"
                            vol = f"${row.get('24h Volume (USDT)', row.get('24h Volume (USD)', 0))/1e6:.1f}M"
                            
                            scan_results.append({
                                'Chart': chart_link, 'Symbol': sym, 'Price': row['Price'],
                                '24h Change (%)': row['24h Change (%)'], 'Volume': vol,
                                'Score': score, 'Patterns': ", ".join(patterns) if patterns else "-",
                                'RSI': round(last['RSI'], 1), 'MACD_Hist': round(last['MACD_Hist'], 4) if 'MACD_Hist' in last else 0,
                                'Vol Anomaly': vol_anomaly, 'Breakout': breakout, 'Pullback': pullback,
                                'Uptrend': last['close'] > last['EMA50']
                            })
                    except Exception as e:
                        continue

            details_df = pd.DataFrame(scan_results)

        if details_df.empty:
            st.warning("No data returned or error processing data.")
            return

        # Apply confidence score filter
        details_df = details_df[details_df['Score'] >= min_score]
        
        if details_df.empty:
            st.info(f"No assets meet your minimum confidence score of {min_score}.")
            return

        # Styling function for dataframe
        def color_score(val):
            color = 'rgba(144, 238, 144, 0.2)' if val >= 50 else 'rgba(255, 165, 0, 0.2)' if val >= 30 else 'rgba(240, 128, 128, 0.2)'
            return f'background-color: {color}'
        
        def color_rsi(val):
            color = 'rgba(240, 128, 128, 0.2)' if val >= 70 else 'rgba(144, 238, 144, 0.2)' if val <= 30 else ''
            return f'background-color: {color}'

        styled_df = details_df.style.map(color_score, subset=['Score']).map(color_rsi, subset=['RSI'])

        tab1, tab2, tab3, tab4, tab5 = st.tabs(["List View", "🚨 Alerts & Breakouts", "📈 Interactive Charts", "🧠 AI Ideas", "📰 Latest News"])
        link_config = {"Chart": st.column_config.LinkColumn("Chart", display_text="📈 View")}
        
        # Throw a toast notification for top alerts
        if not details_df.empty:
            alert_count = len(details_df[(details_df['Breakout']) | (details_df['Vol Anomaly'])])
            if alert_count > 0:
                st.toast(f"🚨 {alert_count} active setups found in {timeframe} timeframe for {'Crypto' if is_crypto else 'Stocks'}!")
                
                # Check webhook
                webhook_url = st.session_state.get("discord_webhook", "")
                if webhook_url and st.session_state.get("webhook_active", False):
                    # Prevent spamming the webhook
                    try:
                        message = f"**Trading Dashboard Alert!** 🚨\nFound {alert_count} active setups for {'Crypto' if is_crypto else 'Stocks'} on the `{timeframe}` timeframe."
                        requests.post(webhook_url, json={"content": message})
                    except:
                        pass

        with tab1:
            st.dataframe(styled_df, column_config=link_config, use_container_width=True, hide_index=True)
            
        with tab2:
            action_df = details_df[(details_df['Vol Anomaly']) | (details_df['Breakout']) | (details_df['Pullback'])]
            if not action_df.empty:
                styled_action_df = action_df.style.map(color_score, subset=['Score']).map(color_rsi, subset=['RSI'])
                st.dataframe(styled_action_df, column_config=link_config, use_container_width=True, hide_index=True)
            else:
                st.info("No active setups detected.")
            
        with tab3:
            st.subheader(f"Plotly Charts ({timeframe}) - Top 3 Movers")
            # Show charts for top 3
            top3 = details_df.head(3)['Symbol'].tolist()
            cols = st.columns(3)
            for idx, sym in enumerate(top3):
                with cols[idx]:
                    st.markdown(f"**{sym}**")
                    if sym in detailed_data:
                        df_plot = detailed_data[sym].tail(60) # Last 60 candles
                        fig = go.Figure(data=[go.Candlestick(x=df_plot['timestamp'],
                                        open=df_plot['open'], high=df_plot['high'],
                                        low=df_plot['low'], close=df_plot['close'])])
                        if 'VWAP' in df_plot:
                            fig.add_trace(go.Scatter(x=df_plot['timestamp'], y=df_plot['VWAP'], line=dict(color='orange', width=1), name='VWAP'))
                        fig.update_layout(height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, use_container_width=True)
                        
        with tab4:
            st.subheader("💡 AI Generated Trade Summaries (Top Setups)")
            # Sort by setups
            setup_candidates = details_df[(details_df['Breakout']) | (details_df['Pullback']) | (details_df['Vol Anomaly'])].head(5)
            
            if setup_candidates.empty:
                setup_candidates = details_df.head(5) # fallback to top gainers
                
            cols = st.columns(len(setup_candidates) if len(setup_candidates) > 0 else 1)
            for idx, (_, row) in enumerate(setup_candidates.iterrows()):
                with cols[idx]:
                    sym = row['Symbol']
                    st.markdown(f"### [{sym}]({row['Chart']})")
                    
                    if sym in st.session_state.ai_ideas:
                        st.info(st.session_state.ai_ideas[sym])
                        if st.button(f"Regenerate Idea", key=f"ai_regen_btn_{sym}_{timeframe}"):
                            with st.spinner("Analyzing..."):
                                idea = generate_ai_trade_idea(row)
                                st.session_state.ai_ideas[sym] = idea
                                st.rerun()
                    else:
                        if st.button(f"Generate AI Idea", key=f"ai_btn_{sym}_{timeframe}"):
                            with st.spinner("Analyzing..."):
                                idea = generate_ai_trade_idea(row)
                                st.session_state.ai_ideas[sym] = idea
                                st.rerun()
                                
        with tab5:
            st.subheader(f"📰 Live News Feed ({'Crypto is not supported yet' if is_crypto else 'Stocks'})")
            if not is_crypto:
                top_sym = details_df.iloc[0]['Symbol'] if not details_df.empty else "SPY"
                st.markdown(f"**Latest news for {top_sym} (Top Mover):**")
                
                news_items = fetch_market_news(top_sym)
                if news_items:
                    for item in news_items:
                        with st.expander(f"{item['Time']} | {item['Title']}"):
                            st.write(f"Source: {item['Publisher']}")
                            st.markdown(f"[Read Full Article]({item['Link']})")
                else:
                    st.info(f"No recent news found for {top_sym}.")

    with asset_tabs[0]:
        render_movers_section(fetch_top_binance_movers, fetch_ohlcv_data, '24h Vol (USDT)', is_crypto=True)
        
    with asset_tabs[1]:
        render_movers_section(fetch_top_stock_movers, fetch_stock_ohlcv_data, '24h Vol (USD)', is_crypto=False)

    st.divider()

    # --- 3. Trade Journal ---
    st.header("📓 Trade Journal & Quick Logs")
    with st.expander("Log a New Trade", expanded=False):
        with st.form("trade_form"):
            col_t1, col_t2, col_t3 = st.columns(3)
            with col_t1:
                t_date = st.date_input("Date")
                t_symbol = st.text_input("Symbol", "AAPL")
            with col_t2:
                t_side = st.selectbox("Side", ["LONG", "SHORT"])
                t_entry = st.number_input("Entry Price", value=0.0, format="%.4f")
            with col_t3:
                t_exit = st.number_input("Exit Price", value=0.0, format="%.4f")
                t_pnl = st.number_input("P&L ($)", value=0.0, format="%.2f")
            t_notes = st.text_input("Trade Notes (Setup, Emotions, etc.)")
            
            submitted = st.form_submit_button("Log Trade")
            if submitted:
                new_trade = pd.DataFrame([{
                    "Date": t_date,
                    "Symbol": t_symbol,
                    "Side": t_side,
                    "Entry Price": t_entry,
                    "Exit Price": t_exit,
                    "P&L": t_pnl,
                    "Notes": t_notes
                }])
                st.session_state.trades = pd.concat([st.session_state.trades, new_trade], ignore_index=True)
                st.success("Trade Logged Successfully!")
                st.rerun()

    # Editable dataframe to allow users to modify entries or delete them
    if not st.session_state.trades.empty:
        st.session_state.trades = st.data_editor(
            st.session_state.trades, 
            num_rows="dynamic",
            use_container_width=True,
            key="trade_editor"
        )
        
        # Display Quick Stats
        total_pnl = st.session_state.trades["P&L"].sum()
        win_rate = len(st.session_state.trades[st.session_state.trades["P&L"] > 0]) / len(st.session_state.trades) * 100 if len(st.session_state.trades) > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Trades Logged", len(st.session_state.trades))
        m2.metric("Total P&L ($)", f"${total_pnl:.2f}")
        m3.metric("Win Rate", f"{win_rate:.1f}%")
        
        # Export to CSV
        csv = st.session_state.trades.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Trade Journal as CSV",
            data=csv,
            file_name='trade_journal.csv',
            mime='text/csv',
        )

if __name__ == "__main__":
    main()
