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
    """Fetch OHLCV data for a specific crypto symbol"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        return None

@st.cache_data(ttl=300)
def fetch_top_stock_movers():
    """Fetch 24h change for popular stocks."""
    tickers = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AMD', 'INTC', 'NFLX', 
               'WMT', 'JPM', 'V', 'LLY', 'AVGO', 'COST', 'JNJ', 'ORCL', 'CRM', 'BAC']
    stock_pairs = []
    
    for symbol in tickers:
        try:
            hist = yf.Ticker(symbol).history(period="5d")
            if not hist.empty and len(hist) >= 2:
                prev_close = float(hist['Close'].iloc[-2])
                curr_close = float(hist['Close'].iloc[-1])
                volume = float(hist['Volume'].iloc[-1])
                pct_change = ((curr_close - prev_close) / prev_close) * 100
                
                stock_pairs.append({
                    'Symbol': symbol,
                    'Price': curr_close,
                    '24h Change (%)': pct_change,
                    '24h Volume (USDT)': volume * curr_close # approx dollar volume
                })
        except Exception as e:
            continue
            
    df = pd.DataFrame(stock_pairs)
    if not df.empty:
        df = df.sort_values(by='24h Change (%)', ascending=False).head(20)
    return df

@st.cache_data(ttl=300)
def fetch_stock_ohlcv_data(symbol, timeframe='1h', limit=100):
    """Fetch OHLCV data for a specific stock"""
    try:
        # Increase period to 3mo to guarantee we get at least 100 1-hour candles even around holidays/weekends
        interval_map = {'1h': '1h', '1d': '1d'}
        inv = interval_map.get(timeframe, '1h')
        
        hist = yf.Ticker(symbol).history(period="3mo", interval=inv)
        if hist.empty:
            return None
            
        df = hist.reset_index()
        # Rename columns to lowercase to match existing logic
        rename_map = {
            'Datetime': 'timestamp', 
            'Date': 'timestamp',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        }
        df = df.rename(columns=rename_map)
        # Ensure 'close' is float
        df['close'] = df['close'].astype(float)
        
        return df.tail(limit)
    except Exception as e:
        return None
