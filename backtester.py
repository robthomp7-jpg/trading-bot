import pandas as pd
import yfinance as yf
from config import *
from strategy import add_indicators, signal_score

def download(ticker):
    try:
        df = yf.download(ticker, start=START_DATE, auto_adjust=True,
                          progress=False, threads=False)
        if df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        required = ["Open","High","Low","Close","Volume"]
        if any(c not in df.columns for c in required):
            return pd.DataFrame()
        return add_indicators(df)
    except Exception:
        return pd.DataFrame()

def load_data(tickers=None):
    result = {}
    for ticker in tickers or TICKERS:
        d = download(ticker)
        if not d.empty:
            result[ticker] = d
    return result

def count_signals(data, min_score=70):
    rows=[]
    for ticker, df in data.items():
        # Signal is based on a completed historical bar.
        for i in range(len(df)-1):
            r=df.iloc[i]
            s=signal_score(r)
            if s >= min_score:
                rows.append({
                    "Ticker":ticker,
                    "Signal date":df.index[i].strftime("%Y-%m-%d"),
                    "Entry date":df.index[i+1].strftime("%Y-%m-%d"),
                    "Score":s
                })
    return pd.DataFrame(rows)

def run_backtest(data, target=DEFAULT_TARGET, stop=DEFAULT_STOP,
                 initial_capital=INITIAL_CAPITAL,
                 risk_per_trade=RISK_PER_TRADE,
                 max_positions=MAX_OPEN_POSITIONS, min_score=70):
    # Simpler event-driven engine. Signals are collected first, then trades are
    # simulated from the next day's OPEN. This removes the previous nested
    # date/position interaction that was causing the optimiser to return zero.
    signals = count_signals(data, min_score)
    if signals.empty:
        return pd.DataFrame(), pd.DataFrame(), signals

    events={}
    for _, r in signals.iterrows():
        events.setdefault(r["Entry date"], []).append(r)

    cash=float(initial_capital)
    positions={}
    trades=[]
    equity_rows=[]

    dates=sorted(set().union(*(df.index for df in data.values())))

    for date in dates:
        ds=date.strftime("%Y-%m-%d")

        # exits
        for ticker in list(positions):
            p=positions[ticker]
            df=data[ticker]
            if date not in df.index:
                continue
            row=df.loc[date]
            op,hi,lo,cl=[float(row[x]) for x in ["Open","High","Low","Close"]]
            target_px=p["entry"]*(1+target)
            stop_px=p["entry"]*(1-stop)
            held=(date-p["entry_date"]).days
            reason=None
            exit_px=cl

            if op <= stop_px:
                reason,exit_px="stop_loss_gap",op
            elif op >= target_px:
                reason,exit_px="take_profit_gap",op
            elif lo <= stop_px:
                reason,exit_px="stop_loss",stop_px
            elif hi >= target_px:
                reason,exit_px="take_profit",target_px
            elif held >= MAX_HOLD_DAYS:
                reason="max_hold"

            if reason:
                exit_px*=1-SLIPPAGE_RATE
                proceeds=p["shares"]*exit_px
                sell_cost=proceeds*COMMISSION_RATE
                cash += proceeds-sell_cost
                pnl=(exit_px-p["entry"])*p["shares"]-p["buy_cost"]-sell_cost
                trades.append({
                    "ticker":ticker,"entry_date":p["entry_date"].strftime("%Y-%m-%d"),
                    "exit_date":date.strftime("%Y-%m-%d"),"entry":p["entry"],
                    "exit":exit_px,"shares":p["shares"],"capital":p["capital"],
                    "pnl":pnl,"return_pct":pnl/p["capital"],"reason":reason,
                    "hold_days":held,"score":p["score"]
                })
                del positions[ticker]

        # entries for this date
        for event in events.get(ds, []):
            if len(positions) >= max_positions:
                break
            ticker=event["Ticker"]
            if ticker in positions:
                continue
            df=data[ticker]
            if date not in df.index:
                continue

            open_px=float(df.loc[date,"Open"])
            if open_px <= 0:
                continue

            # Position sizing: 2% equity risk with the selected stop.
            marked=cash
            for t,p in positions.items():
                if date in data[t].index:
                    marked += p["shares"]*float(data[t].loc[date,"Close"])

            risk_cash=marked*risk_per_trade
            risk_per_share=open_px*stop
            shares=min(
                risk_cash/risk_per_share,
                cash/(open_px*(1+COMMISSION_RATE+SLIPPAGE_RATE))
            )
            if shares <= 0:
                continue

            entry_px=open_px*(1+SLIPPAGE_RATE)
            capital_used=shares*entry_px
            buy_cost=capital_used*COMMISSION_RATE
            if capital_used+buy_cost > cash:
                continue

            cash -= capital_used+buy_cost
            positions[ticker]={
                "entry":entry_px,"entry_date":date,"shares":shares,
                "capital":capital_used,"buy_cost":buy_cost,
                "score":int(event["Score"])
            }

        marked=cash
        for t,p in positions.items():
            if date in data[t].index:
                marked += p["shares"]*float(data[t].loc[date,"Close"])
        equity_rows.append((date,marked))

    # close anything left at final date
    if dates:
        final_date=dates[-1]
        for ticker in list(positions):
            p=positions[ticker]
            df=data[ticker]
            avail=df[df.index<=final_date]
            if avail.empty:
                continue
            row=avail.iloc[-1]
            exit_px=float(row["Close"])*(1-SLIPPAGE_RATE)
            proceeds=p["shares"]*exit_px
            sell_cost=proceeds*COMMISSION_RATE
            cash += proceeds-sell_cost
            pnl=(exit_px-p["entry"])*p["shares"]-p["buy_cost"]-sell_cost
            trades.append({
                "ticker":ticker,"entry_date":p["entry_date"].strftime("%Y-%m-%d"),
                "exit_date":avail.index[-1].strftime("%Y-%m-%d"),
                "entry":p["entry"],"exit":exit_px,"shares":p["shares"],
                "capital":p["capital"],"pnl":pnl,"return_pct":pnl/p["capital"],
                "reason":"end_of_test","hold_days":(avail.index[-1]-p["entry_date"]).days,
                "score":p["score"]
            })
        equity_rows.append((final_date,cash))

    trades_df=pd.DataFrame(trades)
    equity_df=pd.DataFrame(equity_rows,columns=["date","equity"]).drop_duplicates("date").set_index("date")
    return trades_df,equity_df,signals

