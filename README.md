# TradingDashboard
A dashboard with the most interesting Cryptocurrencies and stocks to day trade right now.

## 🚀 Basic Functionalities

- **Market Overview**: Get real-time data for major indices (S&P 500, NASDAQ) and top cryptocurrencies (BTC, ETH) with trend analysis.
- **Top Movers & Setups**: Scans Binance for the top 24-hour gainers and movers.
- **Technical Pre-Screening**: Automatically evaluates volume anomalies, breakouts, and pullbacks using Technical Analysis (RSI, EMA50, Volume indicators).
- **AI Trade Ideas**: Generates automated trade ideas and analysis using an integrated AI agent.
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

4. **Run the Streamlit application**:
   ```bash
   streamlit run app.py
   ```

5. **View the Dashboard**: 
   Open your browser and navigate to `http://localhost:8501`.
