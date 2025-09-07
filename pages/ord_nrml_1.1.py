import streamlit as st
import pandas as pd
import io
import zipfile
import requests
import os
import traceback
from typing import Optional, Dict, Any
from math import floor

st.set_page_config(layout="wide")
st.header("🛒 Place Order — Definedge (Refined)")

# ------------------- Configuration -------------------
MASTER_URL = "https://app.definedgesecurities.com/public/allmaster.zip"
MASTER_FILE = "data/master/allmaster.csv"
MASTER_DIR = os.path.dirname(MASTER_FILE)

# ------------------- Utilities -------------------
def _safe_str(x: Any) -> str:
    return "" if x is None else str(x)


def _read_master_from_disk() -> pd.DataFrame:
    """Read master from disk if present, otherwise return empty DF."""
    if os.path.exists(MASTER_FILE):
        try:
            return pd.read_csv(MASTER_FILE)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def download_and_extract_master(force: bool = False, timeout: int = 20) -> pd.DataFrame:
    """Download master zip and extract CSV. If `force` True, always re-download.

    This function intentionally writes a local copy to speed up future loads.
    """
    # If we already have file locally and not forcing, load it
    if not force and os.path.exists(MASTER_FILE):
        return _read_master_from_disk()

    try:
        r = requests.get(MASTER_URL, timeout=timeout)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            csv_name = [n for n in z.namelist() if n.lower().endswith('.csv')]
            if not csv_name:
                st.error("Master archive didn't contain any CSV files.")
                return pd.DataFrame()
            csv_name = csv_name[0]
            with z.open(csv_name) as f:
                # original master has no header — set column names to known layout
                df = pd.read_csv(f, header=None, dtype=str)

        df.columns = [
            "SEGMENT","TOKEN","SYMBOL","TRADINGSYM","INSTRUMENT","EXPIRY",
            "TICKSIZE","LOTSIZE","OPTIONTYPE","STRIKE","PRICEPREC","MULTIPLIER",
            "ISIN","PRICEMULT","COMPANY"
        ]
        os.makedirs(MASTER_DIR, exist_ok=True)
        df.to_csv(MASTER_FILE, index=False)
        return df
    except Exception as e:
        st.error(f"Failed to download master file: {e}")
        return pd.DataFrame()


def load_master(force: bool = False) -> pd.DataFrame:
    """Public loader that will use local file unless forced to refresh."""
    if force:
        return download_and_extract_master(force=True)
    df = _read_master_from_disk()
    if df.empty:
        return download_and_extract_master(force=True)
    return df


def safe_int(x, default=0):
    try:
        return int(float(x))
    except Exception:
        return default


def fetch_ltp(client, exchange: str, token: Optional[str], symbol: Optional[str] = None) -> float:
    """Attempt to fetch LTP from the `client`. Tries token first then symbol if available.

    Returns 0.0 on failure.
    """
    if not client:
        return 0.0
    tries = []
    try:
        # preferred: token-based query
        if token:
            q = client.get_quotes(exchange, str(token))
            tries.append(('token', q))
            if isinstance(q, dict):
                # common shapes: {'ltp':..} or {'data': {'ltp': ..}}
                if 'ltp' in q:
                    return float(q.get('ltp') or 0.0)
                if 'data' in q and isinstance(q['data'], dict) and 'ltp' in q['data']:
                    return float(q['data'].get('ltp') or 0.0)
        # fallback: symbol based query (some clients accept symbol instead of token)
        if symbol:
            q2 = client.get_quotes(exchange, _safe_str(symbol))
            tries.append(('symbol', q2))
            if isinstance(q2, dict):
                if 'ltp' in q2:
                    return float(q2.get('ltp') or 0.0)
                if 'data' in q2 and isinstance(q2['data'], dict) and 'ltp' in q2['data']:
                    return float(q2['data'].get('ltp') or 0.0)
    except Exception:
        # Never raise here — caller will show friendly UI
        return 0.0
    return 0.0


