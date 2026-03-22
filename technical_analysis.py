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
