import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime

# ---------------------- PAGE CONFIG ----------------------
st.set_page_config(page_title="Final Holdings Dashboard", layout="wide")
st.title("📊 GM TRADEBOT 1.0 – Final Holdings Dashboard")

# ---------------------- DATA INPUT ----------------------
st.markdown("### 📂 Upload your trades file (CSV Format)")
uploaded_file = st.file_uploader("Upload your trade data file", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
else:
    st.info("👆 Please upload your trade CSV file first.")
    st.stop()

# ---------------------- DATA CLEANING ----------------------
required_cols = ['symbol', 'entry_date', 'exit_date', 'entry_price', 'exit_price', 'stop_loss', 'qty']
for col in required_cols:
    if col not in df.columns:
        st.error(f"❌ Missing required column: {col}")
        st.stop()

df['entry_date'] = pd.to_datetime(df['entry_date'], errors='coerce')
df['exit_date'] = pd.to_datetime(df['exit_date'], errors='coerce')
today = pd.Timestamp.today().normalize()
df['status'] = np.where(df['exit_date'].isna(), 'Open', 'Closed')
df['exit_price'] = df['exit_price'].fillna(df['entry_price'])

# ---------------------- CORE CALCULATIONS ----------------------
df['pnl'] = (df['exit_price'] - df['entry_price']) * df['qty']
df['initial_risk'] = (df['entry_price'] - df['stop_loss']) * df['qty']
df['R_multiple'] = np.where(df['initial_risk'] > 0, df['pnl'] / df['initial_risk'], 0)

# Holding Days
df['holding_days'] = (df['exit_date'].fillna(today) - df['entry_date']).dt.days

# Expected trade durations
avg_win_days = 16  # (12–20)
avg_loss_days = 4  # (3–5)
df['expected_days'] = np.where(df['pnl'] > 0, avg_win_days, avg_loss_days)

# ---------------------- METRICS ----------------------
total_trades = len(df)
win_trades = len(df[df['pnl'] > 0])
loss_trades = len(df[df['pnl'] < 0])
open_trades = len(df[df['status'] == 'Open'])
win_rate = (win_trades / (win_trades + loss_trades)) * 100 if total_trades > 0 else 0

total_pnl = float(df['pnl'].sum())
total_risk = float(df['initial_risk'].sum())
total_open_risk = float(df[df['status'] == 'Open']['initial_risk'].sum())

# ---------------------- MAX DRAWDOWN ----------------------
df['equity_curve'] = df['pnl'].cumsum()
roll_max = df['equity_curve'].cummax()
drawdown = df['equity_curve'] - roll_max
max_drawdown = float(drawdown.min())

# ---------------------- SUMMARY METRICS DISPLAY ----------------------
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total Trades", total_trades)
k2.metric("Win Rate", f"{win_rate:.2f}%")
k3.metric("Total P&L", f"₹{total_pnl:,.2f}")
k4.metric("Total Risk", f"₹{total_risk:,.2f}")
k5.metric("Open Risk (TSL)", f"₹{total_open_risk:,.2f}")
k6.metric("Max Drawdown", f"₹{max_drawdown:,.2f}")

# ---------------------- CURRENT PHASE DETECTION ----------------------
recent_trades = df.tail(6)
recent_positive = (recent_trades['pnl'] > 0).sum()
recent_negative = (recent_trades['pnl'] < 0).sum()

if recent_positive > recent_negative + 1:
    phase = "🔥 Momentum / Winning Phase"
elif recent_negative > recent_positive + 1:
    phase = "⚠️ Cooling / Drawdown Phase"
else:
    phase = "⏳ Neutral / Sideways Phase"

st.subheader(f"📈 Current Phase: {phase}")

# ---------------------- CHART 1: R-MULTIPLE ----------------------
st.markdown("### 📊 R Multiple per Trade")
fig_r = px.bar(
    df.sort_values('R_multiple', ascending=False),
    x='symbol',
    y='R_multiple',
    color='status',
    title='R Multiple by Symbol',
    color_discrete_map={'Closed': 'green', 'Open': 'orange'}
)
st.plotly_chart(fig_r, use_container_width=True)

# ---------------------- CHART 2: EXPECTED VS ACTUAL ----------------------
st.markdown("### ⏱️ Expected vs Actual Holding Days")
fig_days = px.scatter(
    df,
    x='expected_days',
    y='holding_days',
    color='status',
    size='R_multiple',
    hover_data=['symbol', 'pnl'],
    title='Expected vs Actual Holding Duration'
)
st.plotly_chart(fig_days, use_container_width=True)

# ---------------------- CHART 3: EQUITY CURVE ----------------------
st.markdown("### 💰 Equity Curve (Cumulative P&L)")
fig_eq = px.line(df, x=df.index, y='equity_curve', title='Cumulative P&L over Trades')
st.plotly_chart(fig_eq, use_container_width=True)

# ---------------------- TABLE: DETAILED SUMMARY ----------------------
st.markdown("### 📋 Detailed Trade Summary")
st.dataframe(df[['symbol', 'entry_date', 'exit_date', 'status', 'holding_days', 'expected_days', 'R_multiple', 'pnl']])

# ---------------------- PERFORMANCE MARKDOWN SUMMARY ----------------------
st.markdown("### 🧾 Markdown Performance Summary")
top_r = df.sort_values('R_multiple', ascending=False).head(10)
bottom_r = df.sort_values('R_multiple', ascending=True).head(10)

st.markdown("#### 🔝 Top 10 Trades by R Multiple")
st.dataframe(top_r[['symbol', 'R_multiple', 'pnl', 'holding_days']])

st.markdown("#### 🔻 Bottom 10 Trades by R Multiple")
st.dataframe(bottom_r[['symbol', 'R_multiple', 'pnl', 'holding_days']])

# ---------------------- SUMMARY INSIGHTS ----------------------
st.markdown("### 🧠 Key Insights")
avg_R = df['R_multiple'].mean()
avg_holding = df['holding_days'].mean()

colA, colB = st.columns(2)
colA.metric("Average R per Trade", f"{avg_R:.2f}")
colB.metric("Average Holding Days", f"{avg_holding:.1f}")

if avg_R > 1.5:
    st.success("✅ Your average R multiple is excellent! Keep following your plan.")
elif 0.8 <= avg_R <= 1.5:
    st.info("⚖️ Stable performance. Watch for consistency.")
else:
    st.warning("📉 Average R below 0.8 — review entries or stop-loss discipline.")

# ---------------------- AUTO PHASE COMMENT ----------------------
if "Winning" in phase:
    st.markdown("🚀 You're in a strong phase — avoid over-leveraging but keep confidence high.")
elif "Cooling" in phase:
    st.markdown("🧊 Current phase is cooling down — reduce position size, protect capital.")
else:
    st.markdown("😐 Neutral phase — ideal for scanning new setups and building watchlists.")

# ---------------------- EXPORT OPTION ----------------------
st.markdown("### 💾 Export Processed Data")
csv = df.to_csv(index=False).encode('utf-8')
st.download_button("Download Updated Trade Summary (CSV)", csv, "trade_summary_processed.csv", "text/csv")

# ---------------------- END ----------------------
st.success("✅ Dashboard Updated Successfully!")
