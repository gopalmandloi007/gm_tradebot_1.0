# holdings.py (Final Enhanced Version)
import streamlit as st
import pandas as pd
from typing import List, Dict

st.set_page_config(layout="wide")
st.title("📦 Holdings — Definedge (PnL Enhanced)")

# -----------------------
# Check login
# -----------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in")
    st.stop()

debug = st.checkbox("Show debug info (holdings)", value=False)

# -----------------------
# Helper: pick first non-null field
# -----------------------
def _pick_first(row: Dict, candidates: List[str], default=None):
    for c in candidates:
        if c in row and row[c] not in (None, ""):
            return row[c]
    return default

# -----------------------
# Main holdings fetch
# -----------------------
try:
    resp = client.get_holdings()
    if debug:
        st.write("🔎 Raw holdings response:", resp)

    if not isinstance(resp, dict) or resp.get("status") != "SUCCESS":
        st.error("⚠️ Holdings API returned non-success. Showing raw response:")
        st.write(resp)
        st.stop()

    raw_list = resp.get("data", [])
    if not raw_list:
        st.warning("⚠️ No holdings found")
        st.stop()

    df = pd.DataFrame(raw_list)

    # ---- Normalize important numeric fields ----
    for col in ["dp_qty", "t1_qty", "holding_used", "sell_amount",
                "average_price", "ltp", "previous_close"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        else:
            df[col] = 0.0

    # ---- Quantity calculations ----
    df["open_qty"] = (df["dp_qty"] + df["t1_qty"]).astype(int)   # actual holdings
    df["sold_qty"] = df["holding_used"].astype(int)              # sold
    df["total_qty"] = df["open_qty"] + df["sold_qty"]

    # ---- PnL calculations ----
    df["realized_pnl"] = df["sell_amount"] - (df["sold_qty"] * df["average_price"])
    df["unrealized_pnl"] = (df["ltp"] - df["average_price"]) * df["open_qty"]
    df["today_pnl"] = (df["ltp"] - df["previous_close"]) * df["open_qty"]

    df["pnl_total"] = df["realized_pnl"] + df["unrealized_pnl"]

    # ---- % change ----
    df["pct_change"] = ((df["ltp"] - df["previous_close"]) / df["previous_close"]) * 100
    df["pct_change"] = df["pct_change"].round(2)

    # ---- Arrange columns nicely ----
    show_cols = [
        "tradingsymbol", "total_qty", "open_qty", "sold_qty",
        "average_price", "ltp", "previous_close",
        "pct_change", "today_pnl", "realized_pnl",
        "unrealized_pnl", "pnl_total"
    ]
    df = df[[c for c in show_cols if c in df.columns]]

    # Store for other pages
    st.session_state["holdings_df"] = df

    st.success(f"✅ Holdings loaded: {len(df)} rows")
    st.dataframe(df, use_container_width=True)

    # ---- Portfolio summary ----
    st.subheader("📊 Portfolio Summary")
    summary = {
        "Invested": (df["average_price"] * df["open_qty"]).sum(),
        "Current Value": (df["ltp"] * df["open_qty"]).sum(),
        "Realized PnL": df["realized_pnl"].sum(),
        "Unrealized PnL": df["unrealized_pnl"].sum(),
        "Today PnL": df["today_pnl"].sum(),
        "Total PnL": df["pnl_total"].sum()
    }
    st.write(summary)

except Exception as e:
    st.error(f"Holdings fetch failed: {e}")
    import traceback
    st.text(traceback.format_exc())
