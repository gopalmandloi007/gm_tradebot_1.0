# holdings.py
import streamlit as st
import pandas as pd
from typing import List, Dict

st.set_page_config(layout="wide")
st.title("📦 Holdings — Definedge (Cleaned)")

client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in")
    st.stop()

debug = st.checkbox("Show debug info (holdings)", value=False)

def _flatten_holdings(raw_data: List[Dict]) -> List[Dict]:
    """Flatten the holdings response structure into a list of rows, focusing on NSE."""
    records = []
    for h in raw_data:
        base = {k: v for k, v in h.items() if k != "tradingsymbol"}
        for ts in h.get("tradingsymbol", []):
            # Only NSE to match your preference (you can remove filter if you want others)
            if ts.get("exchange") == "NSE":
                row = {**base, **ts}
                records.append(row)
    return records

def _pick_first(row: Dict, candidates: List[str], default=None):
    for c in candidates:
        if c in row and row[c] not in (None, ""):
            return row[c]
    return default

try:
    resp = client.get_holdings()
    if debug:
        st.write("🔎 Raw holdings response:", resp)

    if not isinstance(resp, dict) or resp.get("status") != "SUCCESS":
        st.error("⚠️ Holdings API returned non-success. Showing raw response:")
        st.write(resp)
        st.stop()

    raw_list = resp.get("data", [])
    records = _flatten_holdings(raw_list)

    if not records:
        st.warning("⚠️ No NSE holdings found")
        st.stop()

    # Build dataframe with robust columns
    df = pd.DataFrame(records)

    # Normalize quantity fields (many APIs use different names)
    df["quantity"] = df.apply(lambda r: int(float(_pick_first(r, ["quantity", "qty", "holding_qty", "holdings_quantity", "net_quantity"], 0))), axis=1)
    df["available_quantity"] = df.apply(lambda r: int(float(_pick_first(r, ["sellable_quantity", "available_quantity", "available_qty", "sellable"], r.get("quantity", 0)))), axis=1)
    # remaining qty we interpret as available qty; adjust logic if your API uses dif names
    df["remaining_qty"] = df["available_quantity"]

    # average / avg price
    df["average_price"] = df.apply(lambda r: float(_pick_first(r, ["average_price", "avg_price", "avg_buy_price", "buy_price"], 0.0)), axis=1)

    # canonical trading symbol column to match GTT pages
    df["tradingsymbol"] = df["tradingsymbol"].astype(str).str.upper()

    # small helpful columns
    df = df[sorted(df.columns)]

    # store for other pages
    st.session_state["holdings_df"] = df

    st.success(f"✅ NSE Holdings loaded: {len(df)} rows")
    st.dataframe(df, use_container_width=True)

except Exception as e:
    st.error(f"Holdings fetch failed: {e}")
    import traceback
    st.text(traceback.format_exc())