def summarise(trades,equity,initial_capital):
    final=float(equity["equity"].iloc[-1]) if not equity.empty else initial_capital
    dd=float((equity["equity"]/equity["equity"].cummax()-1).min()) if not equity.empty else 0
    if trades.empty:
        return {"Total return":final/initial_capital-1,"Win rate":0,
                "Profit factor":0,"Max drawdown":dd,"Trades":0,"Avg trade":0}
    wins=trades[trades.pnl>0]
    losses=trades[trades.pnl<=0]
    loss=abs(losses.pnl.sum())
    return {"Total return":final/initial_capital-1,
            "Win rate":len(wins)/len(trades),
            "Profit factor":wins.pnl.sum()/loss if loss else float("inf"),
            "Max drawdown":dd,"Trades":len(trades),
            "Avg trade":float(trades.return_pct.mean())}

def optimise_targets(data, stop=DEFAULT_STOP,
                     initial_capital=INITIAL_CAPITAL,
                     risk_per_trade=RISK_PER_TRADE,
                     max_positions=MAX_OPEN_POSITIONS,min_score=70):
    rows=[]
    signals=count_signals(data,min_score)
    for target in [0.05,0.06,0.07,0.08,0.09,0.10]:
        tr,eq,_=run_backtest(data,target,stop,initial_capital,
                             risk_per_trade,max_positions,min_score)
        s=summarise(tr,eq,initial_capital)
        rows.append({
            "Target":target,"Total Return":s["Total return"],
            "Win Rate":s["Win rate"],"Profit Factor":s["Profit factor"],
            "Max Drawdown":s["Max drawdown"],"Trades":s["Trades"],
            "Average Trade":s["Avg trade"],"Signals Available":len(signals)
        })
    return pd.DataFrame(rows),signals

def scan_current(tickers=None,min_score=70):
    rows=[]
    for ticker in tickers or TICKERS:
        df=download(ticker)
        if df.empty: continue
        r=df.iloc[-1]; s=signal_score(r)
        rows.append({
            "Ticker":ticker,"Price":float(r.Close),"Score":s,
            "RSI":float(r.RSI),"20d Momentum":float(r.MOM20),
            "60d Momentum":float(r.MOM60),"Volume Ratio":float(r.VOL_RATIO),
            "Above SMA50":bool(r.Close>r.SMA50),
            "SMA20>SMA50":bool(r.SMA20>r.SMA50),
            "SMA50>SMA200":bool(r.SMA50>r.SMA200),
            "Signal":"BUY" if s>=min_score else "WATCH"
        })
    return pd.DataFrame(rows).sort_values(["Score","Volume Ratio"],ascending=False) if rows else pd.DataFrame()
