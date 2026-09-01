import streamlit as st
import plotly.express as px
from backtester import run_backtest, scan_current
from config import *

st.set_page_config(page_title="Momentum Trading Bot", page_icon="📈", layout="wide")
st.title("📈 Momentum Swing Trading Bot")
st.caption("Backtest + stock scanner dashboard | Default target +7% / stop -3%")

@st.cache_data(show_spinner="Running historical backtest...")
def get_backtest():
    return run_backtest()

@st.cache_data(ttl=900, show_spinner="Scanning current market data...")
def get_scan():
    return scan_current()

trades, equity = get_backtest()
scan = get_scan()

if trades.empty:
    st.error("No trades were generated. Try a wider date range or a larger stock universe.")
    st.stop()

wins = trades[trades.pnl > 0]
losses = trades[trades.pnl <= 0]
final_equity = float(equity.iloc[-1].equity)
total_return = final_equity / INITIAL_CAPITAL - 1
max_dd = (equity.equity / equity.equity.cummax() - 1).min()
pf = wins.pnl.sum() / abs(losses.pnl.sum()) if len(losses) else float("inf")

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Final equity", f"£{final_equity:,.0f}")
c2.metric("Total return", f"{total_return*100:.1f}%")
c3.metric("Win rate", f"{len(wins)/len(trades)*100:.1f}%")
c4.metric("Profit factor", f"{pf:.2f}")
c5.metric("Max drawdown", f"{max_dd*100:.1f}%")

st.subheader("Equity curve")
eq = equity.reset_index()
fig = px.line(eq, x="date", y="equity", title="Portfolio equity")
fig.update_layout(yaxis_title="£", xaxis_title="")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Win / loss statistics")
a,b = st.columns(2)
with a:
    stats = {
        "Trades": len(trades),
        "Winners": len(wins),
        "Losers": len(losses),
        "Average trade": f"{trades.return_pct.mean()*100:.2f}%",
        "Average winner": f"{wins.return_pct.mean()*100:.2f}%" if len(wins) else "n/a",
        "Average loser": f"{losses.return_pct.mean()*100:.2f}%" if len(losses) else "n/a",
    }
    st.dataframe(stats.items(), use_container_width=True, hide_index=True)
with b:
    wl = trades.assign(Result=trades.pnl.apply(lambda x:"Win" if x>0 else "Loss")).groupby("Result").size().reset_index(name="Trades")
    st.plotly_chart(px.bar(wl,x="Result",y="Trades",title="Wins vs losses"),use_container_width=True)

st.subheader("Individual trades")
st.dataframe(trades.sort_values("exit_date", ascending=False), use_container_width=True, hide_index=True)

st.subheader("Stocks the bot is finding")
st.dataframe(scan, use_container_width=True, hide_index=True)

st.info("This is a research/backtesting tool, not a guarantee of returns. Use paper trading before risking real money.")
