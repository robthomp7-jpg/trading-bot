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
        if df.empty: return pd.DataFrame()
        if hasattr(df.columns, "levels"): df.columns = df.columns.get_level_values(0)
        return add_indicators(df)
    except Exception:
        return pd.DataFrame()

def load_data(tickers):
    out = {}
    for ticker in tickers:
        d = download(ticker)
        if not d.empty: out[ticker] = d
    return out

def run_backtest(tickers=None, target=DEFAULT_TARGET, stop=DEFAULT_STOP,
                 initial_capital=INITIAL_CAPITAL, risk_per_trade=RISK_PER_TRADE,
                 max_positions=MAX_OPEN_POSITIONS, min_score=70):
    # Signal uses yesterday's completed bar; entry is today's open.
    # If target and stop both occur on one daily bar, stop is assumed first.
    data = load_data(tickers or TICKERS)
    if not data: return pd.DataFrame(), pd.DataFrame()

    cash = float(initial_capital)
    positions, trades, curve = {}, [], []
    dates = sorted(set().union(*(d.index for d in data.values())))

    for date in dates:
        # Exit existing positions.
        for ticker in list(positions):
            p = positions[ticker]
            df = data[ticker]
            if date not in df.index: continue
            row = df.loc[date]
            op, hi, lo, cl = map(float, [row["Open"], row["High"], row["Low"], row["Close"]])
            p["high"] = max(p["high"], hi)
            held = (date - p["entry_date"]).days
            target_px = p["entry"] * (1 + target)
            stop_px = p["entry"] * (1 - stop)
            reason, exit_px = None, cl

            if op <= stop_px:
                reason, exit_px = "stop_loss_gap", op * (1 - SLIPPAGE_RATE)
            elif op >= target_px:
                reason, exit_px = "take_profit_gap", op * (1 - SLIPPAGE_RATE)
            elif lo <= stop_px:
                reason, exit_px = "stop_loss", stop_px * (1 - SLIPPAGE_RATE)
            elif hi >= target_px:
                reason, exit_px = "take_profit", target_px * (1 - SLIPPAGE_RATE)
            else:
                trailing = p["high"] * (1 - TRAIL_DISTANCE) if p["high"] >= p["entry"]*(1+TRAIL_START) else None
                if trailing is not None and lo <= trailing:
                    reason, exit_px = "trailing_stop", trailing * (1 - SLIPPAGE_RATE)
                elif held >= MAX_HOLD_DAYS:
                    reason = "max_hold"

            if reason:
                proceeds = p["shares"] * exit_px
                sell_cost = proceeds * COMMISSION_RATE
                cash += proceeds - sell_cost
                pnl = (exit_px-p["entry"])*p["shares"] - p["buy_cost"] - sell_cost
                trades.append(Trade(ticker, p["entry_date"].strftime("%Y-%m-%d"), date.strftime("%Y-%m-%d"),
                    p["entry"], exit_px, p["shares"], p["capital"], pnl, pnl/p["capital"],
                    reason, held, p["score"]))
                del positions[ticker]

        # Entry uses only the previous completed day's signal.
        for ticker, df in data.items():
            if len(positions) >= max_positions or ticker in positions or date not in df.index: continue
            idx = df.index.get_loc(date)
            if idx == 0: continue
            signal_row, today = df.iloc[idx-1], df.iloc[idx]
            if not entry_signal(signal_row, min_score): continue

            equity = cash + sum(p["shares"]*float(data[t].loc[date]["Close"]) for t,p in positions.items() if date in data[t].index)
            risk_cash = equity * risk_per_trade
            open_px = float(today["Open"])
            risk_per_share = open_px * stop
            if risk_per_share <= 0: continue

            shares = min(risk_cash/risk_per_share, cash/(open_px*(1+COMMISSION_RATE+SLIPPAGE_RATE)))
            if shares <= 0: continue

            entry_px = open_px * (1 + SLIPPAGE_RATE)
            capital_used = shares * entry_px
            buy_cost = capital_used * COMMISSION_RATE
            total_cost = capital_used + buy_cost
            if total_cost > cash: continue

            cash -= total_cost
            positions[ticker] = {"entry":entry_px, "entry_date":date, "shares":shares,
                                 "capital":capital_used, "buy_cost":buy_cost,
                                 "high":entry_px, "score":signal_score(signal_row)}

        equity = cash + sum(p["shares"]*float(data[t].loc[date]["Close"]) for t,p in positions.items() if date in data[t].index)
        curve.append((date, equity))

    return pd.DataFrame([t.__dict__ for t in trades]), pd.DataFrame(curve, columns=["date","equity"]).set_index("date")

def summarise(trades, equity, initial_capital):
    final = float(equity["equity"].iloc[-1]) if not equity.empty else initial_capital
    dd = float((equity["equity"]/equity["equity"].cummax()-1).min()) if not equity.empty else 0
    if trades.empty:
        return {"Total return":final/initial_capital-1,"Win rate":0,"Profit factor":0,"Max drawdown":dd,"Trades":0,"Avg trade":0}
    wins, losses = trades[trades.pnl>0], trades[trades.pnl<=0]
    return {"Total return":final/initial_capital-1,"Win rate":len(wins)/len(trades),
            "Profit factor":wins.pnl.sum()/abs(losses.pnl.sum()) if len(losses) and losses.pnl.sum()!=0 else float("inf"),
            "Max drawdown":dd,"Trades":len(trades),"Avg trade":float(trades.return_pct.mean())}

def optimise_targets(tickers=None, targets=None, stop=DEFAULT_STOP, initial_capital=INITIAL_CAPITAL,
                      risk_per_trade=RISK_PER_TRADE, max_positions=MAX_OPEN_POSITIONS, min_score=70):
    rows=[]
    for target in targets or [0.05,0.06,0.07,0.08,0.09,0.10]:
        tr, eq = run_backtest(tickers, target, stop, initial_capital, risk_per_trade, max_positions, min_score)
        s=summarise(tr,eq,initial_capital)
        rows.append({"Target":target,"Total Return":s["Total return"],"Win Rate":s["Win rate"],
                     "Profit Factor":s["Profit factor"],"Max Drawdown":s["Max drawdown"],
                     "Trades":s["Trades"],"Average Trade":s["Avg trade"]})
    return pd.DataFrame(rows)

def scan_current(tickers=None, min_score=70):
    rows=[]
    for ticker in tickers or TICKERS:
        df=download(ticker)
        if df.empty: continue
        r=df.iloc[-1]; score=signal_score(r)
        rows.append({"Ticker":ticker,"Price":float(r["Close"]),"Score":score,"RSI":float(r["RSI"]),
                     "20d Momentum":float(r["MOM20"]),"60d Momentum":float(r["MOM60"]),
                     "Volume Ratio":float(r["VOL_RATIO"]),
                     "Above SMA50":bool(r["Close"]>r["SMA50"]),
                     "SMA20>SMA50":bool(r["SMA20"]>r["SMA50"]),
                     "SMA50>SMA200":bool(r["SMA50"]>r["SMA200"]),
                     "Signal":"BUY" if score>=min_score else "WATCH"})
    return pd.DataFrame(rows).sort_values(["Score","Volume Ratio"],ascending=False) if rows else pd.DataFrame()
