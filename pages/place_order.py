import streamlit as st
import pandas as pd
import requests
import time

# Example client object with dummy methods for illustration
class DummyClient:
    def get_quotes(self, exchange, token):
        return {"ltp": 2217.80}
    def api_get(self, endpoint):
        return {"cash": 1226663.61}
    def place_order(self, payload):
        return {"status": "SUCCESS", "order_id": "123456"}

client = DummyClient()

st.header("🛒 Place Order — Definedge")

# Exchange selection
exchange = st.radio("Exchange", ["NSE", "BSE", "NFO", "MCX"], index=0, horizontal=True)

# Dummy data for symbols
symbols = ["ZYDUSWELL-EQ"]
selected_symbol = st.selectbox("Trading Symbol", symbols)

# Dummy token and LTP
token = 12345
current_ltp = 2217.80
cash_available = 1226663.61

# Fetch current LTP dynamically (simulate)
def fetch_ltp():
    return current_ltp

# Top info in compact row
col1, col2, col3 = st.columns([2, 1, 2])
with col1:
    st.markdown("**Trading Symbol**")
    st.text(selected_symbol)
with col2:
    st.markdown("**📈 LTP**")
    st.metric("", f"{fetch_ltp():.2f}")
with col3:
    st.markdown("**💰 Cash Available:**")
    st.metric("", f"₹{cash_available:,.2f}")

# Order form in a compact layout
with st.form("order_form"):
    st.subheader("Order Details")
    # Row 1: Order Type & Price Type
    col1, col2 = st.columns(2)
    with col1:
        order_type = st.radio("Order Type", ["BUY", "SELL"], index=0, horizontal=True)
    with col2:
        price_type = st.radio("Price Type", ["LIMIT", "MARKET", "SL-LIMIT", "SL-MARKET"], index=0, horizontal=True)

    # Row 2: Quantity & Amount
    col1, col2 = st.columns(2)
    with col1:
        quantity = st.number_input("Qty", min_value=1, step=1, value=1)
    with col2:
        amount = st.number_input("Amt", min_value=0.0, step=0.05, value=0.0)

    # Row 3: Price & Trigger Price
    col1, col2 = st.columns(2)
    with col1:
        price = st.number_input("Price", min_value=0.0, step=0.05, value=fetch_ltp())
    with col2:
        trigger_price = st.number_input("Trigger Price", min_value=0.0, step=0.05, value=0.0)

    # Row 4: Product & Validity
    col1, col2 = st.columns(2)
    with col1:
        product_type = st.selectbox("Product", ["NORMAL", "INTRADAY", "CNC"], index=2)
    with col2:
        validity = st.selectbox("Validity", ["DAY", "IOC", "EOS"], index=0)

    # Remarks
    remarks = st.text_input("Remarks", "")

    submitted = st.form_submit_button("🚀 Place Order")

# Simulate fetching latest LTP
if 'current_ltp' not in st.session_state:
    st.session_state['current_ltp'] = fetch_ltp()

if submitted:
    # Calculate quantity based on amount if needed
    if amount > 0 and fetch_ltp() > 0:
        qty = max(1, int(amount // fetch_ltp()))
    else:
        qty = max(1, int(quantity))
    payload = {
        "exchange": exchange,
        "tradingsymbol": selected_symbol,
        "order_type": order_type,
        "price": str(price),
        "price_type": price_type,
        "product_type": product_type,
        "quantity": str(qty),
        "validity": validity,
    }
    if trigger_price > 0:
        payload["trigger_price"] = str(trigger_price)
    if remarks:
        payload["remarks"] = remarks

    st.write("Sending payload:")
    st.json(payload)

    # Dummy order placement response
    response = {"status": "SUCCESS", "order_id": "123456"}
    st.write("API Response:")
    st.json(response)

    if response.get("status") == "SUCCESS":
        st.success(f"Order placed successfully. ID: {response.get('order_id')}")
    else:
        st.error("Order failed.")
