# pages/place_order.py
"""
Improved, user-friendly Place Order page for Definedge.
Features:
- Master download / refresh + manual symbol fallback
- Searchable symbol select (by substring)
- LTP fetch and live display
- Place by Quantity or Amount (auto-calc)
- Enforces lot-size multiples (auto-adjust with notice)
- SL orders show Trigger Price only when needed
- Preview -> Confirm flow (prevents accidental orders)
- Helpful validations and estimated order value vs available cash
- Debug toggle to inspect payload/response
"""

import streamlit as st
import pandas as pd
import io
import zipfile
import requests
import os
import traceback
from typing import Optional

st.set_page_config(layout="wide")
st.header("🛒 Place Order — Definedge (Improved)")

# ---- configuration ----
MASTER_URL = "https://app.definedgesecurities.com/public/allmaster.zip"
MASTER_FILE = "data/master/allmaster.csv"

# ---- helpers ----
def download_and_extract_master() -> pd.DataFrame:
    try:
        r = requests.get(MASTER_URL, timeout=20)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            csv_name = [n for n in z.namelist() if n.lower().endswith('.csv')][0]
            with z.open(csv_name) as f:
                df = pd.read_csv(f, header=None)
        df.columns = [
            "SEGMENT","TOKEN","SYMBOL","TRADINGSYM","INSTRUMENT","EXPIRY",
            "TICKSIZE","LOTSIZE","OPTIONTYPE","STRIKE","PRICEPREC","MULTIPLIER",
            "ISIN","PRICEMULT","COMPANY"
        ]
        os.makedirs(os.path.dirname(MASTER_FILE), exist_ok=True)
        df.to_csv(MASTER_FILE, index=False)
        return df
    except Exception as e:
        st.error(f"Failed to download master file: {e}")
        return pd.DataFrame()

def load_master_symbols() -> pd.DataFrame:
    if os.path.exists(MASTER_FILE):
        try:
            return pd.read_csv(MASTER_FILE)
        except Exception:
            return download_and_extract_master()
    else:
        return download_and_extract_master()

def fetch_ltp(client, exchange: str, token: Optional[str]) -> float:
    if not client or token is None:
        return 0.0
    try:
        quotes = client.get_quotes(exchange, str(token))
        if isinstance(quotes, dict) and 'ltp' in quotes:
            return float(quotes.get('ltp') or 0.0)
        if isinstance(quotes, dict) and 'data' in quotes and isinstance(quotes['data'], dict):
            return float(quotes['data'].get('ltp') or 0.0)
    except Exception:
        return 0.0
    return 0.0

def _safe_str(x):
    return "" if x is None else str(x)

# ---- page start ----
client = st.session_state.get('client')
if not client:
    st.error("⚠️ Not logged in. Please login first from Login page.")
    st.stop()

debug = st.checkbox("Show debug info", value=False)

# Load master and provide refresh control
master_df = load_master_symbols()
col_refresh, col_manual = st.columns([1, 1])
with col_refresh:
    if st.button("🔄 Refresh Master (redownload)") and st.session_state.get("_refreshing") != True:
        st.session_state["_refreshing"] = True
        master_df = download_and_extract_master()
        st.session_state["_refreshing"] = False
        st.rerun()
with col_manual:
    manual_mode = st.checkbox("Manual symbol input (no master)")

# Exchange selector
exchange = st.radio("Exchange", ["NSE", "BSE", "NFO", "MCX"], index=0, horizontal=True)

# Symbol selector
if not manual_mode and not master_df.empty:
    try:
        df_exch = master_df[master_df['SEGMENT'] == exchange]
    except Exception:
        df_exch = master_df

    search = st.text_input("Search symbol (type part of name / tradingsym)")
    if search:
        mask = df_exch['TRADINGSYM'].astype(str).str.contains(search, case=False, na=False) | \
               df_exch['COMPANY'].astype(str).str.contains(search, case=False, na=False)
        choices = df_exch[mask]
    else:
        choices = df_exch

    if choices.empty:
        st.info("No symbols found in master for this filter. Switch to manual mode or refresh master.")
        selected_symbol = st.text_input("Trading Symbol (manual)").strip().upper()
        lot_size = 1
        token = None
    else:
        display = choices['TRADINGSYM'].astype(str).tolist()
        idx = st.selectbox("Trading Symbol", display, index=0)
        selected_symbol = str(idx)
        token_row = choices[choices['TRADINGSYM'] == selected_symbol].iloc[0]
        try:
            lot_size = int(token_row.get('LOTSIZE', 1)) if not pd.isna(token_row.get('LOTSIZE', 1)) else 1
        except Exception:
            lot_size = 1
        try:
            token = token_row.get('TOKEN')
        except Exception:
            token = None
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

# LTP fetch
current_ltp = fetch_ltp(client, exchange, token) if token else 0.0
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("**Symbol**")
    st.code(selected_symbol or "-")
with col2:
    st.metric("📈 LTP", f"{current_ltp:.2f}")
with col3:
    st.metric("💰 Cash", f"₹{cash_available:,.2f}")

