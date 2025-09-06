# holdings.py (Enhanced + Detailed)
import streamlit as st
import pandas as pd
from typing import List, Dict

st.set_page_config(layout="wide")
st.title("📦 Holdings — Definedge (Enhanced, Detailed)")

# -----------------------
# Check login
# -----------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in")
    st.stop()

debug = st.checkbox("Show debug info (holdings)", value=False)

# -----------------------
# Helper functions
# -----------------------
def _flatten_holdings(raw_data: List[Dict]) -> List[Dict]:
    """Flatten the holdings response structure into a list of rows, focusing on NSE."""
    records = []
    for h in raw_data:
        base = {k: v for k, v in h.items() if k != "tradingsymbol"}
        for ts in h.get("tradingsymbol", []):
            # Only NSE holdings (can remove filter if you want all exchanges)
            if ts.get("exchange") == "NSE":
                row = {**base, **ts}
                records.append(row)
    return records

def _pick_first(row: Dict, candidates: List[str], default=None):
    """Pick first non-null column from a list of candidates."""
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
    records = _flatten_holdings(raw_list)

    if not records:
        st.warning("⚠️ No NSE holdings found")
        st.stop()

    # -----------------------
    # Build dataframe
    # -----------------------
    df = pd.DataFrame(records)

    # ---- Quantity fields ----
    df["quantity"] = df.apply(
        lambda r: int(float(_pick_first(
            r,
            ["quantity", "qty", "holding_qty", "holdings_quantity", "net_quantity"],
            0
        ))),
        axis=1
    )

    df["available_quantity"] = df.apply(
        lambda r: int(float(_pick_first(
            r,
            ["sellable_quantity", "available_quantity", "available_qty", "sellable"],
            r.get("quantity", 0)
        ))),
        axis=1
    )

    # Remaining qty = available qty
    df["remaining_qty"] = df["available_quantity"]

    # ---- Average price ----
    df["average_price"] = df.apply(
        lambda r: float(_pick_first(
            r,
            ["average_price", "avg_price", "avg_buy_price", "buy_price"],
            0.0
        )),
        axis=1
    )

    # ---- Product type (robust handling) ----
    if "product_type" in df.columns:
        df["product_type"] = df["product_type"].fillna("UNKNOWN")
    elif "productType" in df.columns:
        df["product_type"] = df["productType"].fillna("UNKNOWN")
    else:
        df["product_type"] = "UNKNOWN"

    # ---- Trading symbol (canonical) ----
    if "tradingsymbol" in df.columns:
        df["tradingsymbol"] = df["tradingsymbol"].astype(str).str.upper()
    else:
        df["tradingsymbol"] = "UNKNOWN"

    # -----------------------
    # Final tidy dataframe
    # -----------------------
    df = df[sorted(df.columns)]

    # Store for other pages
    st.session_state["holdings_df"] = df

    st.success(f"✅ NSE Holdings loaded: {len(df)} rows")
    st.dataframe(df, use_container_width=True)

except Exception as e:
    st.error(f"Holdings fetch failed: {e}")
    import traceback
    st.text(traceback.format_exc())
