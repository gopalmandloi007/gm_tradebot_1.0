import streamlit as st
import pandas as pd
import plotly.express as px

# ------------------- PAGE CONFIG -------------------
st.set_page_config(
    page_title="📊 Trading Plan Dashboard",
    page_icon="💹",
    layout="wide",
)

st.title("💹 **Trading Risk & Reward Management System**")
st.caption("By Gopal Mandloi | Designed for disciplined & systematic trading 🧠⚡")

# ------------------- INPUTS -------------------
st.sidebar.header("⚙️ Input Parameters")

total_capital = st.sidebar.number_input("💰 Total Capital (₹)", value=1112000.0, step=10000.0)
win_rate = st.sidebar.slider("✅ Win Rate (%)", min_value=10, max_value=90, value=35)
risk_per_trade = st.sidebar.number_input("📉 Risk per Trade (₹)", value=2224.0, step=500.0)
reward_per_win = st.sidebar.number_input("💵 Reward per Win (₹)", value=11120.0, step=1000.0)
target_profit = st.sidebar.number_input("🎯 Target Profit (₹)", value=556000.0, step=10000.0)
max_drawdown = st.sidebar.number_input("⚠️ Max Drawdown Allowed (%)", value=5.0)
avg_trade_days = st.sidebar.slider("🗓️ Avg Duration per Trade (Days)", 1, 30, 10)

st.sidebar.markdown("---")

st.sidebar.markdown("### 📎 Upload Portfolio CSV")
uploaded_file = st.sidebar.file_uploader("Upload CSV with columns:", type=["csv"])
st.sidebar.markdown("`symbol, avg_buy, sl_price, ltp, quantity`")

# ------------------- SAMPLE DATA -------------------
if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
else:
    df = pd.DataFrame({
        "symbol": ["RELIANCE", "INFY", "HDFCBANK", "TCS", "ITC"],
        "avg_buy": [2500, 1550, 1580, 3650, 440],
        "sl_price": [2450, 1500, 1550, 3550, 425],
        "ltp": [2700, 1600, 1700, 3800, 450],
        "quantity": [20, 30, 25, 10, 50]
    })

# ------------------- CALCULATIONS -------------------
df["invested"] = df["avg_buy"] * df["quantity"]
df["current_value"] = df["ltp"] * df["quantity"]
df["unrealized_pnl"] = df["current_value"] - df["invested"]
df["initial_risk"] = (df["avg_buy"] - df["sl_price"]) * df["quantity"]
df["current_r_multiple"] = (df["ltp"] - df["avg_buy"]) / (df["avg_buy"] - df["sl_price"])
df["expected_value_per_trade"] = (win_rate/100 * reward_per_win) - ((1 - win_rate/100) * risk_per_trade)

# Make numeric (important fix)
numeric_cols = ["initial_risk", "unrealized_pnl"]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

# ------------------- METRICS SUMMARY -------------------
total_invested = df["invested"].sum()
total_pnl = df["unrealized_pnl"].sum()
max_possible_loss = df["initial_risk"].sum()
expected_value = df["expected_value_per_trade"].mean()
trades_needed = target_profit / expected_value
expected_days = trades_needed * avg_trade_days
expected_months = expected_days / 30

st.markdown("## ⚖️ Portfolio Summary")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Capital", f"₹{total_capital:,.0f}")
col2.metric("Invested Capital", f"₹{total_invested:,.0f}")
col3.metric("Total Unrealized P&L", f"₹{total_pnl:,.0f}")
col4.metric("Max Drawdown (All SL Hit)", f"₹{max_possible_loss:,.0f}")

# ------------------- CHARTS -------------------
st.markdown("## 📈 Risk vs Reward Overview")

fig_bar = px.bar(
    df,
    x="symbol",
    y=["initial_risk", "unrealized_pnl"],
    barmode="group",
    title="Risk (SL) vs Unrealized P&L per Symbol",
    labels={"value": "Amount (₹)", "symbol": "Stock"},
    color_discrete_sequence=px.colors.qualitative.Set2
)
st.plotly_chart(fig_bar, use_container_width=True)

# ------------------- HIGH R MULTIPLE -------------------
st.markdown("## 🔥 High-R Stocks (5R or more)")
high_r_df = df[df["current_r_multiple"] >= 5]

if not high_r_df.empty:
    st.dataframe(high_r_df[["symbol", "current_r_multiple", "unrealized_pnl"]])
else:
    st.info("No stocks with >5R yet — stay patient & disciplined. ⚖️")

# ------------------- EXPECTED VALUE & TIME -------------------
st.markdown("## 🕒 Expected Value & Time Forecast")
st.markdown(f"""
**🎯 Expected Value per Trade:** ₹{expected_value:,.2f}  
**📊 Trades Needed for 50% Gain:** {trades_needed:,.0f}  
**⏳ Expected Duration:** ~{expected_days:,.0f} days (≈ {expected_months:,.1f} months)
""")

# ------------------- STRATEGY GUIDELINES -------------------
st.markdown("## 🧭 Position Management Strategy")

st.markdown("""
| Stage | Capital Used | Condition | Action |
|-------|---------------|------------|---------|
| **Stage-I** | 10–20% | Initial testing | Start small, observe performance |
| **Stage-II** | 30–50% | 1 Profitable Trade | Increase position size (risk financed) |
| **Stage-III** | 100% | 8–10 Profitable Trades | Fully financed stage |
| **Stage-IV** | 100% + | 10+ Profitable Trades | Compound position sizing |
""")

st.markdown("""
### ⚠️ **Risk Control Rules**
- ⛔ **Slow Down** after 5 back-to-back stop losses  
- 🛑 **Stop Trading 1 Week** after 10 continuous SL  
- 🚫 **Stop Trading 1 Month** after 15 continuous SL  
- 🧘 **Break Taken** after 25 SL — review system  
- 📈 **Increase Position Size** after 5 consecutive target hits  
""")

st.success("✅ Dashboard ready! Use data-driven discipline — not emotions — to win the market. 💹")

# Footer
st.markdown("---")
st.caption("Developed by Gopal Mandloi | 💡 Focus: Trading Psychology + Quantitative Discipline")
