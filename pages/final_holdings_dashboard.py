import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime

# ---------------------------- PAGE CONFIG ----------------------------
st.set_page_config(page_title="GM TradeBot 1.0 – Final Holdings Dashboard", layout="wide")
st.title("📊 GM TRADEBOT 1.0 – Final Holdings Dashboard")

# ---------------------------- FILE UPLOAD ----------------------------
st.markdown("### 📂 Upload Your Trade Log (CSV Format)")
uploaded_file = st.file_uploader("Upload your trade log CSV file", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
else:
    st.info("👆 Please upload your trade file to start analysis.")
    st.stop()

# ---------------------------- VALIDATION ----------------------------
required_cols = [
    'symbol', 'entry_date', 'exit_date',
    'entry_price', 'exit_price', 'stop_loss', 'qty'
]

missing = [c for c in required_cols if c not in df.columns]
if missing:
    st.error(f"❌ Missing columns in CSV: {missing}")
    st.stop()

# ---------------------------- DATA CLEANING ----------------------------
df['entry_date'] = pd.to_datetime(df['entry_date'], errors='coerce')
df['exit_date'] = pd.to_datetime(df['exit_date'], errors='coerce')
today = pd.Timestamp.today().normalize()

df['status'] = np.where(df['exit_date'].isna(), 'Open', 'Closed')
df['exit_price'] = df['exit_price'].fillna(df['entry_price'])
df['pnl'] = (df['exit_price'] - df['entry_price']) * df['qty']
df['initial_risk'] = (df['entry_price'] - df['stop_loss']) * df['qty']
df['R_multiple'] = np.where(df['initial_risk'] > 0, df['pnl'] / df['initial_risk'], 0)
df['holding_days'] = (df['exit_date'].fillna(today) - df['entry_date']).dt.days

# Expected holding duration assumptions
avg_win_days = 16
avg_loss_days = 4
df['expected_days'] = np.where(df['pnl'] > 0, avg_win_days, avg_loss_days)

# Remove duplicate columns (Main Fix)
df = df.loc[:, ~df.columns.duplicated()].copy()

# ---------------------------- CALCULATIONS ----------------------------
total_trades = len(df)
win_trades = len(df[df['pnl'] > 0])
loss_trades = len(df[df['pnl'] < 0])
open_trades = len(df[df['status'] == 'Open'])
win_rate = (win_trades / (win_trades + loss_trades) * 100) if (win_trades + loss_trades) > 0 else 0

total_pnl = float(df['pnl'].sum())
total_risk = float(df['initial_risk'].sum())
open_risk = float(df[df['status'] == 'Open']['initial_risk'].sum())

# Equity curve and drawdown
df['equity_curve'] = df['pnl'].cumsum()
df['rolling_max'] = df['equity_curve'].cummax()
df['drawdown'] = df['equity_curve'] - df['rolling_max']
max_drawdown = float(df['drawdown'].min())

# Capital allocation % estimate
total_capital = st.number_input("💰 Enter Your Total Capital", value=1_000_000, step=10_000)
df['capital_allocation_%'] = (df['entry_price'] * df['qty']) / total_capital * 100

# ---------------------------- SUMMARY METRICS ----------------------------
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Total Trades", total_trades)
col2.metric("Win Rate", f"{win_rate:.2f}%")
col3.metric("Total P&L", f"₹{total_pnl:,.2f}")
col4.metric("Total Risk", f"₹{total_risk:,.2f}")
col5.metric("Open Risk (TSL)", f"₹{open_risk:,.2f}")
col6.metric("Max Drawdown", f"₹{max_drawdown:,.2f}")

# ---------------------------- CURRENT PHASE ----------------------------
recent = df.tail(8)
recent_wins = (recent['pnl'] > 0).sum()
recent_losses = (recent['pnl'] < 0).sum()

if recent_wins > recent_losses + 2:
    phase = "🔥 Winning / Momentum Phase"
elif recent_losses > recent_wins + 2:
    phase = "🧊 Cooling / Drawdown Phase"
else:
    phase = "⏳ Neutral / Sideways Phase"

st.subheader(f"📈 Current Trading Phase: {phase}")

# ---------------------------- EXPECTED TIME CALC ----------------------------
avg_R = df['R_multiple'].mean()
avg_hold = df['holding_days'].mean()
expected_trades_for_target = st.number_input("🎯 Enter Target Profit (₹)", value=500000)
ev_per_trade = avg_R * 2000  # assume 2% risk = ₹2000 base risk
expected_days_to_target = (expected_trades_for_target / ev_per_trade) * avg_hold

st.markdown(f"⏱️ **Expected Trades:** {expected_trades_for_target/ev_per_trade:.0f}  |  🗓️ **Expected Time:** {expected_days_to_target:.0f} days")

# ---------------------------- CHARTS ----------------------------
st.markdown("### 📊 R Multiple per Trade")
fig_r = px.bar(df, x='symbol', y='R_multiple', color='status', title='R Multiple by Trade')
st.plotly_chart(fig_r, use_container_width=True)

st.markdown("### 💰 Cumulative Equity Curve")
fig_eq = px.line(df, x=df.index, y='equity_curve', title='Equity Curve (Cumulative P&L)')
st.plotly_chart(fig_eq, use_container_width=True)

st.markdown("### ⏱️ Expected vs Actual Holding Days")
fig_time = px.scatter(
    df, x='expected_days', y='holding_days', color='status',
    hover_data=['symbol', 'pnl'], size='R_multiple', title='Expected vs Actual Holding Duration'
)
st.plotly_chart(fig_time, use_container_width=True)

# ---------------------------- DATAFRAME DISPLAY ----------------------------
st.markdown("### 📋 Detailed Trade Summary")

display_cols = [
    'symbol', 'entry_date', 'exit_date', 'status', 'capital_allocation_%',
    'R_multiple', 'pnl', 'holding_days', 'expected_days'
]

if 'capital_allocation_%' in df.columns:
    st.dataframe(
        df[[c for c in display_cols if c in df.columns]]
        .sort_values(by='capital_allocation_%', ascending=False)
        .reset_index(drop=True),
        use_container_width=True
    )
else:
    st.dataframe(df)

# ---------------------------- INSIGHTS ----------------------------
st.markdown("### 🧠 Key Insights")

colA, colB = st.columns(2)
colA.metric("Average R per Trade", f"{avg_R:.2f}")
colB.metric("Average Holding Days", f"{avg_hold:.1f}")

if avg_R > 1.5:
    st.success("✅ Strong system performance – your R multiple is excellent!")
elif 0.8 <= avg_R <= 1.5:
    st.info("⚖️ Moderate performance – maintain discipline and consistency.")
else:
    st.warning("📉 Weak R multiple – review trade setups or SL management.")

if "Winning" in phase:
    st.markdown("🚀 You're in a winning phase – ride momentum but avoid overconfidence.")
elif "Cooling" in phase:
    st.markdown("🧊 Cooling phase – reduce position size, preserve profits.")
else:
    st.markdown("😐 Neutral phase – scan markets, avoid impulsive trades.")

# ---------------------------- EXPORT ----------------------------
st.markdown("### 💾 Export Updated Data")
csv = df.to_csv(index=False).encode('utf-8')
st.download_button("Download Processed Trade Summary", csv, "trade_summary.csv", "text/csv")

# ---------------------------- END ----------------------------
st.success("✅ Dashboard updated successfully! Ready to analyze next session.")
