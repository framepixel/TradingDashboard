import pandas as pd

def calculate_indicators(df):
    """Calculate EMA20, EMA50, RSI(14), and Volume MA(20)"""
    if df is None or len(df) < 50:
        return df
    
    # EMAs
    df['EMA20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Volume MA (20)
    df['Vol_MA_20'] = df['volume'].rolling(window=20).mean()
    
    return df

def analyze_strategy(df):
    """Detect Breakouts, Pullbacks, and Volume Anomalies"""
    if df is None or len(df) < 25:
        return False, False, False
    
    last = df.iloc[-1]
    
    # Volume Anomaly: Volume > 1.5x average (last 20 periods)
    vol_anomaly = last['volume'] > (1.5 * last['Vol_MA_20'])
    
    # Breakout Detection: Price breaks previous resistance (last 20 candles high)
    past_20_high = df['high'].iloc[-21:-1].max()
    breakout = last['close'] > past_20_high
    
    # Pullback Detection: Uptrend (price > EMA50), pullback to EMA20 or EMA50
    uptrend = last['close'] > last['EMA50']
    pullback = uptrend and (last['low'] <= last['EMA20']) and (last['close'] >= last['EMA20'])
    
    return vol_anomaly, breakout, pullback
