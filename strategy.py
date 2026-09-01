def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))

def add_indicators(df):
    x = df.copy()
    x["SMA20"] = x["Close"].rolling(20).mean()
    x["SMA50"] = x["Close"].rolling(50).mean()
    x["SMA200"] = x["Close"].rolling(200).mean()
    x["RSI"] = rsi(x["Close"])
    x["VOL20"] = x["Volume"].rolling(20).mean()
    x["MOM20"] = x["Close"].pct_change(20)
    x["MOM60"] = x["Close"].pct_change(60)
    x["VOL_RATIO"] = x["Volume"] / x["VOL20"]
    return x.dropna()

def signal_score(row):
    score = 0
    if row["Close"] > row["SMA50"]: score += 20
    if row["SMA20"] > row["SMA50"]: score += 20
    if row["SMA50"] > row["SMA200"]: score += 15
    r = float(row["RSI"])
    if 55 <= r <= 68: score += 15
    elif 50 <= r <= 72: score += 8
    if row["Volume"] > row["VOL20"]: score += 10
    if row["MOM20"] > 0: score += 10
    if row["MOM60"] > 0: score += 10
    return min(score, 100)

def entry_signal(row, minimum_score=70):
    return signal_score(row) >= minimum_score
