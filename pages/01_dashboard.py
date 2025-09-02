# pages/holdings.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

st.header("📂 Holdings — Definedge")

client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

# ---------------- Debug Option ----------------
show_debug = st.checkbox("🐞 Show Debug Data")

# ---------------- Helper to fetch LTP + Prev Close ----------------
def fetch_ltp(client, segment, token):
    try:
        resp = client.api_get(f"/quotes/{segment}/{token}")
        return float(resp.get("ltp", 0.0))
    except Exception as e:
        st.warning(f"LTP fetch failed for {token}: {e}")
        return 0.0

def fetch_prev_close(client, segment, token, symbol, max_days_lookback=10):
    closes = []
    today = datetime.now()
    try:
        for offset in range(1, max_days_lookback + 1):
            dt = today - timedelta(days=offset - 1)
            date_str = dt.strftime("%d%m%Y")
            from_time = f"{date_str}0000"
            to_time = f"{date_str}1530"
            url = f"/history/{segment}/{token}/day/{from_time}/{to_time}"
            resp = client.api_get(url)

            if isinstance(resp, str):
                lines = resp.strip().splitlines()
                for line in lines:
                    fields = line.split(",")
                    if len(fields) >= 5:
                        closes.append(float(fields[4]))

            if len(closes) >= 2:
                break
    except Exception as e:
        st.warning(f"Prev close fetch failed for {token}: {e}")

    closes = list(dict.fromkeys(closes))  # unique preserve order

    # Debug raw closes
    if show_debug:
        st.write(f"🔎 {symbol} ({token}) closes → {closes}")

    return closes[-2] if len(closes) >= 2 else 0.0

# ---------------- Load Holdings ----------------
try:
    holdings_resp = client.get_holdings()
    if not holdings_resp or "data" not in holdings_resp:
        st.warning("⚠️ No holdings found.")
        st.stop()

    df = pd.DataFrame(holdings_resp["data"])

    # Ensure required columns
    for col in ["symbol", "segment", "token", "quantity", "avg_price"]:
        if col not in df.columns:
            st.error(f"Missing column in holdings: {col}")
            st.stop()

    # Convert numeric
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    df["avg_price"] = pd.to_numeric(df["avg_price"], errors="coerce").fillna(0)

    # Fetch LTP & Prev Close
    df["ltp"] = df.apply(lambda r: fetch_ltp(client, r["segment"], r["token"]), axis=1)
    df["prev_close"] = df.apply(lambda r: fetch_prev_close(client, r["segment"], r["token"], r["symbol"]), axis=1)

    # Calculations
    df["invested"] = df["quantity"] * df["avg_price"]
    df["current"] = df["quantity"] * df["ltp"]
    df["unrealized_pnl"] = df["current"] - df["invested"]
    df["today_pnl"] = (df["ltp"] - df["prev_close"]) * df["quantity"]

    # ---------------- Show Table ----------------
    st.subheader("📊 Holdings Details")
    st.dataframe(df[[
        "symbol", "quantity", "avg_price", "ltp", "prev_close",
        "invested", "current", "unrealized_pnl", "today_pnl"
    ]], use_container_width=True)

    # ---------------- Summary ----------------
    total_invested = df["invested"].sum()
    total_current = df["current"].sum()
    overall_pnl = df["unrealized_pnl"].sum()
    today_pnl = df["today_pnl"].sum()

    st.subheader("💰 Overall Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Invested", f"₹{total_invested:,.2f}")
    col2.metric("Total Current", f"₹{total_current:,.2f}")
    col3.metric("Overall Unrealized PnL", f"₹{overall_pnl:,.2f}")
    col4.metric("Today PnL", f"₹{today_pnl:,.2f}")

except Exception as e:
    st.error(f"Error loading holdings: {e}")
