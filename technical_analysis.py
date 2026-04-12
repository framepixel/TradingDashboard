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

def calculate_pivots(df):
    """Calculates 3-candle fractals to explicitly mark pivot highs and lows"""
    if df is None or len(df) < 3:
        return df
    
    # Needs 3 candles to define a pivot (prev, current, next)
    # Pivot High: current high is higher than both prev and next
    df['Pivot_High'] = (df['high'] > df['high'].shift(1)) & (df['high'] > df['high'].shift(-1))
    
    # Pivot Low: current low is lower than both prev and next
    df['Pivot_Low'] = (df['low'] < df['low'].shift(1)) & (df['low'] < df['low'].shift(-1))
    
    return df

def calculate_indicators(df):
    """Calculate EMAs, RSI(14), Volume MA(20), VWAP, MACD, and Bollinger Bands"""
    if df is None or len(df) < 50:
        return df

    # Calculate Pivot Highs and Lows
    df = calculate_pivots(df)

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
                              
    # Bearish Engulfing
    df['Bearish_Engulfing'] = (df['Prev_Close'] > df['Prev_Open']) & \
                              (df['close'] < df['open']) & \
                              (df['open'] >= df['Prev_Close']) & \
                              (df['close'] <= df['Prev_Open'])

    # Bearish Pinbar / Shooting Star
    df['Bearish_Pinbar'] = (df['Upper_Wick'] > (2 * df['Body'])) & (df['Lower_Wick'] < df['Body']) & (df['Body'] > 0)

    # Doji
    df['Doji'] = df['Body'] <= (0.1 * (df['high'] - df['low']))

    # Head and Shoulders (Simplified checking last 3 pivots)
    df['H_and_S'] = False
    pivot_indices = df.index[df['Pivot_High']].tolist()
    for i in range(2, len(pivot_indices)):
        idx1, idx2, idx3 = pivot_indices[i-2], pivot_indices[i-1], pivot_indices[i]
        ls, head, rs = df.loc[idx1, 'high'], df.loc[idx2, 'high'], df.loc[idx3, 'high']
        if head > ls and head > rs and abs(ls - rs) / ls < 0.05:
            df.loc[idx3, 'H_and_S'] = True

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

def analyze_strategy(df_w, df_d, df_4h):
    """Detect setups applying the 4-step constraints (W, D, 4H)."""
    if df_w is None or df_d is None or df_4h is None:
        return False, False, False, 0, [], "UNKNOWN", [], "Neutral"
    if len(df_w) < 20 or len(df_d) < 20 or len(df_4h) < 20:
        return False, False, False, 0, [], "UNKNOWN", [], "Neutral"

    last_w = df_w.iloc[-1]
    last_d = df_d.iloc[-1]
    last_4h = df_4h.iloc[-1]

    # Step 1: Trend Alignment (W, D, 4H should be in uptrend for long, or valid criteria)
    # Assume 50 EMA is trend
    trend_aligned = (last_w['close'] > last_w['EMA50']) and (last_d['close'] > last_d['EMA50']) and (last_4h['close'] > last_4h['EMA50'])

    # Step 2: AOI Validation (Area of Interest)
    # Price is near EMA20 or VWAP on Daily or 4H
    d_emi = (abs(last_d['close'] - last_d['EMA20']) / last_d['EMA20']) < 0.05
    h4_emi = (abs(last_4h['close'] - last_4h['EMA20']) / last_4h['EMA20']) < 0.05
    aoi_valid = d_emi or h4_emi

    # Step 3: H&S Alignment
    # Inverted H&S indicates bullishness, regular H&S implies bearishness. Let's look for H&S status.
    hs_aligned = (last_d.get('H_and_S', False) == False) and (last_4h.get('H_and_S', False) == False)

    # Step 4: Candlestick Validation
    candle_valid = (
        last_d.get('Bullish_Pinbar', False) or last_d.get('Bullish_Engulfing', False) or 
        last_4h.get('Bullish_Pinbar', False) or last_4h.get('Bullish_Engulfing', False)
    )

    score = 0
    patterns = []
    risk_flags = []

    if trend_aligned: score += 25; patterns.append("Trend Aligned (W/D/4H)")
    else: risk_flags.append("Trend Mismatch")

    if aoi_valid: score += 25; patterns.append("AOI Validation")
    else: risk_flags.append("Not at AOI")

    if hs_aligned: score += 25; patterns.append("H&S Clear")
    else: risk_flags.append("H&S Pattern Present")

    if candle_valid: score += 25; patterns.append("Candle Confirm")
    else: risk_flags.append("No Candle Confirm")

    if score == 100:
        risk_tier = "FRESH"
    elif score == 75:
        risk_tier = "ESTABLISHED"
    elif score == 50:
        risk_tier = "EXTENDED"
    else:
        risk_tier = "EXHAUSTED"
        
    bias_label = "Bullish" if score >= 75 else "Neutral" if score >= 50 else "Bearish"

    # Some dummy returns to match old signature: vol_anomaly, breakout, pullback, score, patterns, risk_tier, risk_flags, bias_label
    vol_anomaly = last_d['volume'] > (1.5 * last_d['Vol_MA_20'])
    breakout = last_d['close'] > df_d['high'].iloc[-21:-1].max()
    pullback = aoi_valid

    return vol_anomaly, breakout, pullback, score, patterns, risk_tier, risk_flags, bias_label

def find_aois(df, atr_multiplier=1.5, min_pivots=3):
    """
    Find Areas of Interest (AOIs) where clusters of >= min_pivots occur 
    within a vertical band defined by atr_multiplier * ATR.
    """
    if df is None or len(df) < min_pivots or 'ATR' not in df.columns \
       or 'Pivot_High' not in df.columns or 'Pivot_Low' not in df.columns:
        return []
        
    current_atr = df['ATR'].iloc[-1]
    if pd.isna(current_atr) or current_atr <= 0:
        return []
        
    band_size = current_atr * atr_multiplier
    
    pivot_highs = df.loc[df['Pivot_High'], 'high'].dropna().tolist()
    pivot_lows = df.loc[df['Pivot_Low'], 'low'].dropna().tolist()
    all_pivots = sorted(pivot_highs + pivot_lows)
    
    aois = []
    visited = set()
    
    for i in range(len(all_pivots)):
        if i in visited:
            continue
            
        cluster = [all_pivots[i]]
        current_visited = {i}
        
        for j in range(i + 1, len(all_pivots)):
            if j not in visited and (all_pivots[j] - cluster[0]) <= band_size:
                cluster.append(all_pivots[j])
                current_visited.add(j)
                
        if len(cluster) >= min_pivots:
            aois.append({
                'price_level': sum(cluster) / len(cluster),
                'top': max(cluster),
                'bottom': min(cluster),
                'pivot_count': len(cluster)
            })
            visited.update(current_visited)
            
    return aois