# Order form
with st.form("place_order_form"):
    st.subheader("Order Details")
    order_type = st.radio("Buy / Sell", ["BUY", "SELL"], index=0, horizontal=True)
    price_type = st.radio("Price Type", ["LIMIT", "MARKET", "SL-LIMIT", "SL-MARKET"], index=0, horizontal=True)
    place_by = st.radio("Place by", ["Quantity", "Amount"], index=0, horizontal=True)

    col_qty, col_amt = st.columns(2)
    with col_qty:
        quantity = int(st.number_input("Quantity", min_value=1, step=1, value=1))
    with col_amt:
        amount = float(st.number_input("Amount (₹)", min_value=0.0, step=0.05, value=0.0))

    # Trigger price persistence
    trigger_price = 0.0
    if price_type in ["SL-LIMIT", "SL-MARKET"]:
        if "trigger_price" not in st.session_state:
            st.session_state["trigger_price"] = 0.0
        trigger_price = st.number_input(
            "Trigger Price (for SL orders)",
            min_value=0.0,
            step=0.05,
            value=st.session_state["trigger_price"],
            key="trigger_price"
        )

    # Price input persistence
    price_input = 0.0
    if price_type == "MARKET":
        st.info("Market order: live market price will be used at placement. Price input is ignored.")
    else:
        if "desired_price" not in st.session_state:
            st.session_state["desired_price"] = float(max(current_ltp, 0.0))
        price_input = st.number_input(
            "Price (per unit)",
            min_value=0.0,
            step=0.05,
            value=st.session_state["desired_price"],
            key="desired_price"
        )

    product_type = st.selectbox("Product Type", ["NORMAL", "INTRADAY", "CNC"], index=2)
    validity = st.selectbox("Validity", ["DAY", "IOC", "EOS"], index=0)
    remarks = st.text_input("Remarks (optional)")
    amo_flag = st.checkbox("AMO order (after market order)", value=False)
    submit = st.form_submit_button("Preview Order")

# Auto-calc quantity
effective_price = price_input if price_type != "MARKET" else (current_ltp or price_input)
if place_by == "Amount" and amount > 0 and effective_price > 0:
    computed_qty = int(amount // effective_price)
else:
    computed_qty = quantity

# Lot-size enforcement
if computed_qty > 0:
    if computed_qty % lot_size != 0:
        adjusted_qty = max(lot_size, (computed_qty // lot_size) * lot_size)
        lot_notice = f"Quantity {computed_qty} adjusted to {adjusted_qty} to match lot size {lot_size}."
        computed_qty = adjusted_qty
    else:
        lot_notice = ""
else:
    lot_notice = ""
    computed_qty = lot_size

# Estimated cost
est_value = computed_qty * effective_price
st.markdown("---")
st.subheader("Order Estimate")
st.write(f"Order Type: **{order_type}**  |  Price Type: **{price_type}**")
st.write(f"Quantity: **{computed_qty}** (Lot size: {lot_size})")

# Show persisted Price & Trigger Price explicitly + comparison with LTP
if price_type != "MARKET":
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
if cash_available > 0 and est_value > cash_available:
    st.error("Estimated order value exceeds available cash — place may fail or require margin.")

# Preview -> Confirm flow
if submit:
    if not selected_symbol:
        st.error("Please select or enter a trading symbol.")
    elif price_type in ["SL-LIMIT", "SL-MARKET"] and st.session_state.get("trigger_price", 0) <= 0:
        st.error("Please provide a Trigger Price for SL orders.")
    elif price_type != "MARKET" and st.session_state.get("desired_price", 0) <= 0:
        st.error("Please provide a valid price.")
    else:
        order_price = st.session_state.get("desired_price", effective_price)
        payload = {
            "exchange": _safe_str(exchange),
            "tradingsymbol": _safe_str(selected_symbol),
            "order_type": _safe_str(order_type),
            "price": _safe_str(round(float(order_price), 2)),
            "price_type": _safe_str(price_type),
            "product_type": _safe_str(product_type),
            "quantity": _safe_str(int(computed_qty)),
            "validity": _safe_str(validity),
            "amo": "YES" if amo_flag else "",
        }
        trig = st.session_state.get("trigger_price", 0)
        if trig and trig > 0:
            payload["trigger_price"] = _safe_str(round(float(trig), 2))
        if remarks:
            payload["remarks"] = _safe_str(remarks)

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
            if isinstance(resp, dict) and resp.get('status') == 'SUCCESS':
                st.success(f"✅ Order placed successfully. Order ID: {resp.get('order_id')}")
                del st.session_state['_pending_place_order']
                st.rerun()
            else:
                st.error(f"❌ Placement failed: {resp}")
        except Exception as e:
            st.error(f"🚨 Exception while placing order: {e}")
            st.text(traceback.format_exc())
    if c2.button('❌ Cancel'):
        del st.session_state['_pending_place_order']
        st.info('Order preview cancelled.')

# Footer hints
st.markdown('---')
st.info('Tip: Use "Refresh Master" if your symbol is missing. Use Manual mode to quickly enter custom symbols. For MARKET orders the live market price (LTP) will be used.')

if debug:
    st.write('Session state keys:')
    st.write({k: v for k, v in st.session_state.items() if k.startswith('_pending_')})
