from dataclasses import dataclass
import pandas as pd
import yfinance as yf
from config import *
from strategy import add_indicators, entry_signal

@dataclass
class Trade:
    ticker: str
    entry_date: str
    exit_date: str
    entry: float
    exit: float
    shares: float
    pnl: float
    return_pct: float
    reason: str
    hold_days: int

def download(ticker):
    df = yf.download(ticker, start=START_DATE, auto_adjust=True, progress=False)
    if df.empty:
        return df
    if hasattr(df.columns, "levels"):
        df.columns = df.columns.get_level_values(0)
    return add_indicators(df)

def run_backtest():
    cash = INITIAL_CAPITAL
    positions = {}
    trades = []
    curve = []
    data = {t: download(t) for t in TICKERS}
    data = {t:d for t,d in data.items() if not d.empty}
    dates = sorted(set().union(*(d.index for d in data.values())))

    for date in dates:
        for ticker in list(positions):
            p = positions[ticker]
            if date not in data[ticker].index:
                continue
            row = data[ticker].loc[date]
            price = float(row.Close)
            p["high"] = max(p["high"], price)
            held = (date - p["entry_date"]).days
            target = p["entry"] * (1 + TAKE_PROFIT)
            stop = p["entry"] * (1 - STOP_LOSS)
            trailing = p["high"] * (1 - TRAIL_DISTANCE) if p["high"] >= p["entry"]*(1+TRAIL_START) else None
            reason, exit_price = None, price
            if price >= target:
                reason, exit_price = "take_profit", target
            elif price <= stop:
                reason, exit_price = "stop_loss", stop
            elif trailing is not None and price <= trailing:
                reason, exit_price = "trailing_stop", trailing
            elif held >= MAX_HOLD_DAYS:
                reason = "max_hold"
            if reason:
                proceeds = p["shares"] * exit_price
                sell_cost = proceeds * (COMMISSION_RATE + SLIPPAGE_RATE)
                cash += proceeds - sell_cost
                pnl = (exit_price-p["entry"])*p["shares"] - p["buy_cost"] - sell_cost
                trades.append(Trade(ticker,p["entry_date"].strftime("%Y-%m-%d"),date.strftime("%Y-%m-%d"),
                                    p["entry"],exit_price,p["shares"],pnl,pnl/p["capital"],reason,held))
                del positions[ticker]

        for ticker, df in data.items():
            if len(positions) >= MAX_OPEN_POSITIONS or ticker in positions or date not in df.index:
                continue
            row = df.loc[date]
            if not entry_signal(row):
                continue
            equity = cash + sum(
                p["shares"]*float(data[t].loc[date].Close)
                for t,p in positions.items() if date in data[t].index
            )
            capital = min(cash, equity*POSITION_FRACTION)
            if capital <= 0:
                continue
            price = float(row.Close)*(1+SLIPPAGE_RATE)
            buy_cost = capital*COMMISSION_RATE
            shares = (capital-buy_cost)/price
            total = shares*price+buy_cost
            if total > cash:
                continue
            cash -= total
            positions[ticker] = {"entry":price,"entry_date":date,"shares":shares,
                                 "capital":capital,"buy_cost":buy_cost,"high":price}

        equity = cash + sum(
            p["shares"]*float(data[t].loc[date].Close)
            for t,p in positions.items() if date in data[t].index
        )
        curve.append((date,equity))

    trades_df = pd.DataFrame([t.__dict__ for t in trades])
    equity_df = pd.DataFrame(curve, columns=["date","equity"]).set_index("date")
    return trades_df, equity_df

def scan_current():
    rows=[]
    for ticker in TICKERS:
        df=download(ticker)
        if df.empty: continue
        r=df.iloc[-1]
        rows.append({
            "Ticker":ticker, "Price":float(r.Close), "RSI":float(r.RSI),
            "Above SMA50":bool(r.Close>r.SMA50),
            "SMA20>SMA50":bool(r.SMA20>r.SMA50),
            "Volume Confirmed":bool(r.Volume>r.VOL20),
            "Signal":"BUY" if entry_signal(r) else "WAIT"
        })
    return pd.DataFrame(rows)