# ------------------- Page start -------------------
client = st.session_state.get('client')
if not client:
    st.error("⚠️ Not logged in. Please login first from Login page.")
    st.stop()

# Debug toggle
debug = st.checkbox("Show debug info", value=False)

# Master controls
col_m1, col_m2, col_m3 = st.columns([1, 1, 2])
with col_m1:
    if st.button("🔄 Refresh Master (force re-download)"):
        master_df = load_master(force=True)
        # refresh page so everything updates
        st.experimental_rerun()
with col_m2:
    manual_mode = st.checkbox("Manual symbol input (skip master)")
with col_m3:
    st.write("Tip: Use the master for quick symbol lookup. If symbol is new, use Manual mode or refresh master.")

# Load master (non-force)
master_df = load_master(force=False)

# Exchange
exchange = st.radio("Exchange", ["NSE", "BSE", "NFO", "MCX"], index=0, horizontal=True)

# Symbol selection UI
selected_symbol = ""
token: Optional[str] = None
lot_size = 1

if not manual_mode and not master_df.empty:
    # try to filter by segment column (some masters use different segment naming)
    try:
        df_exch = master_df[master_df['SEGMENT'] == exchange].copy()
        if df_exch.empty:
            # some masters use segment codes like 'NSE_EQ' - allow partial match
            df_exch = master_df[master_df['SEGMENT'].astype(str).str.contains(exchange, case=False, na=False)].copy()
    except Exception:
        df_exch = master_df.copy()

    search = st.text_input("Search symbol or company (type any substring)")

    if search:
        mask = (
            df_exch['TRADINGSYM'].astype(str).str.contains(search, case=False, na=False)
            | df_exch['COMPANY'].astype(str).str.contains(search, case=False, na=False)
            | df_exch['SYMBOL'].astype(str).str.contains(search, case=False, na=False)
        )
        choices = df_exch[mask]
    else:
        choices = df_exch

    if choices.empty:
        st.info("No symbols found in master for this filter. Switch to manual mode or refresh master.")
        selected_symbol = st.text_input("Trading Symbol (manual)").strip().upper()
        token = None
        lot_size = 1
    else:
        # show a compact selectbox with helpful label
        choices['__label__'] = choices.apply(lambda r: f"{r['TRADINGSYM']} — {(_safe_str(r.get('COMPANY'))[:40])}  (Lot: {r.get('LOTSIZE')})", axis=1)
        sel_label = st.selectbox("Trading Symbol", choices['__label__'].tolist(), index=0)
        # map back to row
        sel_row = choices[choices['__label__'] == sel_label].iloc[0]
        selected_symbol = _safe_str(sel_row['TRADINGSYM']).upper()
        token = sel_row.get('TOKEN')
        lot_size = safe_int(sel_row.get('LOTSIZE'), default=1) or 1
else:
    selected_symbol = st.text_input("Trading Symbol (manual)").strip().upper()
    lot_size = int(st.number_input("Lot size (if known)", min_value=1, step=1, value=1))
    token = None

# Fetch limits/cash
limits = {}
try:
    limits = client.api_get('/limits') or {}
except Exception:
    limits = {}

cash_available = float(limits.get('cash') or 0.0)

# LTP fetch area
ltp_col1, ltp_col2 = st.columns([2, 1])
with ltp_col1:
    current_ltp = 0.0
    # Try to use cached LTP per-symbol in session_state to avoid extra calls
    ltp_key = f"ltp_{token or selected_symbol}"
    if ltp_key not in st.session_state:
        st.session_state[ltp_key] = 0.0

    if st.button("🔁 Refresh LTP"):
        st.session_state[ltp_key] = fetch_ltp(client, exchange, token, selected_symbol)

    # initial fetch (only if not present)
    if st.session_state.get(ltp_key, 0.0) == 0.0:
        st.session_state[ltp_key] = fetch_ltp(client, exchange, token, selected_symbol)

    current_ltp = float(st.session_state.get(ltp_key, 0.0) or 0.0)
    st.metric("📈 LTP", f"{current_ltp:.2f}")
