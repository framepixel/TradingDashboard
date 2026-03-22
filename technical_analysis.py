import pandas as pd

def calculate_indicators(df):
    """Calculate EMAs, RSI(14), Volume MA(20), VWAP, MACD, and Bollinger Bands"""
    if df is None or len(df) < 50:
        return df
    
    # EMAs
    df['EMA20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # VWAP (Intraday anchor typically, but here rolling for simplicity across charts)
    df['VW'] = df['close'] * df['volume']
    df['VWAP'] = df['VW'].rolling(window=20).sum() / df['volume'].rolling(window=20).sum()

    # MACD (12, 26, 9)
    df['EMA12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal']

    # Bollinger Bands (20, 2)
    df['BB_MA'] = df['close'].rolling(window=20).mean()
    df['BB_STD'] = df['close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_MA'] + (2 * df['BB_STD'])
    df['BB_Lower'] = df['BB_MA'] - (2 * df['BB_STD'])

    # ATR (14)
    df['TR'] = df[['high', 'low', 'close']].diff().abs().max(axis=1)
    df['ATR'] = df['TR'].rolling(window=14).mean()
    
    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Volume MA (20)
    df['Vol_MA_20'] = df['volume'].rolling(window=20).mean()
    
    # -----------------------------
    # CANDLESTICK PATTERNS
    # -----------------------------
    # Body and Wicks
    df['Body'] = abs(df['close'] - df['open'])
    df['Lower_Wick'] = df[['open', 'close']].min(axis=1) - df['low']
    df['Upper_Wick'] = df['high'] - df[['open', 'close']].max(axis=1)
    
    # Bullish Hammer / Pinbar
    df['Bullish_Pinbar'] = (df['Lower_Wick'] > (2 * df['Body'])) & (df['Upper_Wick'] < df['Body']) & (df['Body'] > 0)
    
    # Bullish Engulfing
    df['Prev_Open'] = df['open'].shift(1)
    df['Prev_Close'] = df['close'].shift(1)
    df['Bullish_Engulfing'] = (df['Prev_Close'] < df['Prev_Open']) & \
                              (df['close'] > df['open']) & \
                              (df['open'] <= df['Prev_Close']) & \
                              (df['close'] >= df['Prev_Open'])
                              
    return df

def analyze_strategy(df):
    """Detect Breakouts, Pullbacks, Volume Anomalies, and calculate Confidence Score"""
    if df is None or len(df) < 25:
        return False, False, False, 0, []
    
    last = df.iloc[-1]
    
    # Volume Anomaly: Volume > 1.5x average (last 20 periods)
    vol_anomaly = last['volume'] > (1.5 * last['Vol_MA_20'])
    
    # Breakout Detection: Price breaks previous resistance (last 20 candles high)
    past_20_high = df['high'].iloc[-21:-1].max()
    breakout = last['close'] > past_20_high
    
    # Pullback Detection: Uptrend (price > EMA50), pullback to EMA20 or EMA50
    uptrend = last['close'] > last['EMA50']
    pullback = uptrend and (last['low'] <= last['EMA20']) and (last['close'] >= last['EMA20'])
    
    # Advanced Signal Confidence Score & Tags
    score = 0
    patterns = []
    
    # Momentum points
    if last['MACD'] > last['Signal']:
        score += 15
        patterns.append("Bullish MACD")
    
    if last['RSI'] < 30:
        score += 20
        patterns.append("Oversold (RSI)")
    elif 30 <= last['RSI'] < 50:
        score += 10
        patterns.append("Favorable RSI")
        
    # Technical Setup Points
    if breakout:
        score += 20
        patterns.append("Breakout")
    if pullback:
        score += 15
        patterns.append("EMA Pullback")
    if vol_anomaly:
        score += 15
        patterns.append("High Vol")
        
    # Pattern Points
    if last['Bullish_Pinbar']:
        score += 20
        patterns.append("Hammer/Pinbar")
    if last['Bullish_Engulfing']:
        score += 20
        patterns.append("Bull_Engulfing")
        
    # VWAP interaction
    if ('VWAP' in last) and (last['low'] < last['VWAP']) and (last['close'] > last['VWAP']):
        score += 15
        patterns.append("VWAP Bounce")
    
    return vol_anomaly, breakout, pullback, score, patterns
