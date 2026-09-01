from dataclasses import dataclass
import pandas as pd
import yfinance as yf
from config import *
from strategy import add_indicators, signal_score, entry_signal

@dataclass
class Trade:
    ticker: str
    entry_date: str
    exit_date: str
    entry: float
    exit: float
    shares: float
    capital: float
    pnl: float
    return_pct: float
    reason: str
    hold_days: int
    score: float

def download(ticker):
    try:
        df = yf.download(ticker, start=START_DATE, auto_adjust=True, progress=False, threads=False)
        if df.empty: return df
        if hasattr(df.columns, "levels"): df.columns = df.columns.get_level_values(0)
        return add_indicators(df)
    except Exception:
        return pd.DataFrame()

def load_data(tickers):
    result = {}
    for ticker in tickers:
        d = download(ticker)
        if not d.empty: result[ticker] = d
    return result

def run_backtest(tickers=None, target=DEFAULT_TARGET, stop=DEFAULT_STOP,
                 initial_capital=INITIAL_CAPITAL, risk_per_trade=RISK_PER_TRADE,
                 max_positions=MAX_OPEN_POSITIONS, min_score=70):
    data = load_data(tickers or TICKERS)
    if not data: return pd.DataFrame(), pd.DataFrame()
    cash, positions, trades, curve = initial_capital, {}, [], []
    dates = sorted(set().union(*(d.index for d in data.values())))

    for date in dates:
        for ticker in list(positions):
            p = positions[ticker]
            if date not in data[ticker].index: continue
            price = float(data[ticker].loc[date]["Close"])
            p["high"] = max(p["high"], price)
            held = (date - p["entry_date"]).days
            target_price = p["entry"] * (1 + target)
            stop_price = p["entry"] * (1 - stop)
            trailing = p["high"] * (1 - TRAIL_DISTANCE) if p["high"] >= p["entry"]*(1+TRAIL_START) else None
            reason, exit_price = None, price
            if price >= target_price: reason, exit_price = "take_profit", target_price
            elif price <= stop_price: reason, exit_price = "stop_loss", stop_price
            elif trailing is not None and price <= trailing: reason, exit_price = "trailing_stop", trailing
            elif held >= MAX_HOLD_DAYS: reason = "max_hold"
            if reason:
                proceeds = p["shares"] * exit_price
                sell_cost = proceeds * (COMMISSION_RATE + SLIPPAGE_RATE)
                cash += proceeds - sell_cost
                pnl = (exit_price-p["entry"])*p["shares"] - p["buy_cost"] - sell_cost
                trades.append(Trade(ticker,p["entry_date"].strftime("%Y-%m-%d"),date.strftime("%Y-%m-%d"),
                    p["entry"],exit_price,p["shares"],p["capital"],pnl,pnl/p["capital"],reason,held,p["score"]))
                del positions[ticker]

        for ticker, df in data.items():
            if len(positions) >= max_positions or ticker in positions or date not in df.index: continue
            row = df.loc[date]
            score = signal_score(row)
            if not entry_signal(row, min_score): continue
            equity = cash + sum(p["shares"]*float(data[t].loc[date]["Close"]) for t,p in positions.items() if date in data[t].index)
            risk_cash = equity * risk_per_trade
            capital = min(cash, risk_cash / stop)
            if capital <= 0: continue
            price = float(row["Close"]) * (1 + SLIPPAGE_RATE)
            buy_cost = capital * COMMISSION_RATE
            shares = max((capital-buy_cost)/price, 0)
            total = shares*price + buy_cost
            if shares <= 0 or total > cash: continue
            cash -= total
            positions[ticker] = {"entry":price,"entry_date":date,"shares":shares,"capital":capital,
                                 "buy_cost":buy_cost,"high":price,"score":score}

        equity = cash + sum(p["shares"]*float(data[t].loc[date]["Close"]) for t,p in positions.items() if date in data[t].index)
        curve.append((date,equity))

    trades_df = pd.DataFrame([t.__dict__ for t in trades])
    equity_df = pd.DataFrame(curve, columns=["date","equity"]).set_index("date")
    return trades_df, equity_df

def summarise(trades, equity, initial_capital):
    if trades.empty or equity.empty:
        return {"Total return":0,"Win rate":0,"Profit factor":0,"Max drawdown":0,"Trades":0,"Avg trade":0}
    wins, losses = trades[trades.pnl>0], trades[trades.pnl<=0]
    dd = equity.equity / equity.equity.cummax() - 1
    return {
        "Total return": float(equity.equity.iloc[-1]/initial_capital-1),
        "Win rate": len(wins)/len(trades),
        "Profit factor": wins.pnl.sum()/abs(losses.pnl.sum()) if len(losses) and losses.pnl.sum()!=0 else float("inf"),
        "Max drawdown": float(dd.min()),
        "Trades": len(trades),
        "Avg trade": float(trades.return_pct.mean())
    }

def optimise_targets(tickers=None, targets=None, stop=DEFAULT_STOP, initial_capital=INITIAL_CAPITAL,
                      risk_per_trade=RISK_PER_TRADE, max_positions=MAX_OPEN_POSITIONS, min_score=70):
    rows=[]
    for target in targets or [0.05,0.06,0.07,0.08,0.09,0.10]:
        trades,equity=run_backtest(tickers,target,stop,initial_capital,risk_per_trade,max_positions,min_score)
        s=summarise(trades,equity,initial_capital)
        rows.append({"Target":target,"Total Return":s["Total return"],"Win Rate":s["Win rate"],
                     "Profit Factor":s["Profit factor"],"Max Drawdown":s["Max drawdown"],
                     "Trades":s["Trades"],"Average Trade":s["Avg trade"]})
    return pd.DataFrame(rows)

def scan_current(tickers=None, min_score=70):
    rows=[]
    for ticker in tickers or TICKERS:
        df=download(ticker)
        if df.empty: continue
        r=df.iloc[-1]
        score=signal_score(r)
        rows.append({"Ticker":ticker,"Price":float(r.Close),"Score":score,"RSI":float(r.RSI),
                     "20d Momentum":float(r.MOM20),"60d Momentum":float(r.MOM60),
                     "Volume Ratio":float(r.VOL_RATIO),
                     "Above SMA50":bool(r.Close>r.SMA50),"SMA20>SMA50":bool(r.SMA20>r.SMA50),
                     "SMA50>SMA200":bool(r.SMA50>r.SMA200),
                     "Signal":"BUY" if score>=min_score else "WATCH"})
    return pd.DataFrame(rows).sort_values(["Score","Volume Ratio"],ascending=False)
