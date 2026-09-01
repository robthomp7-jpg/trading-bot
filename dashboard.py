import streamlit as st
import plotly.express as px
from config import *
from backtester import load_data,run_backtest,summarise,optimise_targets,scan_current

st.set_page_config(page_title="Trading Bot V5",page_icon="📈",layout="wide")
st.title("📈 Momentum Swing Trading Bot — V5")
st.caption("Diagnostic backtest engine. No live orders are placed.")

with st.sidebar:
    st.header("Controls")
    target=st.slider("Take-profit target",5,10,7,1)/100
    stop=st.slider("Stop loss",2,6,3,1)/100
    risk=st.slider("Risk per trade",0.5,3.0,2.0,0.25)/100
    score=st.slider("Minimum signal score",50,90,70,5)
    positions=st.slider("Maximum open positions",1,10,5)
    capital=st.number_input("Starting capital (£)",1000.0,1000000.0,10000.0,1000.0)
    if st.button("🔄 Clear cache & reload"):
        st.cache_data.clear()
        st.rerun()

@st.cache_data(show_spinner="Downloading historical data...")
def get_data():
    return load_data(TICKERS)

data=get_data()

st.subheader("Engine diagnostics")
d1,d2,d3,d4=st.columns(4)
d1.metric("Stocks with data",len(data))
d2.metric("Stocks requested",len(TICKERS))
total_rows=sum(len(x) for x in data.values())
d3.metric("Historical rows",f"{total_rows:,}")

# Always calculate signals independently before the optimiser.
signals = __import__("backtester").count_signals(data,score)
d4.metric("Qualifying signals",len(signals))

if len(data)==0:
    st.error("No historical data was downloaded. This is a data connection problem, not a strategy result.")
elif len(signals)==0:
    st.error("Historical data is present, but no qualifying signals exist at the selected score. Lower Minimum signal score to 50 temporarily to diagnose.")
else:
    st.success(f"V5 found {len(signals):,} qualifying historical signals at score ≥ {score}.")

@st.cache_data(show_spinner="Running selected backtest...")
def selected_bt(target,stop,capital,risk,positions,score):
    return run_backtest(data,target,stop,capital,risk,positions,score)

@st.cache_data(show_spinner="Testing 5%-10% targets...")
def optimiser(capital,risk,positions,score,stop):
    return optimise_targets(data,stop,capital,risk,positions,score)

trades,equity,selected_signals=selected_bt(target,stop,capital,risk,positions,score)
summary=summarise(trades,equity,capital)

c1,c2,c3,c4,c5=st.columns(5)
c1.metric("Final equity",f"£{equity.equity.iloc[-1]:,.0f}" if not equity.empty else "—")
c2.metric("Return",f"{summary['Total return']*100:.1f}%")
c3.metric("Win rate",f"{summary['Win rate']*100:.1f}%")
c4.metric("Profit factor",f"{summary['Profit factor']:.2f}")
c5.metric("Trades",summary["Trades"])

tab1,tab2,tab3,tab4=st.tabs(["📈 Backtest","🎯 Target optimiser","🔎 Scanner","📋 Trades"])

with tab1:
    st.subheader("Equity curve")
    if not equity.empty:
        st.plotly_chart(px.line(equity.reset_index(),x="date",y="equity"),use_container_width=True)
    st.subheader("Signals vs actual trades")
    a,b=st.columns(2)
    a.metric("Qualifying signals",len(selected_signals))
    b.metric("Executed trades",len(trades))
    if not selected_signals.empty:
        st.dataframe(selected_signals.head(25),use_container_width=True,hide_index=True)

with tab2:
    st.subheader("Which profit target works best?")
    o,all_signals=optimiser(capital,risk,positions,score,stop)
    shown=o.copy()
    for col in ["Total Return","Win Rate","Max Drawdown","Average Trade"]:
        shown[col]=shown[col].map(lambda x:f"{x*100:.1f}%")
    shown["Target"]=shown["Target"].map(lambda x:f"{x*100:.0f}%")
    st.dataframe(shown,use_container_width=True,hide_index=True)
    st.plotly_chart(px.line(o,x="Target",y="Total Return",markers=True),use_container_width=True)
    st.caption(f"Every target has {len(all_signals):,} qualifying signals available. Only the exit target changes.")

with tab3:
    st.subheader("Ranked opportunities")
    s=scan_current(TICKERS,score)
    if s.empty: st.info("No scan results returned.")
    else:
        st.dataframe(s,use_container_width=True,hide_index=True)
        buys=s[s.Signal=="BUY"]
        st.success(f"{len(buys)} stocks currently meet the {score}/100 threshold." if len(buys) else "No stocks currently meet the threshold.")

with tab4:
    st.subheader("Individual trades")
    if trades.empty: st.info("No trades were executed.")
    else:
        v=trades.sort_values("exit_date",ascending=False).copy()
        v["Result"]=v.pnl.apply(lambda x:"WIN" if x>0 else "LOSS")
        v["Return"]=v.return_pct.map(lambda x:f"{x*100:.2f}%")
        v["P/L"]=v.pnl.map(lambda x:f"£{x:,.2f}")
        st.dataframe(v[["ticker","entry_date","exit_date","entry","exit","capital","P/L","Return","Result","reason","hold_days","score"]],
                     use_container_width=True,hide_index=True)

st.divider()
st.caption("Historical results are hypothetical. They are not a guarantee of future performance. Paper trade before risking real money.")
