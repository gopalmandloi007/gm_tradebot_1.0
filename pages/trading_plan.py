import streamlit as st
import pandas as pd

st.set_page_config(page_title="📘 Trading Plan & Risk Management", layout="wide")

st.title("📘 Trading Plan & Risk Management Dashboard")
st.markdown("""
💡 **Purpose:** This page summarizes your entire trading system — from capital allocation, risk per trade, expected value, and psychological rules for discipline.

---
""")

# === USER INPUTS ===
st.sidebar.header("🔧 Inputs")
total_capital = st.sidebar.number_input("💰 Total Capital (₹)", value=1112000, step=10000)
position_size = st.sidebar.number_input("📊 Position Size (₹)", value=111200)
risk_per_trade_pct = st.sidebar.number_input("⚠️ Risk per Trade (%)", value=2.0) / 100
reward_per_win_pct = st.sidebar.number_input("🎯 Reward per Win (%)", value=10.0) / 100
win_rate = st.sidebar.number_input("🏆 Win Rate (%)", value=35.0) / 100
target_profit_pct = st.sidebar.number_input("🚀 Yearly Target (%)", value=50.0) / 100
max_drawdown_pct = st.sidebar.number_input("🛑 Max Drawdown (%)", value=5.0) / 100
expected_time_per_trade_days = st.sidebar.number_input("⏳ Avg Time per Trade (Days)", value=10)

# === CALCULATIONS ===
risk_per_trade = position_size * risk_per_trade_pct
reward_per_trade = position_size * reward_per_win_pct
target_profit = total_capital * target_profit_pct
max_drawdown = total_capital * max_drawdown_pct

# Expected Value per Trade (EV)
EV = (reward_per_trade * win_rate) - (risk_per_trade * (1 - win_rate))

# Trades needed for yearly target
trades_needed = int(target_profit / EV) if EV > 0 else 0

# Expected time for target
expected_days = trades_needed * expected_time_per_trade_days
expected_months = round(expected_days / 30, 1)

# === DATA TABLE ===
data = {
    "Parameter": [
        "Total Capital", "Position Size", "Risk per Trade (2%)", "Reward per Win (10%)",
        "Win Rate (Accuracy)", "Target Profit (50% Yearly)", "Max Drawdown (5%)",
        "Expected Value (EV) per Trade", "Trades Needed for Target", "Expected Time for Target"
    ],
    "Value": [
        f"₹{total_capital:,.0f}", f"₹{position_size:,.0f}", f"₹{risk_per_trade:,.0f}", 
        f"₹{reward_per_trade:,.0f}", f"{win_rate*100:.1f}%", f"₹{target_profit:,.0f}", 
        f"₹{max_drawdown:,.0f}", f"₹{EV:,.1f}", f"{trades_needed:,}", f"{expected_months} months (~{expected_days} days)"
    ],
    "Notes": [
        "Trading Capital", "Per Trade Exposure", "Loss per trade allowed",
        "Target profit per trade", "Based on system performance", 
        "Expected yearly return goal", "Max total capital loss allowed",
        "Expected profit per trade (statistical edge)", 
        "Number of trades required to reach 50% target", 
        "Estimated time based on average trade duration"
    ]
}

df = pd.DataFrame(data)
st.subheader("📊 System Summary Table")
st.dataframe(df, use_container_width=True)

# === TRADING RULES ===
st.markdown("""
---
### 🧭 **Trading Discipline & Rules**

| Condition | Action | Notes |
|:--|:--|:--|
| ⚠️ Back-to-back 5 Stop Loss | 🔽 Reduce Position Size | Market not favorable, volatility high |
| 🚫 10 Consecutive Losses | ⏸ Stop Trading for 1 Week | Wait for improving market environment |
| 🧱 15 Consecutive Losses | ⏸ Stop Trading for 1 Month | Deep drawdown protection |
| ❌ 25 Stop Loss | 🧘‍♂️ Take Full Break | Review system and mindset |
| ✅ 5 Consecutive Targets | ⬆️ Increase Position Size | Compounding stage |
| 💡 EV < 0 | ⚠️ Reduce exposure | Market edge temporarily lost |
| 💪 EV > 0 and DD < 5% | 🔼 Maintain or scale | Continue systematic trades |

---

### 📈 **Capital Deployment Stages**

| Stage | Capital Allocation | Description |
|:--|:--|:--|
| 🧩 Stage-I | 10–20% | Testing phase — build confidence |
| 🧭 Stage-II | 30–50% | Risk financed, confidence improving |
| 🏗️ Stage-III | 100% | Fully financed, complete conviction |
| 🚀 Stage-IV | 100% + Compounding | Scaling with profits only |

---

### ⏰ **Expected Time System**

| Metric | Typical Duration |
|:--|:--|
| ⛔ Stop Loss Hit | 2–3 days |
| 🎯 Target Hit | 10–15 days |
| 📅 50% Yearly Goal | ~{expected_months} months |

---
""")

st.success("✅ **Discipline = Freedom.** When your risk is defined, your emotions are controlled. Stay systematic, not emotional.")
