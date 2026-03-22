import streamlit as st
import pandas as pd
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

# ==========================================
# DASHBOARD UI
# ==========================================
def main():
    st.title("🚀 Daily Trading Opportunity Dashboard")
    st.markdown("Scans the market for volume anomalies, breakouts, and pullbacks.")
    
    # Auto-refresh logic
    col1, col2 = st.columns([8, 1])
    with col2:
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()

    # --- 1. Market Overview ---
    st.header("📊 Market Overview")
    tradfi = fetch_tradfi_data()
    btc_df = calculate_indicators(fetch_ohlcv_data('BTC/USDT', '1d'))
    eth_df = calculate_indicators(fetch_ohlcv_data('ETH/USDT', '1d'))
    
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
        with st.spinner("Fetching market data and scanning..."):
            top_pairs = fetch_movers_func()
            
            scan_results = []
            if not top_pairs.empty:
                for _, row in top_pairs.iterrows():
                    try:
                        sym = row['Symbol']
                        df = fetch_ohlcv_func(sym, '1h')
                        df_ta = calculate_indicators(df)
                        
                        # Ensure we have enough data (EMA50 requires min data)
                        if df_ta is not None and not df_ta.empty and 'EMA50' in df_ta.columns and 'RSI' in df_ta.columns:
                            vol_anomaly, breakout, pullback = analyze_strategy(df_ta)
                            last = df_ta.iloc[-1]
                            
                            # Dynamic tv chart link formulation
                            if is_crypto:
                                chart_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{sym.replace('/', '')}"
                                vol = f"${row.get('24h Volume (USDT)', 0)/1e6:.1f}M"
                            else:
                                chart_link = f"https://www.tradingview.com/chart/?symbol={sym}"
                                vol = f"${row.get('24h Volume (USDT)', 0)/1e6:.1f}M"  # fallback key used in fetch_top_stock_movers
                            
                            scan_results.append({
                                'Chart': chart_link,
                                'Symbol': sym,
                                'Price': row['Price'],
                                '24h Change (%)': row['24h Change (%)'],
                                volume_label: vol,
                                'RSI': last['RSI'],
                                'Vol Anomaly': vol_anomaly,
                                'Breakout': breakout,
                                'Pullback': pullback,
                                'Uptrend': last['close'] > last['EMA50']
                            })
                    except Exception as e:
                        continue # Skip to next asset if there's any formatting error for this one

            details_df = pd.DataFrame(scan_results)

        if details_df.empty:
            st.warning("No data returned or error processing data.")
            return

        # Tabs for different views
        tab1, tab2, tab3 = st.tabs(["All Top Gainers", "🚨 Anomalies & Breakouts", "🧠 AI Trade Ideas"])
        
        link_config = {"Chart": st.column_config.LinkColumn("Chart", display_text="📈 View")}
        
        with tab1:
            st.dataframe(details_df.style.format({'24h Change (%)': '{:.2f}%', 'RSI': '{:.1f}', 'Price': '{:.6f}'}), column_config=link_config, width='stretch')
            
        with tab2:
            action_df = details_df[(details_df['Vol Anomaly']) | (details_df['Breakout']) | (details_df['Pullback'])]
            if not action_df.empty:
                st.dataframe(action_df, column_config=link_config, width='stretch')
            else:
                st.info("No immediate breakouts or anomalies detected in the top gainers right now.")
                
        with tab3:
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
