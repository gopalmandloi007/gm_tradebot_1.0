# ==============================================================
# 📊 FINAL TRADING DASHBOARD (Definedge Portfolio + R-Multiple)
# Includes: Live Holdings, R-multiple, >5R Filter, Drawdown, Charts
# ==============================================================

import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta, date
import plotly.express as px
import traceback
import requests

# ------------------ Configuration ------------------
st.set_page_config(layout="wide")
st.title("📈 Trading Dashboard — Definedge (R-Multiple, Drawdown, Charts)")

# ------------------ Defaults ------------------
DEFAULT_TOTAL_CAPITAL = 1400000
DEFAULT_INITIAL_SL_PCT = 2.0
DEFAULT_TARGETS = [10, 20, 30, 40]

# ------------------ Helpers ------------------
def safe_float(x):
    try:
        return float(str(x).replace(",", "").strip())
    except:
        return None

def find_in_nested(obj, keys):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in [kk.lower() for kk in keys]:
                return v
            res = find_in_nested(v, keys)
            if res is not None:
                return res
    elif isinstance(obj, (list, tuple)):
        for it in obj:
            res = find_in_nested(it, keys)
            if res is not None:
                return res
    return None

def parse_definedge_csv_text(csv_text: str) -> pd.DataFrame:
    if not csv_text:
        return pd.DataFrame(columns=["DateTime", "Close"])
    df_raw = pd.read_csv(io.StringIO(csv_text), header=None, dtype=str)
    if df_raw.shape[1] < 6:
        return pd.DataFrame(columns=["DateTime", "Close"])
    df = df_raw.rename(columns={0: "DateTime", 4: "Close"})
    df["DateTime"] = pd.to_datetime(df["DateTime"], format="%d%m%Y", errors="coerce")
    df["Close"] = pd.to_numeric(df["Close"].str.replace(",", ""), errors="coerce")
    df = df.dropna().sort_values("DateTime")
    return df[["DateTime", "Close"]]

def fetch_hist_for_date_range(api_key, segment, token, start_date, end_date):
    from_str = start_date.strftime("%d%m%Y") + "0000"
    to_str = end_date.strftime("%d%m%Y") + "1530"
    url = f"https://data.definedgesecurities.com/sds/history/{segment}/{token}/day/{from_str}/{to_str}"
    headers = {"Authorization": api_key}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200 and resp.text.strip():
            return parse_definedge_csv_text(resp.text)
    except:
        return pd.DataFrame()
    return pd.DataFrame()

def get_prev_close(hist_df: pd.DataFrame):
    if hist_df.empty:
        return None
    if len(hist_df) < 2:
        return hist_df["Close"].iloc[-1]
    return hist_df["Close"].iloc[-2]

# ------------------ MAIN ------------------
client = st.session_state.get('client')
if not client:
    st.error("⚠️ Please login first on the Login page.")
    st.stop()

# Sidebar inputs
capital = st.sidebar.number_input("💰 Total Capital (₹)", value=DEFAULT_TOTAL_CAPITAL, step=10000)
initial_sl_pct = st.sidebar.number_input("Initial Stop Loss (%)", value=DEFAULT_INITIAL_SL_PCT, step=0.1) / 100
targets_input = st.sidebar.text_input("Targets % (comma separated)", ",".join(map(str, DEFAULT_TARGETS)))
target_pcts = [float(x.strip()) / 100 for x in targets_input.split(",") if x.strip()]

# Fetch Holdings
try:
    resp = client.get_holdings()
    if not resp or resp.get("status") != "SUCCESS":
        st.warning("No holdings found.")
        st.stop()
    holdings = resp.get("data", [])
except Exception as e:
    st.error(f"Error fetching holdings: {e}")
    st.text(traceback.format_exc())
    st.stop()

# Parse holdings
rows = []
for h in holdings:
    dp = safe_float(h.get("dp_qty")) or 0
    t1 = safe_float(h.get("t1_qty")) or 0
    avg = safe_float(h.get("avg_buy_price")) or 0
    trade_qty = safe_float(h.get("trade_qty")) or 0
    sell_amt = safe_float(h.get("sell_amt")) or 0
    sym = h.get("tradingsymbol")
    token = h.get("token")
    rows.append({
        "symbol": sym, "token": token,
        "buy_qty": dp + t1, "sold_qty": trade_qty,
        "avg_buy_price": avg, "sell_amt": sell_amt
    })

