import streamlit as st
import plotly.express as px

from config import *
from backtester import load_data, run_backtest, summarise, optimise_targets, scan_current

st.set_page_config(page_title="Trading Bot V4", page_icon="📈", layout="wide")

st.title("📈 Momentum Swing Trading Bot — V4")
st.caption("Backtest / paper-trading research tool — no live orders are placed.")

with st.sidebar:
    st.header("Strategy controls")
    target = st.slider("Take-profit target", 5, 10, 7, 1) / 100
    stop = st.slider("Stop loss", 2, 6, 3, 1) / 100
    risk = st.slider("Risk per trade", 0.5, 3.0, 2.0, 0.25) / 100
    score = st.slider("Minimum signal score", 50, 90, 70, 5)
    positions = st.slider("Maximum open positions", 1, 10, 5)
    capital = st.number_input("Starting capital (£)", 1000.0, 1000000.0, 10000.0, 1000.0)

    st.divider()
    st.write(f"**Stocks scanned:** {len(TICKERS)}")
    st.write("**Signal:** previous completed day")
    st.write("**Entry:** next day's open")
    st.write("**Trading 212:** not connected")

if st.button("🔄 Clear cache & rerun everything"):
    st.cache_data.clear()
    st.rerun()

@st.cache_data(show_spinner="Downloading historical data once...")
def get_data():
    return load_data(TICKERS)

data = get_data()

@st.cache_data(show_spinner="Running backtest...")
def do_backtest(target, stop, capital, risk, positions, score):
    return run_backtest(
        target=target,
        stop=stop,
        initial_capital=capital,
        risk_per_trade=risk,
        max_positions=positions,
        min_score=score,
        data=data
    )

@st.cache_data(show_spinner="Optimising all targets using the same dataset...")
def do_optimiser(capital, risk, positions, score):
    return optimise_targets(
        initial_capital=capital,
        risk_per_trade=risk,
        max_positions=positions,
        min_score=score,
        data=data
    )

@st.cache_data(ttl=900, show_spinner="Scanning stocks...")
def do_scan(score):
    return scan_current(TICKERS, min_score=score)

trades, equity = do_backtest(target, stop, capital, risk, positions, score)
summary = summarise(trades, equity, capital)

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Final equity", f"£{equity.equity.iloc[-1]:,.0f}" if not equity.empty else "—")
c2.metric("Total return", f"{summary['Total return']*100:.1f}%")
c3.metric("Win rate", f"{summary['Win rate']*100:.1f}%")
c4.metric("Profit factor", f"{summary['Profit factor']:.2f}")
c5.metric("Max drawdown", f"{summary['Max drawdown']*100:.1f}%")

tab1,tab2,tab3,tab4 = st.tabs([
    "📈 Backtest","🎯 Target optimiser","🔎 Opportunity scanner","📋 Trades"
])

with tab1:
    st.subheader("Equity curve")
    if not equity.empty:
        st.plotly_chart(
            px.line(equity.reset_index(), x="date", y="equity"),
            use_container_width=True
        )

    if not trades.empty:
        wl = trades.assign(
            Result=trades["pnl"].apply(lambda x: "Win" if x > 0 else "Loss")
        ).groupby("Result").size().reset_index(name="Trades")
        st.plotly_chart(
            px.bar(wl, x="Result", y="Trades"),
            use_container_width=True
        )

        a,b,c = st.columns(3)
        a.metric("Average trade", f"{summary['Avg trade']*100:.2f}%")
        b.metric(
            "Average winner",
            f"{trades.loc[trades.pnl>0,'return_pct'].mean()*100:.2f}%"
            if (trades.pnl>0).any() else "—"
        )
        b.metric(
            "Average loser",
            f"{trades.loc[trades.pnl<=0,'return_pct'].mean()*100:.2f}%"
            if (trades.pnl<=0).any() else "—"
        )

with tab2:
    st.subheader("Which profit target works best?")
    st.write(
        "Each target is tested independently against the exact same historical dataset. "
        "Signals and entry dates are identical; only the exit target changes."
    )

    o = do_optimiser(capital, risk, positions, score)

    shown = o.copy()
    for col in ["Total Return","Win Rate","Max Drawdown","Average Trade"]:
        shown[col] = shown[col].map(lambda x: f"{x*100:.1f}%")
    shown["Target"] = shown["Target"].map(lambda x: f"{x*100:.0f}%")

    st.dataframe(shown, use_container_width=True, hide_index=True)

    st.plotly_chart(
        px.line(o, x="Target", y="Total Return", markers=True),
        use_container_width=True
    )

    st.info(
        "V4 also force-closes open positions at the end of the test, so a target "
        "cannot show 0 trades simply because positions were still open."
    )

with tab3:
    st.subheader("Ranked opportunities")
    s = do_scan(score)

    if s.empty:
        st.info("No scan results returned.")
    else:
        st.dataframe(s, use_container_width=True, hide_index=True)
        buys = s[s["Signal"]=="BUY"]
        if len(buys):
            st.success(f"{len(buys)} stock(s) currently meet the {score}/100 threshold.")
        else:
            st.info(f"No stocks currently meet the {score}/100 threshold.")

with tab4:
    st.subheader("Individual trades")
    if trades.empty:
        st.info("No trades generated.")
    else:
        v = trades.sort_values("exit_date", ascending=False).copy()
        v["Result"] = v["pnl"].apply(lambda x: "WIN" if x > 0 else "LOSS")
        v["Return"] = v["return_pct"].map(lambda x: f"{x*100:.2f}%")
        v["P/L"] = v["pnl"].map(lambda x: f"£{x:,.2f}")

        st.dataframe(
            v[[
                "ticker","entry_date","exit_date","entry","exit",
                "capital","P/L","Return","Result","reason",
                "hold_days","score"
            ]],
            use_container_width=True,
            hide_index=True
        )

st.divider()
st.caption(
    "Important: historical backtests are hypothetical and do not guarantee future "
    "results. Paper trade before risking real money."
)
