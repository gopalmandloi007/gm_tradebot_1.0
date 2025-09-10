# holdings.py (Enhanced + Detailed, Corrected)
import streamlit as st
import pandas as pd
from typing import List, Dict

st.set_page_config(layout="wide")
st.title("📦 Holdings — Definedge (Enhanced, Corrected)")

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
    """Flatten holdings into list of rows (robust for str/dict/list)."""
    records = []
    for h in raw_data:
        base = {k: v for k, v in h.items() if k != "tradingsymbol"}
        ts_field = h.get("tradingsymbol")

        if isinstance(ts_field, str):  # simple symbol
            records.append({**base, "tradingsymbol": ts_field})
        elif isinstance(ts_field, dict):  # dict with extra info
            records.append({**base, **ts_field})
        elif isinstance(ts_field, (list, tuple)):  # list of dicts or strings
            for ts in ts_field:
                if isinstance(ts, dict):
                    records.append({**base, **ts})
                else:
                    records.append({**base, "tradingsymbol": str(ts)})
        else:
            # fallback
            records.append({**base, "tradingsymbol": str(ts_field)})

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
        st.warning("⚠️ No holdings found")
        st.stop()

    # -----------------------
    # Build dataframe
    # -----------------------
    df = pd.DataFrame(records)

    # ---- Quantity fields ----
    df["quantity"] = df.apply(
        lambda r: int(float(_pick_first(
            r,
            ["quantity", "qty", "holding_qty", "holdings_quantity", "net_quantity",
             "dp_qty", "t1_qty", "holding_used"],
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

    # ---- Product type ----
    if "product_type" in df.columns:
        df["product_type"] = df["product_type"].fillna("UNKNOWN")
    elif "productType" in df.columns:
        df["product_type"] = df["productType"].fillna("UNKNOWN")
    else:
        df["product_type"] = "UNKNOWN"

    # ---- Trading symbol ----
    df["tradingsymbol"] = df["tradingsymbol"].astype(str).str.upper()

    # -----------------------
    # Aggregate duplicates
    # -----------------------
    if not df.empty:
        df = (
            df.groupby(["tradingsymbol", "product_type"], as_index=False)
            .apply(lambda g: pd.Series({
                "quantity": g["quantity"].sum(),
                "available_quantity": g["available_quantity"].sum(),
                "remaining_qty": g["remaining_qty"].sum(),
                # weighted avg price
                "average_price": (g["average_price"] * g["quantity"]).sum() / max(g["quantity"].sum(), 1)
            }))
            .reset_index(drop=True)
        )

    # -----------------------
    # Final tidy dataframe
    # -----------------------
    st.session_state["holdings_df"] = df

    st.success(f"✅ Holdings loaded: {len(df)} rows")
    st.dataframe(df, use_container_width=True)

except Exception as e:
    st.error(f"Holdings fetch failed: {e}")
    import traceback
    st.text(traceback.format_exc())
