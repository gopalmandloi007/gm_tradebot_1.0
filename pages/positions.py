# pages/positions.py
import streamlit as st
import pandas as pd
import numpy as np
import traceback
from datetime import datetime
import plotly.graph_objects as go

st.set_page_config(layout="wide")
st.header("📈 Positions — Definedge (Risk + TSL analysis)")

# ---------- Config ----------
DEFAULT_TOTAL_CAPITAL = st.sidebar.number_input("Total Capital (₹)", min_value=10000, value=1400000, step=10000)
USE_LIVE_QUOTES = st.sidebar.checkbox("Use live LTP (quotes API) — may be slower", value=False)
SHOW_DEBUG = st.sidebar.checkbox("Show debug info (raw API response)", value=False)

# ---------- Client check ----------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

# ---------- Helpers ----------
def safe_num(x, default=np.nan):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default

def choose_series(df, keys, fill=np.nan):
    """Return first existing column Series for keys (case-insensitive)."""
    cols = {c.lower(): c for c in df.columns}
    for k in keys:
        if k.lower() in cols:
            return df[cols[k.lower()]]
    return pd.Series([fill] * len(df), index=df.index)

def compute_tsl(avg, ltp, qty):
    """Compute trailing stop loss by your rule (long & short symmetric)."""
    try:
        if pd.isna(avg) or pd.isna(ltp) or qty == 0:
            return np.nan
        if qty > 0:  # Long
            gain_pct = (ltp / avg - 1.0) * 100.0
            if gain_pct > 40:
                return avg * 1.30
            if gain_pct > 30:
                return avg * 1.20
            if gain_pct > 20:
                return avg * 1.10
            if gain_pct > 10:
                return avg * 1.00
            return avg * 0.98
        else:  # Short
            drop_pct = (avg - ltp) / avg * 100.0
            if drop_pct > 40:
                return avg * 0.70
            if drop_pct > 30:
                return avg * 0.80
            if drop_pct > 20:
                return avg * 0.90
            if drop_pct > 10:
                return avg * 1.00
            return avg * 1.02
    except Exception:
        return np.nan