with ltp_col2:
    st.metric("💰 Cash", f"₹{cash_available:,.2f}")

# Order form
with st.form("place_order_form"):
    st.subheader("Order Details")
    order_side = st.radio("Buy / Sell", ["BUY", "SELL"], index=0, horizontal=True)
    price_type = st.radio("Price Type", ["LIMIT", "MARKET", "SL-LIMIT", "SL-MARKET"], index=0, horizontal=True)
    place_by = st.radio("Place by", ["Quantity", "Amount"], index=0, horizontal=True)

    col_qty, col_amt = st.columns(2)
    with col_qty:
        quantity = int(st.number_input("Quantity", min_value=1, step=1, value=lot_size))
    with col_amt:
        amount = float(st.number_input("Amount (₹)", min_value=0.0, step=0.01, value=0.0))

    # Trigger price (for SL orders)
    trigger_price = 0.0
    if price_type in ["SL-LIMIT", "SL-MARKET"]:
        if "trigger_price" not in st.session_state:
            st.session_state["trigger_price"] = 0.0
        trigger_price = st.number_input(
            "Trigger Price (for SL orders)",
            min_value=0.0,
            step=0.01,
            value=float(st.session_state["trigger_price"]),
            key="trigger_price_input"
        )
        st.session_state["trigger_price"] = trigger_price

    # Price for LIMIT/SL-LIMIT
    price_input = 0.0
    if price_type == "MARKET" or price_type == "SL-MARKET":
        st.info("Market order: live market price will be used at placement. Price input is ignored (except for SL triggers).")
    else:
        if "desired_price" not in st.session_state:
            # set sensible default to current ltp if available
            st.session_state["desired_price"] = float(max(current_ltp, 0.0) or 0.0)
        price_input = st.number_input(
            "Price (per unit)",
            min_value=0.0,
            step=0.01,
            value=float(st.session_state["desired_price"]),
            key="desired_price_input"
        )
        st.session_state["desired_price"] = float(price_input)

    product_type = st.selectbox("Product Type", ["NORMAL", "INTRADAY", "CNC"], index=2)
    validity = st.selectbox("Validity", ["DAY", "IOC", "EOS"], index=0)
    remarks = st.text_input("Remarks (optional)")
    amo_flag = st.checkbox("AMO order (after market order)", value=False)
    submit = st.form_submit_button("Preview Order")

# Compute effective price
effective_price = price_input if price_type not in ["MARKET", "SL-MARKET"] else (current_ltp or price_input)

# Place-by logic
if place_by == "Amount" and amount > 0 and effective_price > 0:
    computed_qty = int(floor(amount / effective_price))
else:
    computed_qty = int(quantity)

# Enforce lot size multiples
if computed_qty <= 0:
    # If user entered an amount too small, choose 1 lot by default
    computed_qty = max(1, lot_size)

