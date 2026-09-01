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
    score: int

def download(ticker):
    try:
        df = yf.download(
            ticker,
            start=START_DATE,
            auto_adjust=True,
            progress=False,
            threads=False
        )
        if df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        needed = ["Open","High","Low","Close","Volume"]
        if any(c not in df.columns for c in needed):
            return pd.DataFrame()
        return add_indicators(df)
    except Exception:
        return pd.DataFrame()

def load_data(tickers=None):
    result = {}
    for ticker in tickers or TICKERS:
        df = download(ticker)
        if not df.empty:
            result[ticker] = df
    return result

def _backtest_data(data, target, stop, initial_capital, risk_per_trade,
                   max_positions, min_score):
    cash = float(initial_capital)
    positions = {}
    trades = []
    curve = []

    dates = sorted(set().union(*(df.index for df in data.values())))

    for date in dates:
        # Exit first.
        for ticker in list(positions):
            p = positions[ticker]
            df = data[ticker]
            if date not in df.index:
                continue

            row = df.loc[date]
            op = float(row["Open"])
            hi = float(row["High"])
            lo = float(row["Low"])
            cl = float(row["Close"])

            held_days = (date - p["entry_date"]).days
            target_px = p["entry"] * (1 + target)
            stop_px = p["entry"] * (1 - stop)

            reason = None
            exit_px = cl

            # Conservative and gap-aware daily-bar assumptions.
            if op <= stop_px:
                reason, exit_px = "stop_loss_gap", op
            elif op >= target_px:
                reason, exit_px = "take_profit_gap", op
            elif lo <= stop_px:
                reason, exit_px = "stop_loss", stop_px
            elif hi >= target_px:
                reason, exit_px = "take_profit", target_px
            elif held_days >= MAX_HOLD_DAYS:
                reason = "max_hold"

            if reason:
                exit_px *= (1 - SLIPPAGE_RATE)
                proceeds = p["shares"] * exit_px
                sell_cost = proceeds * COMMISSION_RATE
                cash += proceeds - sell_cost

                pnl = (
                    (exit_px - p["entry"]) * p["shares"]
                    - p["buy_cost"]
                    - sell_cost
                )

                trades.append(Trade(
                    ticker=ticker,
                    entry_date=p["entry_date"].strftime("%Y-%m-%d"),
                    exit_date=date.strftime("%Y-%m-%d"),
                    entry=p["entry"],
                    exit=exit_px,
                    shares=p["shares"],
                    capital=p["capital"],
                    pnl=pnl,
                    return_pct=pnl / p["capital"],
                    reason=reason,
                    hold_days=held_days,
                    score=p["score"]
                ))
                del positions[ticker]

        # Enter at today's open using only yesterday's completed signal.
        for ticker, df in data.items():
            if len(positions) >= max_positions:
                break
            if ticker in positions or date not in df.index:
                continue

            idx = df.index.get_loc(date)
            if idx == 0:
                continue

            signal_row = df.iloc[idx - 1]
            today = df.iloc[idx]

            if not entry_signal(signal_row, min_score):
                continue

            open_px = float(today["Open"])
            if open_px <= 0:
                continue

            equity = cash
            for t, p in positions.items():
                if date in data[t].index:
                    equity += p["shares"] * float(data[t].loc[date]["Close"])

            risk_cash = equity * risk_per_trade
            risk_per_share = open_px * stop
            if risk_per_share <= 0:
                continue

            shares_by_risk = risk_cash / risk_per_share
            shares_by_cash = cash / (open_px * (1 + COMMISSION_RATE + SLIPPAGE_RATE))
            shares = min(shares_by_risk, shares_by_cash)

            if shares <= 0:
                continue

            entry_px = open_px * (1 + SLIPPAGE_RATE)
            capital_used = shares * entry_px
            buy_cost = capital_used * COMMISSION_RATE
            total_cost = capital_used + buy_cost

            if total_cost > cash:
                continue

            cash -= total_cost
            positions[ticker] = {
                "entry": entry_px,
                "entry_date": date,
                "shares": shares,
                "capital": capital_used,
                "buy_cost": buy_cost,
                "score": signal_score(signal_row)
            }

        marked = cash
        for t, p in positions.items():
            if date in data[t].index:
                marked += p["shares"] * float(data[t].loc[date]["Close"])
        curve.append((date, marked))

    # Force-close any remaining positions at the final available close.
    if dates:
        final_date = dates[-1]
        for ticker in list(positions):
            p = positions[ticker]
            df = data[ticker]
            available = df[df.index <= final_date]
            if available.empty:
                continue

            final_row = available.iloc[-1]
            exit_px = float(final_row["Close"]) * (1 - SLIPPAGE_RATE)
            proceeds = p["shares"] * exit_px
            sell_cost = proceeds * COMMISSION_RATE
            cash += proceeds - sell_cost

            pnl = (
                (exit_px - p["entry"]) * p["shares"]
                - p["buy_cost"]
                - sell_cost
            )

            trades.append(Trade(
                ticker=ticker,
                entry_date=p["entry_date"].strftime("%Y-%m-%d"),
                exit_date=available.index[-1].strftime("%Y-%m-%d"),
                entry=p["entry"],
                exit=exit_px,
                shares=p["shares"],
                capital=p["capital"],
                pnl=pnl,
                return_pct=pnl / p["capital"],
                reason="end_of_test",
                hold_days=(available.index[-1] - p["entry_date"]).days,
                score=p["score"]
            ))

        curve.append((final_date, cash))

    trades_df = pd.DataFrame([t.__dict__ for t in trades])
    equity_df = pd.DataFrame(curve, columns=["date","equity"]).drop_duplicates("date").set_index("date")
    return trades_df, equity_df