df = pd.DataFrame(rows)
df["quantity"] = df["buy_qty"] - df["sold_qty"]
df = df[df["quantity"] > 0]

# Fetch quotes
ltps, prevs = [], []
LTP_KEYS = ["ltp", "last_price", "lastTradedPrice", "lastPrice"]
PREV_KEYS = ["prev_close", "previous_close", "prevClose"]

for _, row in df.iterrows():
    ltp = prev = None
    try:
        q = client.get_quotes(exchange="NSE", token=row["token"])
        ltp = safe_float(find_in_nested(q, LTP_KEYS))
        prev = safe_float(find_in_nested(q, PREV_KEYS))
    except:
        pass
    ltps.append(ltp)
    prevs.append(prev)

df["ltp"] = ltps
df["prev_close"] = prevs

# Calculations
df["invested_value"] = df["avg_buy_price"] * df["quantity"]
df["current_value"] = df["ltp"] * df["quantity"]
df["unrealized_pnl"] = df["current_value"] - df["invested_value"]

# SL/Target logic
df["initial_sl_price"] = df["avg_buy_price"] * (1 - initial_sl_pct)
df["initial_risk"] = (df["avg_buy_price"] - df["initial_sl_price"]) * df["quantity"]

# --- NEW: R-Multiple and Drawdown ---
df["current_r"] = (df["ltp"] - df["avg_buy_price"]) / (df["avg_buy_price"] - df["initial_sl_price"])
df["current_r"] = df["current_r"].replace([float("inf"), -float("inf")], 0)
df["max_drawdown_if_sl"] = -df["initial_risk"]

# Portfolio metrics
total_invested = df["invested_value"].sum()
total_unrealized = df["unrealized_pnl"].sum()
total_risk = df["initial_risk"].sum()
avg_r = (df["current_r"] * df["invested_value"]).sum() / total_invested if total_invested > 0 else 0
total_r_sum = df["current_r"].sum()
max_drawdown = df["max_drawdown_if_sl"].sum()

# KPIs
st.subheader("💎 Portfolio Summary")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Invested Value", f"₹{total_invested:,.0f}")
c2.metric("Unrealized PnL", f"₹{total_unrealized:,.0f}")
c3.metric("Avg R (Weighted)", f"{avg_r:.2f}")
c4.metric("Total R (Sum)", f"{total_r_sum:.2f}")
c5.metric("Max Drawdown (if all SL hit)", f"₹{max_drawdown:,.0f}")

# --- Stocks > 5R ---
st.subheader("🚀 Stocks Above 5R")
df_highr = df[df["current_r"] >= 5].sort_values("current_r", ascending=False)
if not df_highr.empty:
    st.dataframe(df_highr[["symbol", "quantity", "avg_buy_price", "ltp", "current_r", "unrealized_pnl"]])
else:
    st.info("No stock above 5R currently.")

# --- Positions Table ---
st.subheader("📋 All Positions with R-Multiple")
st.dataframe(df[["symbol", "quantity", "avg_buy_price", "ltp", "unrealized_pnl",
                 "initial_sl_price", "initial_risk", "current_r", "max_drawdown_if_sl"]])

# --- Capital Allocation Pie ---
st.subheader("🧩 Capital Allocation")
fig_pie = px.pie(df, names="symbol", values="invested_value", title="Capital Allocation by Invested Value")
st.plotly_chart(fig_pie, use_container_width=True)

# --- Risk Bar ---
st.subheader("📊 Risk per Stock (Initial vs PnL)")
risk_df = df.sort_values("initial_risk", ascending=False)
fig_bar = px.bar(risk_df, x="symbol", y=["initial_risk", "unrealized_pnl"], barmode="group")
st.plotly_chart(fig_bar, use_container_width=True)

# --- SL & Targets Table ---
st.subheader("🎯 SL & Targets")
for i, t in enumerate(target_pcts, start=1):
    df[f"target_{i}_price"] = df["avg_buy_price"] * (1 + t)
sl_table = df[["symbol", "initial_sl_price"] + [f"target_{i}_price" for i in range(1, len(target_pcts)+1)]]
st.dataframe(sl_table)

# --- Export ---
st.download_button("⬇️ Download CSV", df.to_csv(index=False).encode("utf-8"), "portfolio_r_dashboard.csv", "text/csv")

