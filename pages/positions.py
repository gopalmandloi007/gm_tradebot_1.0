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
        if qty > 0:
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
        else:
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

    # Display dataframe
    df_display = df[[
        "symbol", "exchange", "product", "qty", "avg_price", "ltp",
        "invested_value", "current_value", "unrealized_pnl", "unrealized_pct",
        "capital_alloc_pct", "initial_sl", "tsl", "profit_if_tsl", "loss_if_tsl_from_current",
        "target_10", "target_20", "target_30", "target_40"
    ]].copy()

    # Format
    money_cols = ["avg_price", "ltp", "invested_value", "current_value", "unrealized_pnl",
                  "initial_sl", "tsl", "profit_if_tsl", "loss_if_tsl_from_current",
                  "target_10", "target_20", "target_30", "target_40"]
    for c in money_cols:
        df_display[c] = pd.to_numeric(df_display[c], errors="coerce").round(2)
    df_display["unrealized_pct"] = df_display["unrealized_pct"].round(2)
    df_display["capital_alloc_pct"] = df_display["capital_alloc_pct"].round(2)

    # ---------- Summary KPIs ----------
    total_invested = df_display["invested_value"].sum()
    total_current = df_display["current_value"].sum()
    total_unrealized = df_display["unrealized_pnl"].sum()
    cash_left = DEFAULT_TOTAL_CAPITAL - total_invested
    total_profit_if_all_tsl = df_display["profit_if_tsl"].sum()

    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric("💰 Total Invested", f"₹{total_invested:,.2f}")
    kpi2.metric("📈 Current Value", f"₹{total_current:,.2f}")
    kpi3.metric("📊 Unrealized P&L", f"₹{total_unrealized:,.2f}")
    kpi4.metric("🛑 P&L if all TSL hit", f"₹{total_profit_if_all_tsl:,.2f}")
    kpi5.metric("💵 Cash in Hand", f"₹{cash_left:,.2f}")

    # ---------- Risk Bar Chart ----------
    st.subheader("📉 Open Risk vs TSL Risk")
    risk_df = pd.DataFrame({
        "Metric": ["Unrealized P&L (now)", "P&L if all TSL hit"],
        "Value": [total_unrealized, total_profit_if_all_tsl]
    })
    fig_bar = go.Figure(data=[go.Bar(
        x=risk_df["Metric"],
        y=risk_df["Value"],
        text=risk_df["Value"].apply(lambda v: f"₹{v:,.0f}"),
        textposition="auto"
    )])
    fig_bar.update_layout(yaxis_title="P&L (₹)")
    st.plotly_chart(fig_bar, use_container_width=True)

    # ---------- Table ----------
    st.subheader("📋 Positions Table (Detailed with Targets & SLs)")
    st.dataframe(df_display.sort_values("invested_value", ascending=False).reset_index(drop=True), use_container_width=True)

    # ---------- Downloads ----------
    csv_bytes = df_display.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download Positions CSV", csv_bytes, file_name="positions_with_risk.csv", mime="text/csv")
    st.download_button("⬇️ Download Positions JSON", df_display.to_json(orient="records"), file_name="positions.json", mime="application/json")

    # ---------- Manual Square-off ----------
    st.subheader("🛠️ Manual Square-off")
    with st.form("manual_squareoff"):
        sq_symbol = st.text_input("Enter Trading Symbol")
        sq_exchange = st.selectbox("Exchange", ["NSE", "BSE", "NFO"])
        sq_qty = st.text_input("Quantity to Square-off")
        submitted = st.form_submit_button("Square-off")

        if submitted:
            if not sq_symbol or not sq_qty:
                st.error("Provide symbol and quantity.")
            else:
                try:
                    payload = {
                        "exchange": sq_exchange,
                        "tradingsymbol": sq_symbol,
                        "quantity": int(sq_qty),
                        "product_type": "INTRADAY",
                    }
                    resp_square = client.square_off_position(payload)
                    st.write("🔎 Square-off API Response:", resp_square)
                    if resp_square and resp_square.get("status") == "SUCCESS":
                        st.success(f"Position {sq_symbol} squared-off successfully ✅")
                        st.rerun()
                    else:
                        st.error(f"Square-off failed: {resp_square}")
                except Exception as e:
                    st.error(f"Square-off failed: {e}")
                    st.text(traceback.format_exc())

except Exception as e:
    st.error(f"Fetching positions failed: {e}")
    st.text(traceback.format_exc())
