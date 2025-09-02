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
    # not found -> return series of fill
    return pd.Series([fill] * len(df), index=df.index)

def compute_tsl(avg, ltp, qty):
    """Compute trailing stop loss by your rule (long & short symmetric).
    Long:
      - LTP <= +10%  -> initial SL (avg * 0.98)
      - 10% < LTP <=20% -> TSL = avg
      - 20% < LTP <=30% -> TSL = avg * 1.10
      - 30% < LTP <=40% -> TSL = avg * 1.20
      - >40% -> TSL = avg * 1.30
    Short: mirror symmetric
    """
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
            # default initial SL (2% below avg)
            return avg * 0.98
        else:
            # short: profit when price falls. compute drop percent
            drop_pct = (avg - ltp) / avg * 100.0
            if drop_pct > 40:
                return avg * 0.70  # avg - 30%
            if drop_pct > 30:
                return avg * 0.80
            if drop_pct > 20:
                return avg * 0.90
            if drop_pct > 10:
                return avg * 1.00
            # initial SL for short is 2% above avg
            return avg * 1.02
    except Exception:
        return np.nan

# ---------- Fetch positions ----------
try:
    resp = client.get_positions()
    if SHOW_DEBUG:
        st.subheader("🔎 Raw Positions Response")
        st.write(resp)

    # Response shape: sometimes {"status":"SUCCESS","positions":[...]} or {"status":"SUCCESS","data":[...]}
    positions = None
    if isinstance(resp, dict):
        positions = resp.get("positions") or resp.get("data") or resp.get("result") or resp.get("positions_list")
    else:
        positions = None

    if not positions:
        st.warning("⚠️ Positions API returned no positions.")
        st.stop()

    df = pd.DataFrame(positions)
    if df.empty:
        st.warning("⚠️ No positions found.")
        st.stop()

    # Normalize column names to lowercase for easier selection
    df.columns = df.columns.astype(str)
    df.columns = [c.lower() for c in df.columns]

    # Extract canonical fields (robust to field name differences)
    df["symbol"] = choose_series(df, ["tradingsymbol", "symbol", "trading_symbol"])
    df["token"] = choose_series(df, ["token"])
    df["exchange"] = choose_series(df, ["exchange"])
    df["product"] = choose_series(df, ["product_type", "product"])
    # Qty candidates
    qty_series = choose_series(df, ["net_quantity", "netqty", "net_quantity", "net_quantity"])
    df["qty"] = pd.to_numeric(qty_series, errors="coerce").fillna(0).astype(int)
    # Avg price candidates
    avg_series = choose_series(df, ["net_averageprice", "net_average_price", "net_average", "net_averageprice", "day_averageprice", "original_average_price"])
    df["avg_price"] = pd.to_numeric(avg_series, errors="coerce")
    # Last price from API if present
    lastprice_series = choose_series(df, ["lastprice","ltp","last_price","markprice"])
    df["ltp"] = pd.to_numeric(lastprice_series, errors="coerce")

    # If ltp missing & user asked for live quotes, fetch them per token
    if USE_LIVE_QUOTES:
        st.info("Fetching live quotes for each position (may be rate-limited)...")
        for i, row in df.iterrows():
            try:
                tok = row.get("token")
                exch = row.get("exchange") or "NSE"
                if pd.isna(tok) or str(tok) == "nan":
                    continue
                q = client.get_quotes(exchange=exch, token=str(tok))
                # quote may be a dict with ltp/day_open/day_high/day_low/volume
                if isinstance(q, dict):
                    ltp_val = q.get("ltp") or q.get("lastprice") or q.get("last_price") or q.get("lastPrice")
                    if ltp_val is not None:
                        df.at[i, "ltp"] = safe_num(ltp_val, default=df.at[i, "ltp"])
            except Exception as e:
                # don't fail all positions for one quote
                if SHOW_DEBUG:
                    st.write(f"Quote fetch failed for index {i}: {e}")

    # Fallback: if avg_price missing try to compute from open_buy_averageprice, net_uploadprice, etc.
    fallback_avg = choose_series(df, ["net_uploadprice", "upload_price", "open_buy_averageprice", "day_averageprice"])
    df["avg_price"] = df["avg_price"].fillna(pd.to_numeric(fallback_avg, errors="coerce"))

    # If avg still missing, try using ltp (not ideal, but avoids NaN)
    df["avg_price"] = df["avg_price"].fillna(df["ltp"])

    # Numeric coerce for ltp
    df["ltp"] = pd.to_numeric(df["ltp"], errors="coerce").fillna(0.0)

    # Derived columns
    df["invested_value"] = df["avg_price"] * df["qty"].abs()
    df["current_value"] = df["ltp"] * df["qty"].abs()
    df["unrealized_pnl"] = (df["ltp"] - df["avg_price"]) * df["qty"]  # sign included
    df["unrealized_pct"] = np.where(df["avg_price"] > 0, (df["ltp"] / df["avg_price"] - 1.0) * 100.0, 0.0)
    df["capital_alloc_pct"] = (df["invested_value"] / float(DEFAULT_TOTAL_CAPITAL)) * 100.0

    # Initial Stop Loss (2% below avg for long, 2% above avg for short)
    df["initial_sl"] = np.where(df["qty"] >= 0, df["avg_price"] * 0.98, df["avg_price"] * 1.02)

    # Targets at 10/20/30/40% from avg (long) or -10/-20... (short)
    df["target_10"] = np.where(df["qty"] >= 0, df["avg_price"] * 1.10, df["avg_price"] * 0.90)
    df["target_20"] = np.where(df["qty"] >= 0, df["avg_price"] * 1.20, df["avg_price"] * 0.80)
    df["target_30"] = np.where(df["qty"] >= 0, df["avg_price"] * 1.30, df["avg_price"] * 0.70)
    df["target_40"] = np.where(df["qty"] >= 0, df["avg_price"] * 1.40, df["avg_price"] * 0.60)

    # Trailing SL computed by your step rule
    df["tsl"] = df.apply(lambda r: compute_tsl(r["avg_price"], r["ltp"], r["qty"]), axis=1)

    # Profit if TSL hit (positive = still profit after tsl; zero = breakeven; negative = loss)
    df["profit_if_tsl"] = (df["tsl"] - df["avg_price"]) * df["qty"]

    # Loss to be given back if TSL hits relative to current price (i.e., current - tsl) * qty
    df["loss_if_tsl_from_current"] = (df["ltp"] - df["tsl"]) * df["qty"]

    # Clean / formatting columns for display
    df_display = df[[
        "symbol", "exchange", "product", "token", "qty", "avg_price", "ltp",
        "invested_value", "current_value", "unrealized_pnl", "unrealized_pct",
        "capital_alloc_pct", "initial_sl", "tsl", "profit_if_tsl", "loss_if_tsl_from_current",
        "target_10", "target_20", "target_30", "target_40"
    ]].copy()

    # numeric rounding for nicer display
    money_cols = ["avg_price", "ltp", "invested_value", "current_value", "unrealized_pnl",
                  "initial_sl", "tsl", "profit_if_tsl", "loss_if_tsl_from_current",
                  "target_10", "target_20", "target_30", "target_40"]
    for c in money_cols:
        if c in df_display.columns:
            df_display[c] = pd.to_numeric(df_display[c], errors="coerce").round(2)

    df_display["unrealized_pct"] = df_display["unrealized_pct"].round(2)
    df_display["capital_alloc_pct"] = df_display["capital_alloc_pct"].round(3)

    # ---------- Summary KPIs ----------
    total_positions = len(df_display)
    total_invested = df_display["invested_value"].sum()
    total_current = df_display["current_value"].sum()
    total_unrealized = df_display["unrealized_pnl"].sum()
    total_profit_if_all_tsl = df_display["profit_if_tsl"].sum()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Positions", total_positions)
    col2.metric("Total Invested (₹)", f"₹{total_invested:,.2f}")
    col3.metric("Current Value (₹)", f"₹{total_current:,.2f}")
    col4.metric("Unrealized P&L (₹)", f"₹{total_unrealized:,.2f}")

    st.markdown(f"**If all TSLs hit → P&L (sum):** ₹{total_profit_if_all_tsl:,.2f}")

    # Counts: how many positions would be profitable/breakeven/loss after TSL hit
    profitable_if_tsl = (df_display["profit_if_tsl"] > 0).sum()
    breakeven_if_tsl = (df_display["profit_if_tsl"] == 0).sum()
    loss_if_tsl = (df_display["profit_if_tsl"] < 0).sum()
    st.write(f"Positions if TSL hit → Profitable: **{profitable_if_tsl}**, Breakeven: **{breakeven_if_tsl}**, Loss: **{loss_if_tsl}**")

    # Additional summary text (user-friendly)
    if profitable_if_tsl == total_positions:
        st.success("All positions would still be profitable if their trailing-stop levels were hit.")
    elif breakeven_if_tsl + profitable_if_tsl == total_positions:
        st.info("All positions would be at least breakeven (some profitable) if TSLs hit.")
    else:
        st.warning(f"{loss_if_tsl} position(s) would incur a loss if their TSL were hit. Review those symbols.")

    # ---------- Capital allocation pie chart ----------
    st.subheader("📊 Capital Allocation")
    pie_df = df_display[["symbol", "invested_value"]].copy()
    pie_df = pie_df.groupby("symbol", as_index=False).sum().sort_values("invested_value", ascending=False)
    invested_sum = pie_df["invested_value"].sum()
    cash_left = max(0.0, float(DEFAULT_TOTAL_CAPITAL) - float(invested_sum))
    if cash_left > 0:
        pie_df = pd.concat([pie_df, pd.DataFrame([{"symbol": "Cash", "invested_value": cash_left}])], ignore_index=True)

    fig_pie = go.Figure(data=[go.Pie(labels=pie_df["symbol"], values=pie_df["invested_value"], hole=0.35)])
    fig_pie.update_traces(textinfo="label+percent")
    st.plotly_chart(fig_pie, use_container_width=True)

    # ---------- Show table ----------
    st.subheader("📋 Positions Table (detailed)")
    st.dataframe(df_display.sort_values("invested_value", ascending=False).reset_index(drop=True), use_container_width=True)

    # Downloads
    csv_bytes = df_display.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download Positions CSV", csv_bytes, file_name="positions_with_risk.csv", mime="text/csv")
    st.download_button("⬇️ Download Positions JSON", df_display.to_json(orient="records"), file_name="positions.json", mime="application/json")

    # ---------- Manual Square-off (unchanged) ----------
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
