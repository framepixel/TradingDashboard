import streamlit as st
import ccxt
import pandas as pd
import yfinance as yf

# Initialize Binance exchange
exchange = ccxt.binance({
    'enableRateLimit': True,
})

@st.cache_data(ttl=900) # Cache for 15 minutes
def fetch_tradfi_data():
    """Fetch S&P500 and NASDAQ daily change using yfinance"""
    indices = {"S&P 500": "^GSPC", "NASDAQ": "^IXIC"}
    data = {}
    for name, ticker in indices.items():
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                curr_close = hist['Close'].iloc[-1]
                pct_change = ((curr_close - prev_close) / prev_close) * 100
                data[name] = {"close": curr_close, "change": pct_change}
        except Exception as e:
            data[name] = {"close": 0, "change": 0}
    return data

@st.cache_data(ttl=300) # Cache for 5 minutes
def fetch_top_binance_movers():
    """Fetch all USDT pairs, rank by 24h volume and % change."""
    try:
        tickers = exchange.fetch_tickers()
        usdt_pairs = []
        for symbol, ticker in tickers.items():
            if symbol.endswith('/USDT') and 'percentage' in ticker and ticker['percentage'] is not None:
                usdt_pairs.append({
                    'Symbol': symbol,
                    'Price': ticker['last'],
                    '24h Change (%)': ticker['percentage'],
                    '24h Volume (USDT)': ticker['quoteVolume']
                })
        df = pd.DataFrame(usdt_pairs)
        # Filter dust and sort by % change
        df = df[df['24h Volume (USDT)'] > 1000000] # Min $1M volume
        top_gainers = df.sort_values(by='24h Change (%)', ascending=False).head(20)
        return top_gainers
    except Exception as e:
        st.error(f"Error fetching tickers: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_ohlcv_data(symbol, timeframe='1h', limit=100):
    """Fetch OHLCV data for a specific symbol"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        return None
