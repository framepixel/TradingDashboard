import pandas as pd


def _consecutive_green_candles(df, lookback=10):
    """Count consecutive bullish candles from the latest candle backward."""
    if df is None or len(df) == 0:
        return 0
    recent = df.iloc[-lookback:]
    streak = 0
    for _, row in recent.iloc[::-1].iterrows():
        if row['close'] > row['open']:
            streak += 1
        else:
            break
    return streak


def _compute_4h_bias(df_4h):
    """Return a bias score and labels derived from 4h context for safer entries."""
    if df_4h is None or len(df_4h) < 60:
        return 0, "Neutral (insufficient 4h data)", []

    last_4h = df_4h.iloc[-1]
    bias_score = 0
    bias_flags = []

    if last_4h['close'] > last_4h['EMA50']:
        bias_score += 10
        bias_flags.append("4h Uptrend")
    else:
        bias_score -= 20
        bias_flags.append("4h Downtrend")

    if 45 <= last_4h['RSI'] <= 62:
        bias_score += 8
        bias_flags.append("4h RSI Healthy")
    elif last_4h['RSI'] > 70:
        bias_score -= 12
        bias_flags.append("4h RSI Overbought")

    if last_4h['Vol_MA_20'] > 0:
        vol_ratio_4h = last_4h['volume'] / last_4h['Vol_MA_20']
        if vol_ratio_4h < 0.8:
            bias_score -= 6
            bias_flags.append("4h Weak Volume")

    if last_4h['EMA20'] > 0:
        distance_above_ema20 = ((last_4h['close'] - last_4h['EMA20']) / last_4h['EMA20']) * 100
        if distance_above_ema20 > 12:
            bias_score -= 8
            bias_flags.append("4h Extended")

    bias_label = "Bullish" if bias_score >= 8 else "Bearish" if bias_score <= -8 else "Neutral"
    return bias_score, bias_label, bias_flags

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
    
    # -----------------------------
    # VECTORIZED STRATEGY SIGNALS (For Backtesting)
    # -----------------------------
    # Past 20-candle high (excluding current candle)
    df['Past_20_High'] = df['high'].shift(1).rolling(window=20).max()
    df['Signal_Breakout'] = df['close'] > df['Past_20_High']
    
    # Volume Anomaly
    df['Signal_Vol_Anomaly'] = df['volume'] > (1.5 * df['Vol_MA_20'])
    
    # Pullback
    df['Uptrend'] = df['close'] > df['EMA50']
    df['Signal_Pullback'] = df['Uptrend'] & (df['low'] <= df['EMA20']) & (df['close'] >= df['EMA20'])
                              
    return df

def run_backtest(df, signal_col, hold_period=5):
    """
    Simple Historical Backtesting Engine
    Buys when the signal occurs, holds for `hold_period` candles, and computes the outcome.
    Returns: trades_count, win_rate_percentage, total_pnl_percentage
    """
    if df is None or len(df) < (hold_period + 1) or signal_col not in df.columns:
        return 0, 0.0, 0.0
    
    trades = 0
    wins = 0
    total_pnl = 0.0
    
    # Loop over history minus the hold period to avoid out-of-bounds
    # Exclude the very last few candles where we can't complete the hold period
    for i in range(len(df) - hold_period - 1):
        if df.iloc[i][signal_col]:
            # Enter at the open of the next candle after the signal
            entry_price = df.iloc[i + 1]['open']
            # Exit at the close of the holding period
            exit_price = df.iloc[i + 1 + hold_period]['close']
            
            if entry_price > 0:
                pnl = (exit_price - entry_price) / entry_price
                trades += 1
                total_pnl += pnl
                if pnl > 0:
                    wins += 1
                    
    win_rate = (wins / trades * 100) if trades > 0 else 0.0
    return trades, win_rate, total_pnl * 100

def analyze_strategy(df, df_4h_bias=None):
    """Detect setups and return confidence with anti-exhaustion risk controls."""
    if df is None or len(df) < 25:
        return False, False, False, 0, [], "UNKNOWN", [], "Neutral"
    
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
    risk_flags = []
    
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
    elif last['RSI'] > 70:
        score -= 25
        risk_flags.append("RSI Exhausted")
    elif last['RSI'] > 65:
        score -= 12
        risk_flags.append("RSI Elevated")
        
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

    # Late-entry and pump-risk penalties
    recent_high = df['high'].iloc[-21:].max()
    distance_from_recent_high_pct = ((recent_high - last['close']) / recent_high) * 100 if recent_high > 0 else 100
    if distance_from_recent_high_pct < 2:
        score -= 15
        risk_flags.append("Near Recent High")

    if last['EMA20'] > 0:
        distance_above_ema20_pct = ((last['close'] - last['EMA20']) / last['EMA20']) * 100
        if distance_above_ema20_pct > 20:
            score -= 25
            risk_flags.append("Too Extended vs EMA20")
        elif distance_above_ema20_pct > 12:
            score -= 15
            risk_flags.append("Extended vs EMA20")

    green_streak = _consecutive_green_candles(df, lookback=10)
    if green_streak >= 7:
        score -= 25
        risk_flags.append("Exhaustion Candle Streak")
    elif green_streak >= 5:
        score -= 15
        risk_flags.append("Hot Candle Streak")

    vol_ratio = (last['volume'] / last['Vol_MA_20']) if last['Vol_MA_20'] > 0 else 0
    if breakout and vol_ratio < 1.2:
        score -= 20
        risk_flags.append("Weak Volume Breakout")
        
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

    # 4h context is used as a primary bias for safer selection.
    bias_label = "Neutral"
    if df_4h_bias is not None and len(df_4h_bias) >= 60:
        bias_score, bias_label, bias_flags = _compute_4h_bias(df_4h_bias)
        score += bias_score
        risk_flags.extend([flag for flag in bias_flags if "Downtrend" in flag or "Overbought" in flag or "Extended" in flag or "Weak Volume" in flag])
        patterns.extend([flag for flag in bias_flags if flag in ("4h Uptrend", "4h RSI Healthy")])

    score = max(0, min(100, int(round(score))))

    if any(flag in risk_flags for flag in ("Too Extended vs EMA20", "Exhaustion Candle Streak", "Weak Volume Breakout", "RSI Exhausted")):
        risk_tier = "EXHAUSTED"
    elif any(flag in risk_flags for flag in ("Extended vs EMA20", "Hot Candle Streak", "Near Recent High", "RSI Elevated")):
        risk_tier = "EXTENDED"
    elif pullback and uptrend and last['RSI'] <= 62:
        risk_tier = "FRESH"
    else:
        risk_tier = "ESTABLISHED"
    
    return vol_anomaly, breakout, pullback, score, patterns, risk_tier, sorted(set(risk_flags)), bias_label