def run_backtest(tickers=None, target=DEFAULT_TARGET, stop=DEFAULT_STOP,
                 initial_capital=INITIAL_CAPITAL, risk_per_trade=RISK_PER_TRADE,
                 max_positions=MAX_OPEN_POSITIONS, min_score=70, data=None):
    data = data if data is not None else load_data(tickers)
    if not data:
        return pd.DataFrame(), pd.DataFrame()
    return _backtest_data(
        data, target, stop, initial_capital, risk_per_trade,
        max_positions, min_score
    )

def summarise(trades, equity, initial_capital):
    final = float(equity["equity"].iloc[-1]) if not equity.empty else initial_capital
    dd = float((equity["equity"] / equity["equity"].cummax() - 1).min()) if not equity.empty else 0.0

    if trades.empty:
        return {
            "Total return": final / initial_capital - 1,
            "Win rate": 0.0,
            "Profit factor": 0.0,
            "Max drawdown": dd,
            "Trades": 0,
            "Avg trade": 0.0
        }

    wins = trades[trades["pnl"] > 0]
    losses = trades[trades["pnl"] <= 0]
    loss_total = abs(losses["pnl"].sum())

    return {
        "Total return": final / initial_capital - 1,
        "Win rate": len(wins) / len(trades),
        "Profit factor": wins["pnl"].sum() / loss_total if loss_total > 0 else float("inf"),
        "Max drawdown": dd,
        "Trades": len(trades),
        "Avg trade": float(trades["return_pct"].mean())
    }

def optimise_targets(tickers=None, targets=None, stop=DEFAULT_STOP,
                     initial_capital=INITIAL_CAPITAL,
                     risk_per_trade=RISK_PER_TRADE,
                     max_positions=MAX_OPEN_POSITIONS,
                     min_score=70, data=None):
    # Download ONCE, then run every target against the identical dataset.
    fixed_data = data if data is not None else load_data(tickers)

    rows = []
    for target in targets or [0.05,0.06,0.07,0.08,0.09,0.10]:
        trades, equity = run_backtest(
            target=target,
            stop=stop,
            initial_capital=initial_capital,
            risk_per_trade=risk_per_trade,
            max_positions=max_positions,
            min_score=min_score,
            data=fixed_data
        )
        s = summarise(trades, equity, initial_capital)
        rows.append({
            "Target": target,
            "Total Return": s["Total return"],
            "Win Rate": s["Win rate"],
            "Profit Factor": s["Profit factor"],
            "Max Drawdown": s["Max drawdown"],
            "Trades": s["Trades"],
            "Average Trade": s["Avg trade"]
        })

    return pd.DataFrame(rows)

def scan_current(tickers=None, min_score=70):
    rows = []
    for ticker in tickers or TICKERS:
        df = download(ticker)
        if df.empty:
            continue
        r = df.iloc[-1]
        score = signal_score(r)
        rows.append({
            "Ticker": ticker,
            "Price": float(r["Close"]),
            "Score": score,
            "RSI": float(r["RSI"]),
            "20d Momentum": float(r["MOM20"]),
            "60d Momentum": float(r["MOM60"]),
            "Volume Ratio": float(r["VOL_RATIO"]),
            "Above SMA50": bool(r["Close"] > r["SMA50"]),
            "SMA20>SMA50": bool(r["SMA20"] > r["SMA50"]),
            "SMA50>SMA200": bool(r["SMA50"] > r["SMA200"]),
            "Signal": "BUY" if score >= min_score else "WATCH"
        })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["Score","Volume Ratio"], ascending=False
    )
