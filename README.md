# Trading Bot Dashboard

## Install
pip install -r requirements.txt

## Launch
streamlit run dashboard.py

The dashboard shows:
- equity curve
- total return
- win rate
- profit factor
- maximum drawdown
- wins vs losses
- every individual trade
- current stock scan and BUY/WAIT signals

The strategy is intentionally a starting point. It targets +7% and stops around -3%.

The Trading 212 integration is intentionally not connected to live order placement. Trading 212's official API currently provides a Demo/Paper Trading environment, which should be used before any live deployment.
