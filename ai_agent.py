import os
from huggingface_hub import InferenceClient

def generate_ai_trade_idea(asset_data):
    """Generate trade idea using Hugging Face (Mocked if API token is absent)"""
    api_key = os.environ.get("HF_TOKEN")
    prompt = f"""
    Analyze the following asset and provide a structured trade idea:
    Symbol: {asset_data['Symbol']}
    Price: {asset_data['Price']}
    RSI: {asset_data['RSI']:.2f}
    Trend: {'Uptrend' if asset_data['Uptrend'] else 'Downtrend'}
    Context: Breakout={asset_data['Breakout']}, Pullback={asset_data['Pullback']}, Vol Anomaly={asset_data['Vol Anomaly']}
    
    Format:
    - Trend: ...
    - Volume: ...
    - Setup: ...
    - Entry: ...
    - Stop Loss: ...
    - Take Profit: ...
    """
    
    if not api_key:
        return f"**Mock AI Idea for {asset_data['Symbol']}**\n- Trend: Bullish\n- Setup: { 'Breakout' if asset_data['Breakout'] else 'Pullback' }\n- Entry: {asset_data['Price']}\n- Stop Loss: {float(asset_data['Price']) * 0.95:.4f}\n- Take Profit: {float(asset_data['Price']) * 1.1:.4f}\n*(Set HF_TOKEN environment variable for real AI generation)*"

    try:
        client = InferenceClient(api_key=api_key)
        response = client.chat_completion(
            model="Qwen/Qwen2.5-72B-Instruct",
            messages=[
                {"role": "system", "content": "You are an expert quantitative crypto trader."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {e}"
