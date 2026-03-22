import streamlit as st
import ccxt
import pandas as pd
import yfinance as yf
import concurrent.futures

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

@st.cache_data(ttl=60) # Cache for 1 minute for active setups
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

@st.cache_data(ttl=60)
def fetch_ohlcv_data(symbol, timeframe='5m', limit=300):
    """Fetch OHLCV data for a specific crypto symbol"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        return None

@st.cache_data(ttl=60)
def fetch_top_stock_movers():
    """Fetch 24h change for a large universe of highly liquid day trading stocks."""
    # Expanded universe of high volume & high beta stocks for day trading
    tickers = [
        'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AMD', 'INTC', 'NFLX', 
        'WMT', 'JPM', 'V', 'LLY', 'AVGO', 'COST', 'JNJ', 'ORCL', 'CRM', 'BAC',
        'SPY', 'QQQ', 'COIN', 'MSTR', 'PLTR', 'SMCI', 'MARA', 'RIOT', 'SQ', 'ROKU',
        'BA', 'DIS', 'ADBE', 'PYPL', 'UBER', 'SNOW', 'ARM', 'PANW', 'PATH', 'CRWD',
        'SHOP', 'ZS', 'DDOG', 'MDB', 'NET', 'CVNA', 'DKNG', 'CVX', 'XOM', 'HD'
    ]
    stock_pairs = []
    
    def process_ticker(symbol):
        try:
            hist = yf.Ticker(symbol).history(period="5d")
            if not hist.empty and len(hist) >= 2:
                prev_close = float(hist['Close'].iloc[-2])
                curr_close = float(hist['Close'].iloc[-1])
                volume = float(hist['Volume'].iloc[-1])
                pct_change = ((curr_close - prev_close) / prev_close) * 100
                
                return {
                    'Symbol': symbol,
                    'Price': curr_close,
                    '24h Change (%)': pct_change,
                    '24h Volume (USDT)': volume * curr_close # approx dollar volume
                }
        except Exception:
            return None
        return None

    # Fetch concurrently to massively speed up UI blocking overhead
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(process_ticker, tickers)
        
    for r in results:
        if r is not None:
            stock_pairs.append(r)
            
    df = pd.DataFrame(stock_pairs)
    if not df.empty:
        df = df.sort_values(by='24h Volume (USDT)', ascending=False).head(40) # Show top 40 by liquidity
    return df

@st.cache_data(ttl=60)
def fetch_stock_ohlcv_data(symbol, timeframe='5m', limit=300):
    """Fetch OHLCV data for a specific stock"""
    try:
        # Map Crypto timeframes to YFinance timeframes and appropriate period
        interval_map = {'1m': ('1m', '5d'), '5m': ('5m', '1mo'), '15m': ('15m', '1mo'), '1h': ('1h', '3mo'), '1d': ('1d', '6mo')}
        inv, span = interval_map.get(timeframe, ('5m', '1mo'))
        
        hist = yf.Ticker(symbol).history(period=span, interval=inv)
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

@st.cache_data(ttl=300)
def fetch_market_news(symbol="SPY"):
    """Fetch the latest market news from Yahoo Finance for a specific ticker to gauge sentiment"""
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        formatted_news = []
        for item in news[:5]: # Get top 5 news items
            # Yahoo Finance sometimes nests the article details inside a 'content' key
            content = item.get("content", item)
            
            # Extract fields with safe fallbacks
            title = content.get("title", "No Title")
            publisher = content.get("provider", {}).get("displayName", "Unknown")
            link = content.get("clickThroughUrl", {}).get("url", content.get("canonicalUrl", {}).get("url", "#"))
            timestamp = content.get("pubDate", "")
            
            if timestamp:
                time_str = pd.to_datetime(timestamp).strftime("%Y-%m-%d %H:%M")
            else:
                # Fallback for old API format which used providerPublishTime
                time_str = pd.to_datetime(content.get("providerPublishTime", 0), unit='s').strftime("%Y-%m-%d %H:%M")

            formatted_news.append({
                "Title": title,
                "Publisher": publisher,
                "Link": link,
                "Time": time_str
            })
        return formatted_news
    except Exception as e:
        return []
