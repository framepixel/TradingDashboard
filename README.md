# TradingDashboard
A dashboard with the most interesting Cryptocurrencies and stocks to day trade right now.

## 🚀 Features

- **Market Overview & Broad Equities Support**: Get real-time data for major indices (S&P 500, NASDAQ) and top cryptocurrencies (BTC, ETH) with trend analysis. Also tracks a large universe of highly liquid day trading stocks.
- **Top Movers & Setups (Anti-Pump Ranking)**: Scans Binance and ranks liquid symbols with a balanced composite score (liquidity + sustainable momentum - extremeness penalty) instead of pure top-gainer chasing.
- **Risk-Tiered Technical Pre-Screening**: Evaluates breakouts, pullbacks, and volume anomalies with penalty-aware scoring. Adds Risk Tiers (`FRESH`, `ESTABLISHED`, `EXTENDED`, `EXHAUSTED`) plus risk flags for late-entry detection.
- **4h Context Bias**: Uses 4h trend and momentum health as a primary safety context for crypto scoring, helping reduce entries that are already overstretched.
- **AI Trade Ideas**: Generates automated, structured trade ideas and analysis using an integrated Hugging Face AI agent (`Qwen2.5-72B-Instruct`).
- **Historical Backtesting Engine**: Test technical strategies directly in the app to see historical performance over set hold periods.
- **Custom Watchlist**: Keep track of your favorite symbols directly in the sidebar with session persistence.
- **Trade Journal**: A built-in log to track your entries, exits, P&L, and trade notes.
- **Alpaca Trade Execution**: Connect with Alpaca via environment variables to view paper/live account status, buying power, and recent orders, then submit market orders directly from the dashboard.
- **TradingView Integration**: Direct links to TradingView charts for quick visual inspections of setups.

## 🛠️ How to Run the App

1. **Clone the repository** (if you haven't already) and navigate to the project folder:
   ```bash
   cd TradingDashboard
   ```

2. **Create a virtual environment** (Optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install the required dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up Environment Variables (API Keys)**:
   The AI Trade Ideas feature uses Hugging Face's Inference API. You need to provide a valid Hugging Face API token:
   ```bash
   export HF_TOKEN="your_hugging_face_token_here"
   ```
   *(Note: If `HF_TOKEN` is not set, the dashboard will fall back to generating mocked AI trade ideas.)*

   To enable Alpaca trade execution, set your Alpaca API credentials in the environment as well:
   ```bash
   export ALPACA_API_KEY="your_alpaca_key_id"
   export ALPACA_API_SECRET="your_alpaca_secret_key"
   ```

   The dashboard will try to detect whether the credentials are paper or live by authenticating against Alpaca. If you want to force a mode, set:
   ```bash
   export ALPACA_PAPER=true
   ```
   Use `false` to prefer live trading when both modes are available.

5. **Run the Streamlit application**:
   ```bash
   streamlit run app.py
   ```

6. **View the Dashboard**: 
   Open your browser and navigate to `http://localhost:8501`.

## 📖 Feature Tutorials

### 1. Market Overview & Top Movers
- **What it does**: Displays live quotes of S&P 500, NASDAQ, BTC, and ETH. Analyzes market breadth (Advancing vs. Declining stocks) for a large universe of day trading stocks.
- **How to use it**: Use this section right at market open to gauge overall market direction. If the "Top Equity Breadth" metric reads "Bullish Tracker" (over 60% advancing), you generally want to favor long setups.

### 2. Technical Pre-Screening & Backtesting
- **What it does**: Scans for volume anomalies, breakouts, and pullbacks with anti-exhaustion penalties (RSI exhaustion, overextension vs EMA20, weak-volume breakouts, and candle-streak heat). Every setup includes a risk tier and risk flags.
- **How to use it**: In the sidebar, use the Risk Tier filter (default excludes `EXHAUSTED`). Focus on `FRESH` and `ESTABLISHED` setups for safer entries. Use `EXTENDED` selectively and treat risk flags as warning labels.

### 3. AI Trade Ideas
- **What it does**: Passes the technical context of a flagged asset to an advanced LLM (`Qwen/Qwen2.5-72B-Instruct` via Hugging Face) to generate a structured trade plan (Trend, Setup, Entry, Stop Loss, Take Profit).
- **How to use it**: Go to the "🧠 AI Trade Ideas" tab. When you spot a setup you like from the Pre-Screening tab, click "Generate AI Idea" to get exact support/resistance levels and suggested R:R (Risk/Reward) placements without doing the math yourself.

### 4. Custom Watchlist
- **What it does**: A sidebar widget that lets you add and remove specific stock or crypto tickers. 
- **How to use it**: Type a symbol (e.g., `TSLA` or `ETH/USDT`) into the sidebar and hit "Add". Keep an eye on these specific pairs while the main feed updates with the broader top movers.

### 5. Alpaca Trade Execution
- **What it does**: Connects to Alpaca using your environment variables, shows whether the current session is paper or live, displays balance and buying power, and lists the most recent Alpaca orders.
- **How to use it**: Open the "🦙 Alpaca Trade Execution" section, confirm the detected mode, choose whether to size the order by shares or USD notional, and optionally set a Take Profit and Stop Loss before submitting a market order. You can also use the "Sell All (Close Position)" action to close the full position for a specific stock symbol. If the dashboard detects a live account, it requires an explicit confirmation checkbox before submission.

### 6. Trade Journal
- **What it does**: A built-in, local session log to record your executed trades. 
- **How to use it**: After taking a trade generated by the AI or your own setup, input your Entry Price, Exit Price, and Notes. Use this to review your performance at the end of the trading session.