# ---------- Fetch positions ----------
try:
    resp = client.get_positions()
    if SHOW_DEBUG:
        st.subheader("🔎 Raw Positions Response")
        st.write(resp)

    positions = None
    if isinstance(resp, dict):
        positions = resp.get("positions") or resp.get("data") or resp.get("result") or resp.get("positions_list")
    if not positions:
        st.warning("⚠️ Positions API returned no positions.")
        st.stop()

    df = pd.DataFrame(positions)
    if df.empty:
        st.warning("⚠️ No positions found.")
        st.stop()

    # Normalize column names
    df.columns = df.columns.astype(str)
    df.columns = [c.lower() for c in df.columns]

    # Canonical fields
    df["symbol"] = choose_series(df, ["tradingsymbol", "symbol", "trading_symbol"])
    df["token"] = choose_series(df, ["token"])
    df["exchange"] = choose_series(df, ["exchange"])
    df["product"] = choose_series(df, ["product_type", "product"])
    qty_series = choose_series(df, ["net_quantity", "netqty"])
    df["qty"] = pd.to_numeric(qty_series, errors="coerce").fillna(0).astype(int)
    avg_series = choose_series(df, ["net_averageprice", "net_average_price", "day_averageprice"])
    df["avg_price"] = pd.to_numeric(avg_series, errors="coerce")
    lastprice_series = choose_series(df, ["lastprice", "ltp", "last_price"])
    df["ltp"] = pd.to_numeric(lastprice_series, errors="coerce")

    # Live quotes fallback
    if USE_LIVE_QUOTES:
        st.info("Fetching live quotes (may be rate-limited)...")
        for i, row in df.iterrows():
            try:
                tok = row.get("token")
                exch = row.get("exchange") or "NSE"
                if pd.isna(tok):
                    continue
                q = client.get_quotes(exchange=exch, token=str(tok))
                if isinstance(q, dict):
                    ltp_val = q.get("ltp") or q.get("lastprice") or q.get("lastPrice")
                    if ltp_val is not None:
                        df.at[i, "ltp"] = safe_num(ltp_val, default=df.at[i, "ltp"])
            except:
                if SHOW_DEBUG:
                    st.write(f"Quote fetch failed for {row['symbol']}")

    # Fallback avg
    fallback_avg = choose_series(df, ["upload_price", "open_buy_averageprice"])
    df["avg_price"] = df["avg_price"].fillna(pd.to_numeric(fallback_avg, errors="coerce"))
    df["avg_price"] = df["avg_price"].fillna(df["ltp"])

    # Derived
    df["invested_value"] = df["avg_price"] * df["qty"].abs()
    df["current_value"] = df["ltp"] * df["qty"].abs()
    df["unrealized_pnl"] = (df["ltp"] - df["avg_price"]) * df["qty"]
    df["unrealized_pct"] = np.where(df["avg_price"] > 0, (df["ltp"] / df["avg_price"] - 1) * 100, 0)
    df["capital_alloc_pct"] = (df["invested_value"] / float(DEFAULT_TOTAL_CAPITAL)) * 100
    df["initial_sl"] = np.where(df["qty"] >= 0, df["avg_price"] * 0.98, df["avg_price"] * 1.02)
    df["target_10"] = np.where(df["qty"] >= 0, df["avg_price"] * 1.10, df["avg_price"] * 0.90)
    df["target_20"] = np.where(df["qty"] >= 0, df["avg_price"] * 1.20, df["avg_price"] * 0.80)
    df["target_30"] = np.where(df["qty"] >= 0, df["avg_price"] * 1.30, df["avg_price"] * 0.70)
    df["target_40"] = np.where(df["qty"] >= 0, df["avg_price"] * 1.40, df["avg_price"] * 0.60)
    df["tsl"] = df.apply(lambda r: compute_tsl(r["avg_price"], r["ltp"], r["qty"]), axis=1)
    df["profit_if_tsl"] = (df["tsl"] - df["avg_price"]) * df["qty"]
    df["loss_if_tsl_from_current"] = (df["ltp"] - df["tsl"]) * df["qty"]

    # Side classification
    df["side"] = np.where(df["qty"] > 0, "Long", "Short")

    # ---------- Summary Function ----------
    def portfolio_summary_section(df_side, title, cash_in_hand):
        if df_side.empty:
            st.subheader(title)
            st.info("No positions in this side.")
            return

        invested = df_side['invested_value'].sum()
        current = df_side['current_value'].sum()
        unrealized_pnl = df_side['unrealized_pnl'].sum()
        tsl_hit_pnl = df_side['profit_if_tsl'].sum()

        st.subheader(title)
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("💰 Total Invested", f"₹{invested:,.2f}")
        with col2:
            st.metric("📈 Current Value", f"₹{current:,.2f}")
        with col3:
            st.metric("📊 Unrealized P&L", f"₹{unrealized_pnl:,.2f}")
        with col4:
            st.metric("🛑 P&L if all TSL hit", f"₹{tsl_hit_pnl:,.2f}")
        with col5:
            st.metric("💵 Cash in Hand", f"₹{cash_in_hand:,.2f}")

        # Risk chart
        st.subheader("📉 Open Risk vs TSL Risk")
        risk_data = pd.DataFrame({
            "Risk Type": ["Unrealized P&L (now)", "P&L if all TSL hit"],
            "Value": [unrealized_pnl, tsl_hit_pnl]
        })
        st.bar_chart(risk_data.set_index("Risk Type"))

        # Detailed table
        st.subheader("📋 Detailed Positions")
        st.dataframe(df_side[[
            "symbol","qty","avg_price","ltp",
            "invested_value","current_value","unrealized_pnl","unrealized_pct",
            "initial_sl","tsl","profit_if_tsl","loss_if_tsl_from_current",
            "target_10","target_20","target_30","target_40"
        ]].sort_values("invested_value", ascending=False).reset_index(drop=True),
        use_container_width=True)

    # ---------- Cash in hand ----------
    cash_in_hand_total = DEFAULT_TOTAL_CAPITAL - df["invested_value"].sum()

    # 📈 Long Section
    df_long = df[df["side"] == "Long"]
    portfolio_summary_section(df_long, "📈 Long Positions — Definedge (Risk + TSL analysis)", cash_in_hand_total)

    # 📉 Short Section
    df_short = df[df["side"] == "Short"]
    portfolio_summary_section(df_short, "📉 Short Positions — Definedge (Risk + TSL analysis)", cash_in_hand_total)

    # 🏁 Net Portfolio Summary
    st.subheader("🏁 Net Portfolio Summary")
    total_invested = df["invested_value"].sum()
    total_current = df["current_value"].sum()
    total_unrealized = df["unrealized_pnl"].sum()
    total_tsl_hit = df["profit_if_tsl"].sum()
    cash_left = DEFAULT_TOTAL_CAPITAL - total_invested

    colA, colB, colC, colD, colE = st.columns(5)
    colA.metric("💰 Total Invested", f"₹{total_invested:,.2f}")
    colB.metric("📈 Current Value", f"₹{total_current:,.2f}")
    colC.metric("📊 Unrealized P&L", f"₹{total_unrealized:,.2f}")
    colD.metric("🛑 P&L if all TSL hit", f"₹{total_tsl_hit:,.2f}")
    colE.metric("💵 Cash in Hand", f"₹{cash_left:,.2f}")

except Exception as e:
    st.error(f"Fetching positions failed: {e}")
    st.text(traceback.format_exc())
