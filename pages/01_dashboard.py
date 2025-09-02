import streamlit as st
import pandas as pd
import requests
import traceback
import matplotlib.pyplot as plt

# ------------------ Constants ------------------ #
DEFAULT_TOTAL_CAPITAL = 100000
DEFAULT_RISK_PER_TRADE = 1.0
DEFAULT_RISK_PER_DAY = 3.0

# ------------------ Sidebar Config ------------------ #
st.sidebar.header("⚙️ Risk Management Settings")
capital = st.sidebar.number_input(
    "Total Capital (₹)", value=DEFAULT_TOTAL_CAPITAL, step=10000, key="capital_input"
)
risk_per_trade_pct = st.sidebar.number_input(
    "Risk per Trade (%)", value=DEFAULT_RISK_PER_TRADE, step=0.5, key="risk_trade_input"
)
risk_per_day_pct = st.sidebar.number_input(
    "Max Risk per Day (%)", value=DEFAULT_RISK_PER_DAY, step=0.5, key="risk_day_input"
)
strategy = st.sidebar.selectbox(
    "Trading Strategy", ["Intraday", "Swing"], index=0, key="strategy_select"
)

# ------------------ Dummy Holdings ------------------ #
holdings_data = [
    {"symbol": "TCS", "qty": 10, "avg_price": 3200, "ltp": 3250, "prev_close": 3230, "sector": "IT"},
    {"symbol": "HDFCBANK", "qty": 20, "avg_price": 1500, "ltp": 1480, "prev_close": 1495, "sector": "Banking"},
    {"symbol": "RELIANCE", "qty": 5, "avg_price": 2500, "ltp": 2550, "prev_close": 2525, "sector": "Energy"},
]

holdings_df = pd.DataFrame(holdings_data)

# ------------------ Calculations ------------------ #
holdings_df["investment"] = holdings_df["qty"] * holdings_df["avg_price"]
holdings_df["current_value"] = holdings_df["qty"] * holdings_df["ltp"]
holdings_df["pnl"] = holdings_df["current_value"] - holdings_df["investment"]
holdings_df["pnl_pct"] = (holdings_df["pnl"] / holdings_df["investment"]) * 100
holdings_df["daily_return"] = ((holdings_df["ltp"] - holdings_df["prev_close"]) / holdings_df["prev_close"]) * 100

# Risk per trade capital allocation
max_loss_per_trade = capital * (risk_per_trade_pct / 100.0)
max_loss_per_day = capital * (risk_per_day_pct / 100.0)

holdings_df["risk_cap"] = max_loss_per_trade
holdings_df["position_risk"] = holdings_df["qty"] * (holdings_df["ltp"] * 0.01)

# ------------------ Dashboard ------------------ #
st.header("📊 Positions & Risk Dashboard")

st.dataframe(
    holdings_df[
        [
            "symbol",
            "qty",
            "avg_price",
            "ltp",
            "prev_close",
            "investment",
            "current_value",
            "pnl",
            "pnl_pct",
            "daily_return",
            "risk_cap",
            "position_risk",
            "sector",
        ]
    ]
)

# Summary
st.subheader("Portfolio Summary")
total_investment = holdings_df["investment"].sum()
total_value = holdings_df["current_value"].sum()
total_pnl = holdings_df["pnl"].sum()
total_pnl_pct = (total_pnl / total_investment) * 100

st.metric("💰 Total Investment", f"₹{total_investment:,.0f}")
st.metric("📈 Current Value", f"₹{total_value:,.0f}")
st.metric(
    "PnL (₹ / %)", f"₹{total_pnl:,.0f} ({total_pnl_pct:.2f}%)",
    delta=f"{total_pnl_pct:.2f}%"
)

# ------------------ Visuals ------------------ #
st.subheader("PnL Distribution")
fig, ax = plt.subplots()
ax.bar(holdings_df["symbol"], holdings_df["pnl"], color=["g" if x >= 0 else "r" for x in holdings_df["pnl"]])
ax.set_ylabel("PnL (₹)")
st.pyplot(fig)

st.subheader("Exposure by Sector")
sector_exp = holdings_df.groupby("sector")["current_value"].sum()
fig2, ax2 = plt.subplots()
ax2.pie(sector_exp, labels=sector_exp.index, autopct="%1.1f%%")
ax2.axis("equal")
st.pyplot(fig2)

# ------------------ Export ------------------ #
st.subheader("Export Data")
st.download_button(
    "📥 Download Holdings CSV",
    holdings_df.to_csv(index=False).encode("utf-8"),
    file_name="holdings.csv",
    mime="text/csv"
)
