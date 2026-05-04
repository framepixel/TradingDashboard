import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import json
from typing import Any
from datetime import datetime, timezone, timedelta, time as dt_time
import pandas_market_calendars as mcal
from data_fetcher import (
    fetch_tradfi_data, 
    fetch_top_binance_movers, 
    fetch_ohlcv_data,
    fetch_multi_timeframe_data,
    fetch_top_stock_movers,
    fetch_stock_ohlcv_data,
    fetch_stock_multi_timeframe_data,
    fetch_market_news
)
from technical_analysis import calculate_indicators, analyze_strategy, run_backtest
from ai_agent import generate_ai_trade_idea
from alpaca_trading import close_symbol_position, get_account_snapshot, get_recent_orders, submit_market_order

# ==========================================
# PAGE CONFIGURATION & INITIALIZATION
# ==========================================
st.set_page_config(page_title="Daily Trading Opportunity Dashboard", page_icon="📈", layout="wide")

# Try to import autorefresh for active traders
try:
    from streamlit_autorefresh import st_autorefresh
    # Auto-refresh every 10 minutes
    st_autorefresh(interval=600000, key="datarefresh")
except ImportError:
    pass

def get_market_info(calendar_name, market_name):
    now = datetime.now(timezone.utc)
    try:
        cal = mcal.get_calendar(calendar_name)
        today_date = now.strftime('%Y-%m-%d')
        # Get schedule for today and tomorrow to check next open
        schedule = cal.schedule(start_date=today_date, end_date=(now + timedelta(days=5)).strftime('%Y-%m-%d'))
        
        if schedule.empty:
            return f"🔴 {market_name}: CLOSED (Holiday/Weekend)"
            
        # Current day schedule
        schedule_index = pd.DatetimeIndex(schedule.index)
        today_schedule = schedule[schedule_index.date == now.date()]
        if today_schedule.empty:
            # It's weekend/holiday today, find next open
            next_open = schedule.iloc[0]['market_open']
            time_left = next_open - pd.Timestamp(now)
            hours, remainder = divmod(time_left.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            return f"🔴 {market_name}: CLOSED (Opens in {int(hours)}h {int(minutes)}m)"
            
        market_open = today_schedule.iloc[0]['market_open']
        market_close = today_schedule.iloc[0]['market_close']
        
        if pd.Timestamp(now) < market_open:
            time_left = market_open - pd.Timestamp(now)
            hours, remainder = divmod(time_left.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            return f"🔴 {market_name}: CLOSED (Opens in {int(hours)}h {int(minutes)}m)"
        elif market_open <= pd.Timestamp(now) <= market_close:
            time_left = market_close - pd.Timestamp(now)
            hours, remainder = divmod(time_left.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            return f"🟢 {market_name}: OPEN (Closes in {int(hours)}h {int(minutes)}m)"
        else:
            # Market closed for today, get tomorrow's open
            if len(schedule) > 1:
                next_open = schedule.iloc[1]['market_open']
                time_left = next_open - pd.Timestamp(now)
                hours, remainder = divmod(time_left.total_seconds(), 3600)
                minutes, _ = divmod(remainder, 60)
                return f"🔴 {market_name}: CLOSED (Opens in {int(hours)}h {int(minutes)}m)"
            else:
                return f"🔴 {market_name}: CLOSED"
    except Exception:
        return f"⚪ {market_name}: STATUS UNKNOWN"

def get_market_status():
    """Check if US and UK Markets are open"""
    us_status = get_market_info('NYSE', 'US Markets')
    uk_status = get_market_info('LSE', 'UK Markets')
    return f"{us_status}\n\n{uk_status}"

# ==========================================
# DASHBOARD UI
# ==========================================
def main():
    st.sidebar.title("⚙️ Settings")
    min_score = st.sidebar.slider("Minimum Confidence Score", 0, 100, 30, help="Filter setups by technical strength")
    selected_risk_tiers = st.sidebar.multiselect(
        "Risk tiers to include",
        options=["FRESH", "ESTABLISHED", "EXTENDED", "EXHAUSTED"],
        default=["FRESH", "ESTABLISHED", "EXTENDED"],
        help="Exhausted setups are excluded by default to avoid late entries."
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Market Status:**\n\n{get_market_status()}")
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
    # RISK & POSITION SIZING CALCULATOR
    # -----------------------------
    st.sidebar.title("⚖️ Risk Calculator")
    account_size = st.sidebar.number_input("Account Size ($)", min_value=100.0, value=10000.0, step=100.0)
    risk_pct = st.sidebar.slider("Risk per Trade (%)", 0.1, 5.0, 1.0, 0.1)
    
    calc_symbol = st.sidebar.text_input("Ticker to Calculate", "SPY").upper()
    if st.sidebar.button("Calculate Position Size"):
        try:
            # We assume the user wants the calculation on a daily timeframe by default
            df_risk = fetch_stock_ohlcv_data(calc_symbol, '1d')
            if df_risk is not None and not df_risk.empty:
                df_risk = calculate_indicators(df_risk)
                current_price = df_risk.iloc[-1]['close']
                atr = df_risk.iloc[-1]['ATR']
                
                if pd.notna(atr) and atr > 0:
                    risk_amount = account_size * (risk_pct / 100)
                    # Stop loss placed at 1.5x ATR below entry
                    stop_loss_dist = atr * 1.5
                    position_size = risk_amount / stop_loss_dist
                    total_capital_needed = position_size * current_price
                    
                    st.sidebar.info(f"**Price:** ${current_price:.2f}\n\n"
                                    f"**Risk Amount:** ${risk_amount:.2f}\n\n"
                                    f"**Suggested SL:** ${current_price - stop_loss_dist:.2f} ({stop_loss_dist:.2f} pt)\n\n"
                                    f"**Shares to Buy:** {position_size:.2f}\n\n"
                                    f"**Capital Rec:** ${total_capital_needed:.2f}")
                else:
                    st.sidebar.warning("Not enough data to calculate ATR.")
            else:
                st.sidebar.error("Could not fetch data for ticker.")
        except Exception as e:
            st.sidebar.error("Error calculating risk.")

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
    st.header("📊 Market Overview & Breadth")
    tradfi = fetch_tradfi_data()
    btc_df = calculate_indicators(fetch_ohlcv_data('BTC/USDT', '1d'))
    eth_df = calculate_indicators(fetch_ohlcv_data('ETH/USDT', '1d'))
    
    top_stocks = fetch_top_stock_movers()
    market_breadth = "N/A"
    breadth_delta = None
    delta_color = "off"
    
    if not top_stocks.empty:
        advancing = len(top_stocks[top_stocks['24h Change (%)'] > 0])
        declining = len(top_stocks[top_stocks['24h Change (%)'] < 0])
        total = advancing + declining
        if total > 0:
            breadth_pct = (advancing / total) * 100
            
            if breadth_pct >= 60:
                breadth_delta = "Bullish Tracker"
                delta_color = "normal"
            elif breadth_pct <= 40:
                breadth_delta = "-Bearish Tracker"
                delta_color = "normal"
            else:
                breadth_delta = "Neutral"
                delta_color = "off"
                
            market_breadth = f"{advancing} Adv / {declining} Dec"

    c1, c2, c3, c4, c5 = st.columns(5)
    
    def get_trend(df):
        if df is None or len(df) == 0 or 'EMA50' not in df:
            return "Unknown"
        return "Bullish 📈" if df.iloc[-1]['close'] > df.iloc[-1]['EMA50'] else "-Bearish 📉"
        
    c1.metric("S&P 500", f"{tradfi.get('S&P 500', {}).get('close', 0):.2f}", f"{tradfi.get('S&P 500', {}).get('change', 0):.2f}%")
    
    c2.metric("NASDAQ", f"{tradfi.get('NASDAQ', {}).get('close', 0):.2f}", f"{tradfi.get('NASDAQ', {}).get('change', 0):.2f}%")
    
    btc_price = f"${btc_df.iloc[-1]['close']:.2f}" if btc_df is not None and not btc_df.empty else "N/A"
    c3.metric("Bitcoin (BTC)", btc_price, get_trend(btc_df))
    
    eth_price = f"${eth_df.iloc[-1]['close']:.2f}" if eth_df is not None and not eth_df.empty else "N/A"
    c4.metric("Ethereum (ETH)", eth_price, get_trend(eth_df))

    c5.metric("Top Equity Breadth", market_breadth, breadth_delta, delta_color=delta_color)

    st.divider()

    # --- 2. Top Movers & Scans ---
    st.header("🔥 Top Movers & Setups (24h)")
    
    asset_tabs = st.tabs(["🪙 Crypto", "📈 Stocks"])
    
    def render_movers_section(fetch_movers_func, fetch_multi_func, volume_label, is_crypto):
        with st.spinner(f"Fetching market data (1w, 1d, 4h)..."):
            top_pairs = fetch_movers_func()
            
            scan_results = []
            detailed_data = {}

            if not top_pairs.empty:
                for _, row in top_pairs.iterrows():
                    try:
                        sym = row['Symbol']
                        multi_data = fetch_multi_func(sym)
                        df_w = calculate_indicators(multi_data.get('1w'))
                        df_d = calculate_indicators(multi_data.get('1d'))
                        df_4h = calculate_indicators(multi_data.get('4h'))
                        
                        if df_w is not None and df_d is not None and df_4h is not None and not df_w.empty and not df_d.empty and not df_4h.empty and 'EMA50' in df_d.columns and 'RSI' in df_d.columns:
                            detailed_data[sym] = df_d
                            
                            vol_anomaly, breakout, pullback, score, patterns, risk_tier, risk_flags, bias_label = analyze_strategy(df_w, df_d, df_4h)
                            last = df_d.iloc[-1]

                            trend_pattern = next((p for p in patterns if p.startswith("Trend Aligned")), None)
                            if trend_pattern and "(" in trend_pattern and ")" in trend_pattern:
                                trend_alignment = trend_pattern.split("(", 1)[1].rstrip(")")
                            else:
                                trend_alignment = "None"

                            aoi_validation = "AOI Validation" in patterns
                            hs_aligned = "H&S Aligned" in patterns
                            candle_confirm = "Candle Confirm" in patterns
                            
                            tv_symbol = ('BINANCE:' + sym.replace('/', '')) if is_crypto else sym
                            chart_link = f"https://www.tradingview.com/chart/?symbol={tv_symbol}#{sym}"
                            raw_volume = row.get('24h Volume (USDT)', row.get('24h Volume (USD)', 0))
                            if raw_volume >= 1e9:
                                vol = f"${raw_volume/1e9:.3f}B"
                            else:
                                vol = f"${raw_volume/1e6:.3f}M"
                            
                            scan_results.append({
                                'Asset': chart_link, 'Symbol': sym, 'Price': row['Price'],
                                '24h Change (%)': row['24h Change (%)'], 'Volume': vol,
                                'Score': score, 'Quality Score': score,
                                'RSI': last['RSI'], 'MACD_Hist': last['MACD_Hist'] if 'MACD_Hist' in last else 0,
                                'Trend Aligned': trend_alignment,
                                'AOI Validation': aoi_validation,
                                'H&S Aligned': hs_aligned,
                                'Candle Confirm': candle_confirm,
                                'Vol Anomaly': vol_anomaly, 'Breakout': breakout, 'Pullback': pullback,
                                'Uptrend': last['close'] > last['EMA50'],
                                'Risk Tier': risk_tier,
                                'Risk Flags': ", ".join(risk_flags) if risk_flags else "-",
                                '4h Context': bias_label,
                                'Raw Volume': raw_volume
                            })
                    except Exception as e:
                        continue

            details_df = pd.DataFrame(scan_results)

        if details_df.empty:
            st.warning("No data returned or error processing data.")
            return

        # Apply risk-tier and confidence filters.
        if selected_risk_tiers:
            details_df = details_df[details_df['Risk Tier'].isin(selected_risk_tiers)]
        details_df = details_df[details_df['Quality Score'] >= min_score]

        # Prioritize quality first, then liquidity.
        details_df = details_df.sort_values(by=['Quality Score', 'Raw Volume'], ascending=[False, False])
        
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

        bool_cols = {'AOI Validation', 'H&S Aligned', 'Candle Confirm', 'Vol Anomaly', 'Breakout', 'Pullback', 'Uptrend'}

        def format_price(val):
            if pd.isna(val):
                return "-"
            value = float(val)
            decimals = 6 if 0 < abs(value) < 1 else 3
            return f"{value:,.{decimals}f}"

        def format_3dp(val):
            if pd.isna(val):
                return "-"
            return f"{float(val):,.3f}"

        def format_quality_score(val):
            if pd.isna(val):
                return "-"
            value = float(val)
            if value.is_integer():
                return f"{int(value):,}"
            return f"{value:,.3f}"

        formatters: dict[str, Any] = {
            'Price': format_price,
            '24h Change (%)': format_3dp,
            'Quality Score': format_quality_score,
            'RSI': format_3dp,
            'MACD_Hist': format_3dp,
        }

        def display_text(col_name, val):
            if col_name in formatters:
                return formatters[col_name](val)
            if col_name in bool_cols:
                return "True" if bool(val) else "False"
            if pd.isna(val):
                return "-"
            return str(val)

        def adaptive_width(header_label, col_name, series):
            # Make the column wide enough for the longest displayed string (including header).
            max_len = len(str(header_label))
            for value in series:
                max_len = max(max_len, len(display_text(col_name, value)))
            # Compact fit: minimal padding while preserving full header/value visibility.
            return int(max(44, (max_len * 8.0) + 8))

        def build_styler(df):
            return (
                df.style
                .map(color_score, subset=['Quality Score'])
                .map(color_rsi, subset=['RSI'])
                .format(formatters)
                .set_properties(**{'text-align': 'left'})
                .set_table_styles(
                    [
                        {'selector': 'th', 'props': [('text-align', 'left')]},
                        {'selector': 'td', 'props': [('text-align', 'left')]},
                    ],
                    overwrite=False,
                )
            )

        display_columns = [
            'Asset', 'Price', '24h Change (%)', 'Volume', 'Quality Score',
            'Trend Aligned', 'AOI Validation', 'H&S Aligned', 'Candle Confirm',
            'RSI', 'MACD_Hist', 'Vol Anomaly', 'Breakout', 'Pullback', 'Uptrend',
            'Risk Tier', 'Risk Flags', '4h Context'
        ]
        list_view_df = details_df[display_columns]
        styled_df = build_styler(list_view_df)

        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["List View", "🚨 Alerts & Breakouts", "📈 Interactive Charts", "🧠 AI Ideas", "📰 Latest News", "🧪 Backtest Engine"])
        column_widths = {
            col: adaptive_width("Symbol" if col == 'Asset' else col, col, details_df['Symbol'] if col == 'Asset' else list_view_df[col])
            for col in display_columns
        }
        link_config = {
            "Asset": st.column_config.LinkColumn(
                "Symbol",
                display_text=r"https://www\.tradingview\.com/chart/\?symbol=[^#]+#(.+)",
                width=column_widths['Asset']
            )
        }
        table_column_config = {
            **link_config,
            **{
                col: st.column_config.Column(col, width=column_widths[col])
                for col in display_columns if col != 'Asset'
            }
        }
        
        # Throw a toast notification for top alerts
        if not details_df.empty:
            alert_df = details_df[
                ((details_df['Breakout']) | (details_df['Vol Anomaly']) | (details_df['Pullback'])) &
                (details_df['Risk Tier'].isin(["FRESH", "ESTABLISHED"])) &
                (details_df['Quality Score'] >= max(min_score, 45))
            ]
            alert_count = len(alert_df)
            if alert_count > 0:
                st.toast(f"🚨 {alert_count} active setups found for {'Crypto' if is_crypto else 'Stocks'}!")
                
                # Check webhook
                webhook_url = st.session_state.get("discord_webhook", "")
                if webhook_url and st.session_state.get("webhook_active", False):
                    # Prevent spamming the webhook
                    try:
                        top_alert_lines = []
                        for _, r in alert_df.head(3).iterrows():
                            top_alert_lines.append(
                                f"- {r['Symbol']} | Tier: {r['Risk Tier']} | Score: {int(r['Quality Score'])} | Flags: {r['Risk Flags']}"
                            )
                        details_block = "\n".join(top_alert_lines)
                        message = (
                            f"**Trading Dashboard Alert!** 🚨\n"
                            f"Found {alert_count} qualified setups for {'Crypto' if is_crypto else 'Stocks'}.\n"
                            f"{details_block}"
                        )
                        requests.post(webhook_url, json={"content": message})
                    except:
                        pass

        with tab1:
            st.dataframe(styled_df, column_config=table_column_config, width='content', hide_index=True)
            
        with tab2:
            action_df = details_df[(details_df['Vol Anomaly']) | (details_df['Breakout']) | (details_df['Pullback'])]
            if not action_df.empty:
                action_view_df = action_df[display_columns]
                styled_action_df = build_styler(action_view_df)
                st.dataframe(styled_action_df, column_config=table_column_config, width='content', hide_index=True)
            else:
                st.info("No active setups detected.")
            
        with tab3:
            st.subheader(f"Plotly Charts (Daily) - Top 3 Movers")
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
                        st.plotly_chart(fig, width='content')
                        
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
                    st.markdown(f"### [{sym}]({row['Asset']})")
                    
                    if sym in st.session_state.ai_ideas:
                        st.info(st.session_state.ai_ideas[sym])
                        if st.button(f"Regenerate Idea", key=f"ai_regen_btn_{sym}"):
                            with st.spinner("Analyzing..."):
                                idea = generate_ai_trade_idea(row)
                                st.session_state.ai_ideas[sym] = idea
                                st.rerun()
                    else:
                        if st.button(f"Generate AI Idea", key=f"ai_btn_{sym}"):
                            with st.spinner("Analyzing..."):
                                idea = generate_ai_trade_idea(row)
                                st.session_state.ai_ideas[sym] = idea
                                st.rerun()
                                
        with tab5:
            st.subheader(f"📰 Live News Feed ({'Crypto' if is_crypto else 'Stocks'})")
            if is_crypto:
                st.markdown("**Search for any cryptocurrency news:**")
                # Give user the option to check any crypto news, not strictly dependent on top movers
                news_sym = st.text_input("Crypto Symbol (e.g. BTC-USD, ETH-USD):", value="BTC-USD", key=f"crypto_news_1d")
                news_items = fetch_market_news(news_sym)
                if news_items:
                    for item in news_items:
                        with st.expander(f"{item['Time']} | {item['Title']}"):
                            st.write(f"Source: {item['Publisher']}")
                            st.markdown(f"[Read Full Article]({item['Link']})")
                else:
                    st.info(f"No recent news found for {news_sym}.")
            else:
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

        with tab6:
            st.subheader(f"🧪 Quick Backtester (Daily Timeframe)")
            st.markdown("Tests how successful the **Breakout Setup** has been on this ticker historically when holding for 5 candles.")
            
            backtest_results = []
            
            for sym, df in detailed_data.items():
                if sym in details_df['Symbol'].values:
                    trades, wr, pnl = run_backtest(df, 'Signal_Breakout', hold_period=5)
                    row_match = details_df[details_df['Symbol'] == sym]
                    if row_match.empty:
                        continue
                    first_row = row_match.iloc[0]
                    risk_tier = first_row['Risk Tier']
                    quality_score = first_row['Quality Score']
                    backtest_results.append({
                        "Symbol": sym,
                        "Risk Tier": risk_tier,
                        "Quality Score": quality_score,
                        "Historical Trades": trades,
                        "Win Rate (%)": wr,
                        "Total Return (%)": pnl
                    })
                    
            bt_df = pd.DataFrame(backtest_results)
            if not bt_df.empty:
                # Sort by win rate and highlight
                bt_df = bt_df.sort_values(by="Win Rate (%)", ascending=False)
                
                def color_wr(val):
                    color = 'rgba(144, 238, 144, 0.2)' if val >= 55 else 'rgba(240, 128, 128, 0.2)' if val < 40 else ''
                    return f'background-color: {color}'
                    
                st.dataframe(bt_df.style.map(color_wr, subset=['Win Rate (%)'])
                                     .format({'Win Rate (%)': '{:.1f}%', 'Total Return (%)': '{:.2f}%'}),
                             width='content', hide_index=True)
            else:
                st.info("Not enough data to run backtests.")

    with asset_tabs[0]:
        render_movers_section(fetch_top_binance_movers, fetch_multi_timeframe_data, '24h Vol (USDT)', is_crypto=True)
        
    with asset_tabs[1]:
        render_movers_section(fetch_top_stock_movers, fetch_stock_multi_timeframe_data, '24h Vol (USD)', is_crypto=False)

    st.divider()

    # --- 3. Alpaca Trade Execution ---
    st.header("🦙 Alpaca Trade Execution")

    alpaca_snapshot = get_account_snapshot()

    last_order_result = st.session_state.pop("alpaca_last_order_result", None)
    if last_order_result:
        if last_order_result.get("ok"):
            order = last_order_result.get("order", {})
            order_size_label = last_order_result.get("order_size_label", "shares")
            order_size_value = last_order_result.get("order_size_value", order.get("qty", "n/a"))
            if order_size_label == "notional_usd":
                order_size_text = f"${float(order_size_value):,.2f}"
            else:
                order_size_text = f"{order_size_value} shares"
            bracket_text = ""
            tp_value = order.get("take_profit")
            sl_value = order.get("stop_loss")
            if tp_value is not None and sl_value is not None:
                bracket_text = f" | TP: ${float(tp_value):,.2f}, SL: ${float(sl_value):,.2f}"
            st.success(
                f"Submitted {order.get('side', 'order')} order for {order.get('symbol', 'unknown symbol')} "
                f"({order_size_text}) in {last_order_result.get('mode_label', 'Alpaca')}.{bracket_text}"
            )
        else:
            st.error(last_order_result.get("error", "Unable to submit Alpaca order."))

    last_close_result = st.session_state.pop("alpaca_last_close_result", None)
    if last_close_result:
        if last_close_result.get("ok"):
            close_order = last_close_result.get("order", {})
            close_qty = close_order.get("qty")
            if close_qty is None:
                close_size_text = "full position"
            else:
                close_size_text = f"{close_qty} shares"
            st.success(
                f"Close-all request sent for {last_close_result.get('symbol', 'symbol')} "
                f"({close_size_text}) in {last_close_result.get('mode_label', 'Alpaca')}."
            )
        else:
            st.error(last_close_result.get("error", "Unable to close position."))

    if alpaca_snapshot.get("ok"):
        if alpaca_snapshot.get("paper"):
            st.info("Connected to an Alpaca paper trading account.")
        else:
            st.warning("Connected to an Alpaca live trading account. Orders will route to the live broker.")
    else:
        st.warning(alpaca_snapshot.get("error", "Set ALPACA_API_KEY and ALPACA_API_SECRET to enable trading."))

    def format_money(value):
        return f"${value:,.2f}" if value is not None else "N/A"

    alpaca_metrics = st.columns(4)
    alpaca_metrics[0].metric("Account Mode", alpaca_snapshot.get("mode_label", "Unavailable"), "Connected" if alpaca_snapshot.get("ok") else "Disconnected")
    alpaca_metrics[1].metric("Equity", format_money(alpaca_snapshot.get("equity")), f"Status: {alpaca_snapshot.get('status', 'N/A') or 'N/A'}")
    alpaca_metrics[2].metric("Buying Power", format_money(alpaca_snapshot.get("buying_power")), f"Currency: {alpaca_snapshot.get('currency', 'USD')}")
    alpaca_metrics[3].metric("Cash", format_money(alpaca_snapshot.get("cash")), f"Blocked: {'Yes' if alpaca_snapshot.get('trading_blocked') else 'No'}")

    exec_col, history_col = st.columns([1, 1.4])

    with exec_col:
        st.subheader("Submit Market Order")
        with st.form("alpaca_order_form"):
            order_symbol = st.text_input("Symbol", value="AAPL").upper().strip()
            order_side = st.selectbox("Side", ["BUY", "SELL"])

            reference_price = None
            if order_symbol:
                try:
                    ref_df = fetch_stock_ohlcv_data(order_symbol, '1d')
                    if ref_df is not None and not ref_df.empty:
                        reference_price = float(ref_df.iloc[-1]['close'])
                except Exception:
                    reference_price = None

            if reference_price is not None:
                st.caption(f"Reference buy price for checks: ${reference_price:,.2f}")

            order_size_mode = st.radio("Order size", ["Shares", "USD Notional"], horizontal=True, index=1)
            if order_size_mode == "Shares":
                order_qty_label = "Quantity (shares)"
                order_qty = st.number_input(order_qty_label, min_value=1.0, value=1.0, step=1.0, format="%.2f")
                order_notional = None
            else:
                order_qty = None
                order_qty_label = "Quantity (USD)"
                order_notional = st.number_input(order_qty_label, min_value=1.0, value=100.0, step=10.0, format="%.2f")

            tp_col, sl_col = st.columns(2)
            with tp_col:
                take_profit_input = st.text_input("Take Profit Price (optional)", value="", placeholder="e.g. 110.50")
            with sl_col:
                stop_loss_input = st.text_input("Stop Loss Price (optional)", value="", placeholder="e.g. 95.25")

            if alpaca_snapshot.get("ok") and not alpaca_snapshot.get("paper"):
                live_ack = st.checkbox("I understand this submits LIVE orders.", key="alpaca_live_ack")
            else:
                live_ack = True

            can_submit = bool(alpaca_snapshot.get("ok")) and (alpaca_snapshot.get("paper") or live_ack)
            submit_order = st.form_submit_button("Submit Market Order", disabled=not can_submit)

            if submit_order:
                parse_error = None
                take_profit_price = None
                stop_loss_price = None

                if take_profit_input.strip():
                    try:
                        take_profit_price = float(take_profit_input)
                    except ValueError:
                        parse_error = "Take Profit must be a valid number."

                if stop_loss_input.strip() and parse_error is None:
                    try:
                        stop_loss_price = float(stop_loss_input)
                    except ValueError:
                        parse_error = "Stop Loss must be a valid number."

                if parse_error:
                    st.error(parse_error)
                else:
                    result = submit_market_order(
                        order_symbol,
                        order_side,
                        quantity=float(order_qty) if order_qty is not None else None,
                        notional=float(order_notional) if order_notional is not None else None,
                        take_profit=float(take_profit_price) if take_profit_price is not None else None,
                        stop_loss=float(stop_loss_price) if stop_loss_price is not None else None,
                        reference_price=reference_price,
                    )
                    st.session_state.alpaca_last_order_result = result
                    st.rerun()

        with st.form("alpaca_close_position_form"):
            st.markdown("#### Sell All Shares of One Stock")
            close_symbol = st.text_input("Symbol to close", value="AAPL").upper().strip()

            if alpaca_snapshot.get("ok") and not alpaca_snapshot.get("paper"):
                close_live_ack = st.checkbox("I understand this closes the full LIVE position.", key="alpaca_close_live_ack")
            else:
                close_live_ack = True

            can_close = bool(alpaca_snapshot.get("ok")) and (alpaca_snapshot.get("paper") or close_live_ack)
            close_all_submit = st.form_submit_button("Sell All (Close Position)", disabled=not can_close)

            if close_all_submit:
                close_result = close_symbol_position(close_symbol)
                st.session_state.alpaca_last_close_result = close_result
                st.rerun()

        if not alpaca_snapshot.get("ok"):
            st.caption("The order form stays disabled until Alpaca credentials are available and authenticated.")

    with history_col:
        st.subheader("Recent Alpaca Orders")
        recent_orders = get_recent_orders(limit=10)
        if recent_orders.get("ok"):
            order_rows = []
            for order in recent_orders.get("orders", []):
                submitted_at = order.get("submitted_at")
                if submitted_at is not None:
                    submitted_at_text = submitted_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                else:
                    submitted_at_text = "-"

                order_rows.append({
                    "Symbol": order.get("symbol", "-"),
                    "Side": str(order.get("side", "-")),
                    "Qty": order.get("qty", "-"),
                    "Notional": order.get("notional", "-"),
                    "Type": order.get("order_type", "-"),
                    "Status": order.get("status", "-"),
                    "Filled Avg Price": order.get("filled_avg_price", "-"),
                    "Submitted At (UTC)": submitted_at_text,
                })

            orders_df = pd.DataFrame(order_rows)
            if not orders_df.empty:
                st.dataframe(orders_df, width='content', hide_index=True)
            else:
                st.info("No Alpaca orders found yet.")
        else:
            st.warning(recent_orders.get("error", "Unable to load recent Alpaca orders."))

    st.divider()

    # --- 4. Trade Journal ---
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
        # Display Quick Stats
        total_pnl = st.session_state.trades["P&L"].sum()
        win_rate = len(st.session_state.trades[st.session_state.trades["P&L"] > 0]) / len(st.session_state.trades) * 100 if len(st.session_state.trades) > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Trades Logged", len(st.session_state.trades))
        m2.metric("Total P&L ($)", f"${total_pnl:.2f}")
        m3.metric("Win Rate", f"{win_rate:.1f}%")

        # Layout: Journal Table on Left, Equity Curve on Right
        col_table, col_chart = st.columns([1.5, 1])
        
        with col_table:
            st.session_state.trades = st.data_editor(
                st.session_state.trades, 
                num_rows="dynamic",
                width='content',
                key="trade_editor"
            )
            # Export to CSV
            csv = st.session_state.trades.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Trade Journal as CSV",
                data=csv,
                file_name='trade_journal.csv',
                mime='text/csv',
            )
            
        with col_chart:
            if len(st.session_state.trades) > 0:
                # Assuming index is chronological, calculate cumulative PnL
                chart_df = st.session_state.trades.copy()
                chart_df['Cumulative P&L'] = chart_df['P&L'].cumsum()
                
                fig_eq = go.Figure()
                fig_eq.add_trace(go.Scatter(
                    y=chart_df['Cumulative P&L'],
                    mode='lines+markers',
                    name='Equity Curve',
                    line=dict(color='royalblue', width=3),
                    marker=dict(size=6)
                ))
                fig_eq.update_layout(
                    title="Cumulative P&L (Equity Curve)",
                    xaxis_title="Trade #",
                    yaxis_title="Profit & Loss ($)",
                    margin=dict(l=0, r=0, t=40, b=0),
                    height=350
                )
                st.plotly_chart(fig_eq, width='content')

if __name__ == "__main__":
    main()
