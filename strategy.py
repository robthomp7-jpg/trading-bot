import numpy as np
import pandas as pd

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def add_indicators(df):
    x = df.copy()
    x["SMA20"] = x["Close"].rolling(20).mean()
    x["SMA50"] = x["Close"].rolling(50).mean()
    x["RSI"] = rsi(x["Close"], 14)
    x["VOL20"] = x["Volume"].rolling(20).mean()
    return x.dropna()

def entry_signal(row):
    return (
        row["Close"] > row["SMA50"]
        and row["SMA20"] > row["SMA50"]
        and row["Close"] > row["SMA20"]
        and 50 <= row["RSI"] <= 70
        and row["Volume"] > row["VOL20"]
    )