if lot_size > 1:
    if computed_qty % lot_size != 0:
        adjusted_qty = max(lot_size, (computed_qty // lot_size) * lot_size)
        # If adjusted becomes 0, set to one lot
        if adjusted_qty <= 0:
            adjusted_qty = lot_size
        lot_notice = f"Quantity {computed_qty} adjusted to {adjusted_qty} to match lot size {lot_size}."
        computed_qty = adjusted_qty
    else:
        lot_notice = ""
else:
    lot_notice = ""

# Estimated cost
est_value = computed_qty * effective_price

st.markdown("---")
st.subheader("Order Estimate")
st.write(f"Order Side: **{order_side}**  |  Price Type: **{price_type}**")
st.write(f"Quantity: **{computed_qty}** (Lot size: {lot_size})")
if price_type not in ["MARKET", "SL-MARKET"]:
    colp1, colp2 = st.columns(2)
    with colp1:
        st.write(f"📝 Your Price: **₹{st.session_state.get('desired_price', 0):,.2f}**")
    with colp2:
        st.write(f"📈 Current LTP: **₹{current_ltp:,.2f}**")
if price_type in ["SL-LIMIT", "SL-MARKET"]:
    st.write(f"🎯 Trigger Price (your input): **₹{st.session_state.get('trigger_price', 0):,.2f}**")

if lot_notice:
    st.warning(lot_notice)

st.write(f"Estimated order value: **₹{est_value:,.2f}**")
if cash_available > 0 and est_value > cash_available and order_side == 'BUY':
    st.error("Estimated order value exceeds available cash — place may fail or require margin.")

# Preview -> Confirm flow
if submit:
    errors = []
    if not selected_symbol:
        errors.append("Please select or enter a trading symbol.")
    if price_type in ["SL-LIMIT", "SL-MARKET"] and float(st.session_state.get("trigger_price", 0)) <= 0:
        errors.append("Please provide a Trigger Price for SL orders.")
    if price_type not in ["MARKET", "SL-MARKET"] and float(st.session_state.get("desired_price", 0)) <= 0:
        errors.append("Please provide a valid price.")
    if computed_qty <= 0:
        errors.append("Computed quantity is zero. Check Amount or Price.")

    if errors:
        for e in errors:
            st.error(e)
    else:
        # Build payload (keep keys compatible with your earlier client)
        order_price = float(st.session_state.get('desired_price', effective_price))
        payload: Dict[str, Any] = {
            "exchange": _safe_str(exchange),
            "tradingsymbol": _safe_str(selected_symbol),
            "order_type": _safe_str(order_side),
            "price": round(float(order_price), 2) if price_type not in ["MARKET", "SL-MARKET"] else "",
            "price_type": _safe_str(price_type),
            "product_type": _safe_str(product_type),
            "quantity": int(computed_qty),
            "validity": _safe_str(validity),
            "amo": "YES" if amo_flag else "",
        }
        trig = float(st.session_state.get('trigger_price', 0) or 0)
        if trig and trig > 0:
            payload["trigger_price"] = round(float(trig), 2)
        if remarks:
            payload["remarks"] = _safe_str(remarks)

        # Store pending order for confirmation
        st.session_state['_pending_place_order'] = payload
        st.success("✅ Preview ready — confirm below to place order.")

# Confirmation UI
if '_pending_place_order' in st.session_state:
    st.markdown('---')
    st.subheader('Confirm Order')
    st.json(st.session_state['_pending_place_order'])
    c1, c2 = st.columns([1, 1])
    if c1.button('✅ Confirm & Place Order'):
        try:
            payload = st.session_state['_pending_place_order']
            if debug:
                st.write('🔧 Payload to send:')
                st.json(payload)
            resp = client.place_order(payload)
            if debug:
                st.write('🔎 Raw response:')
                st.write(resp)
            # Handle common success shapes
            if isinstance(resp, dict) and (resp.get('status') == 'SUCCESS' or resp.get('success') == True):
                order_id = resp.get('order_id') or resp.get('data', {}).get('order_id') if isinstance(resp.get('data'), dict) else resp.get('order_id')
                st.success(f"✅ Order placed successfully. Order ID: {order_id}")
                del st.session_state['_pending_place_order']
                # clear cached ltp for symbol so next view fetches fresh
                ltp_key = f"ltp_{token or selected_symbol}"
                if ltp_key in st.session_state:
                    del st.session_state[ltp_key]
                st.experimental_rerun()
            else:
                st.error(f"❌ Placement failed: {resp}")
        except Exception as e:
            st.error(f"🚨 Exception while placing order: {e}")
            if debug:
                st.text(traceback.format_exc())
    if c2.button('❌ Cancel'):
        del st.session_state['_pending_place_order']
        st.info('Order preview cancelled.')

# Footer hints & debug
st.markdown('---')
st.info('Tip: Use "Refresh Master" if your symbol is missing. Use Manual mode to quickly enter custom symbols. For MARKET orders the live market price (LTP) will be used.')

if debug:
    st.write('Session state keys (debug):')
    st.write({k: v for k, v in st.session_state.items() if k.startswith('_') or k.startswith('ltp_')})
