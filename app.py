import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_fetcher import (
    fetch_tradfi_data, 
    fetch_top_binance_movers, 
    fetch_ohlcv_data,
    fetch_top_stock_movers,
    fetch_stock_ohlcv_data
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

# ==========================================
# DASHBOARD UI
# ==========================================
def main():
    st.sidebar.title("⚙️ Settings")
    timeframe = st.sidebar.radio("Select Timeframe:", ["1m", "5m", "15m", "1h", "1d"], index=1)
    
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
        if df is None or len(df) == 0:
            return "Unknown"
        return "Bullish 📈" if df.iloc[-1]['close'] > df.iloc[-1]['EMA50'] else "-Bearish 📉"
        
    c1.metric("S&P 500", f"{tradfi.get('S&P 500', {}).get('close', 0):.2f}", f"{tradfi.get('S&P 500', {}).get('change', 0):.2f}%")
    c1.markdown("[📈 Chart](https://www.tradingview.com/chart/?symbol=SP%3ASPX)")
    
    c2.metric("NASDAQ", f"{tradfi.get('NASDAQ', {}).get('close', 0):.2f}", f"{tradfi.get('NASDAQ', {}).get('change', 0):.2f}%")
    c2.markdown("[📈 Chart](https://www.tradingview.com/chart/?symbol=NASDAQ%3AIXIC)")
    
    c3.metric("Bitcoin (BTC)", f"${btc_df.iloc[-1]['close']:.2f}", get_trend(btc_df))
    c3.markdown("[📈 Chart](https://www.tradingview.com/chart/?symbol=BINANCE%3ABTCUSDT)")
    
    c4.metric("Ethereum (ETH)", f"${eth_df.iloc[-1]['close']:.2f}", get_trend(eth_df))
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
                            vol_anomaly, breakout, pullback = analyze_strategy(df_ta)
                            last = df_ta.iloc[-1]
                            
                            chart_link = f"https://www.tradingview.com/chart/?symbol={'BINANCE:' + sym.replace('/', '') if is_crypto else sym}"
                            vol = f"${row.get('24h Volume (USDT)', row.get('24h Volume (USD)', 0))/1e6:.1f}M"
                            
                            scan_results.append({
                                'Chart': chart_link, 'Symbol': sym, 'Price': row['Price'],
                                '24h Change (%)': row['24h Change (%)'], 'Volume': vol,
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

        tab1, tab2, tab3, tab4 = st.tabs(["List View", "🚨 Alerts & Breakouts", "📈 Interactive Charts", "🧠 AI Ideas"])
        link_config = {"Chart": st.column_config.LinkColumn("Chart", display_text="📈 View")}
        
        # Throw a toast notification for top alerts
        if not details_df.empty:
            alert_count = len(details_df[(details_df['Breakout']) | (details_df['Vol Anomaly'])])
            if alert_count > 0:
                st.toast(f"🚨 {alert_count} active setups found in {timeframe} timeframe for {'Crypto' if is_crypto else 'Stocks'}!")

        with tab1:
            st.dataframe(details_df, column_config=link_config, width='stretch', hide_index=True)
            
        with tab2:
            action_df = details_df[(details_df['Vol Anomaly']) | (details_df['Breakout']) | (details_df['Pullback'])]
            st.dataframe(action_df, column_config=link_config, width='stretch', hide_index=True) if not action_df.empty else st.info("No active setups detected.")
            
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
                        st.plotly_chart(fig, width='stretch')
                        
        with tab4:
            st.subheader("💡 AI Generated Trade Summaries (Top 5 Setups)")
            # Sort by setups
            setup_candidates = details_df[(details_df['Breakout']) | (details_df['Pullback']) | (details_df['Vol Anomaly'])].head(5)
            
            if setup_candidates.empty:
                setup_candidates = details_df.head(5) # fallback to top gainers
                
            cols = st.columns(len(setup_candidates))
            for idx, (_, row) in enumerate(setup_candidates.iterrows()):
                with cols[idx]:
                    st.markdown(f"### [{row['Symbol']}]({row['Chart']})")
                    with st.spinner("Analyzing..."):
                        idea = generate_ai_trade_idea(row)
                        st.info(idea)

    with asset_tabs[0]:
        render_movers_section(fetch_top_binance_movers, fetch_ohlcv_data, '24h Vol (USDT)', is_crypto=True)
        
    with asset_tabs[1]:
        render_movers_section(fetch_top_stock_movers, fetch_stock_ohlcv_data, '24h Vol (USD)', is_crypto=False)

if __name__ == "__main__":
    main()
