import streamlit as st
import pandas as pd
import traceback

# --- Helper functions ---

def fetch_holdings(client):
    """Fetch holdings and return DataFrame."""
    resp = client.get_holdings()
    if resp.get("status") != "SUCCESS":
        return pd.DataFrame()
    raw_data = resp.get("data", [])
    records = []
    for h in raw_data:
        base = {k: v for k, v in h.items() if k != "tradingsymbol"}
        for ts in h.get("tradingsymbol", []):
            if ts.get("exchange") == "NSE":
                records.append({**base, **ts})
    return pd.DataFrame(records)

def fetch_positions(client):
    """Fetch positions and return DataFrame."""
    resp = client.get_positions()
    if resp.get("status") != "SUCCESS":
        return pd.DataFrame()
    data = resp.get("data", [])
    records = []
    for pos in data:
        base = {k: v for k, v in pos.items() if k != "tradingsymbol"}
        for ts in pos.get("tradingsymbol", []):
            if ts.get("exchange") == "NSE":
                records.append({**base, **ts})
    return pd.DataFrame(records)

def fetch_gtt_oco_orders(client):
    """Fetch existing GTT/OCO orders."""
    resp = client.gtt_orders()
    if not isinstance(resp, dict) or resp.get("status") != "SUCCESS":
        return pd.DataFrame()
    rows = resp.get("pendingGTTOrderBook") or []
    return pd.DataFrame(rows)

def place_gtt_order(client, tradingsymbol):
    """Open the GTT order placement form with pre-filled symbol."""
    st.session_state['place_gtt'] = {'tradingsymbol': tradingsymbol}

def place_oco_order(client, tradingsymbol):
    """Open the OCO order placement form with pre-filled symbol."""
    st.session_state['place_oco'] = {'tradingsymbol': tradingsymbol}

# --- Main Streamlit app ---

st.title("📊 Manage GTT & OCO Orders")

client = st.session_state.get("client")
if not client:
    st.error("⚠️ Please log in first.")
    st.stop()

# Fetch data
holdings_df = fetch_holdings(client)
positions_df = fetch_positions(client)
gtt_oco_df = fetch_gtt_oco_orders(client)

# Get list of all stocks in holdings and positions
holdings_symbols = set(holdings_df['tradingsymbol'])
positions_symbols = set(positions_df['tradingsymbol'])
all_symbols = holdings_symbols | positions_symbols

# Stocks with existing GTT/OCO orders
existing_order_symbols = set(gtt_oco_df['tradingsymbol'])

# Eligible stocks for new GTT/OCO
eligible_symbols = [sym for sym in all_symbols if sym not in existing_order_symbols]

st.subheader("Stocks eligible for new GTT/OCO orders")
if not eligible_symbols:
    st.info("No stocks available for new GTT/OCO orders.")
else:
    for sym in eligible_symbols:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.write(f"**{sym}**")
        with col2:
            gtt_btn = st.button(f"Place GTT", key=f"gtt_{sym}")
            oco_btn = st.button(f"Place OCO", key=f"oco_{sym}")
            if gtt_btn:
                place_gtt_order(client, sym)
            if oco_btn:
                place_oco_order(client, sym)

# Handle GTT Order Placement
if 'place_gtt' in st.session_state:
    sym = st.session_state['place_gtt']['tradingsymbol']
    st.session_state.pop('place_gtt')
    st.write(f"## Place GTT Order for {sym}")
    with st.form("place_gtt_form"):
        exchange = st.selectbox("Exchange", ["NSE", "BSE", "NFO", "MCX"], index=0)
        tradingsymbol = sym
        condition = st.selectbox("Condition", ["LTP_ABOVE", "LTP_BELOW"], index=0)
        alert_price = st.number_input("Alert Price", min_value=0.0, format="%.2f", step=0.05)
        order_type = st.selectbox("Order Type", ["BUY", "SELL"])
        price = st.number_input("Order Price", min_value=0.0, format="%.2f", step=0.05, value=alert_price)
        quantity = st.number_input("Quantity", min_value=1, step=1, value=1)
        product_type = st.selectbox("Product Type", ["", "CNC", "INTRADAY", "NORMAL"], index=0)
        remarks = st.text_input("Remarks", "")
        submitted = st.form_submit_button("🚀 Place GTT Order")
    if submitted:
        payload = {
            "exchange": exchange,
            "tradingsymbol": tradingsymbol,
            "condition": condition,
            "alert_price": str(alert_price),
            "order_type": order_type,
            "price": str(price),
            "quantity": str(int(quantity)),
        }
        if product_type:
            payload["product_type"] = product_type
        if remarks:
            payload["remarks"] = remarks
        try:
            resp = client.gtt_place(payload)
            if isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                st.success(f"✅ GTT Order Placed. Alert ID: {resp.get('alert_id')}")
            else:
                st.error(f"Failed to place GTT order: {resp}")
        except Exception as e:
            st.error(f"Error: {e}")

# Handle OCO Order Placement
if 'place_oco' in st.session_state:
    sym = st.session_state['place_oco']['tradingsymbol']
    st.session_state.pop('place_oco')
    st.write(f"## Place OCO Order for {sym}")
    with st.form("place_oco_form"):
        exchange = st.selectbox("Exchange", ["NSE", "BSE", "NFO", "MCX"], index=2)
        tradingsymbol = sym
        order_type = st.selectbox("Order Type", ["BUY", "SELL"], index=1)
        target_quantity = st.number_input("Target Quantity", min_value=1, step=1, value=50)
        stoploss_quantity = st.number_input("Stoploss Quantity", min_value=1, step=1, value=50)
        target_price = st.number_input("Target Price", min_value=0.0, format="%.2f")
        stoploss_price = st.number_input("Stoploss Price", min_value=0.0, format="%.2f")
        remarks = st.text_input("Remarks", value="admin")
        submitted_oco = st.form_submit_button("🚀 Place OCO Order")
    if submitted_oco:
        payload = {
            "exchange": exchange,
            "tradingsymbol": tradingsymbol,
            "order_type": order_type,
            "target_quantity": str(int(target_quantity)),
            "stoploss_quantity": str(int(stoploss_quantity)),
            "target_price": str(target_price),
            "stoploss_price": str(stoploss_price),
        }
        if remarks:
            payload["remarks"] = remarks
        try:
            resp = client.oco_place(payload)
            if isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                st.success(f"✅ OCO Order Placed. Alert ID: {resp.get('alert_id')}")
            else:
                st.error(f"Failed to place OCO order: {resp}")
        except Exception as e:
            st.error(f"Error: {e}")

# --- End ---
