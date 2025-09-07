import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, timedelta
import traceback

st.set_page_config(layout="wide")
st.title("📑 Place Order — Improved Flow")

# -----------------------
# Session defaults
# -----------------------
if "ltp" not in st.session_state:
    st.session_state.ltp = None
if "price" not in st.session_state:
    st.session_state.price = 0.0
if "trigger_price" not in st.session_state:
    st.session_state.trigger_price = 0.0
if "side" not in st.session_state:
    st.session_state.side = "Buy"

# -----------------------
# Order side selection with color
# -----------------------
side = st.radio("Select Order Side", ["Buy", "Sell"], horizontal=True, index=0)

st.session_state.side = side

if side == "Buy":
    st.markdown("<h3 style='color:green;'>🟢 BUY Order Selected</h3>", unsafe_allow_html=True)
else:
    st.markdown("<h3 style='color:red;'>🔴 SELL Order Selected</h3>", unsafe_allow_html=True)

# -----------------------
# Symbol selection (for demo, using text input)
# -----------------------
symbol = st.text_input("Symbol", value="RELIANCE")

# -----------------------
# LTP refresh handling
# -----------------------
def get_ltp(sym):
    # Dummy fetch (replace with broker API)
    import random
    return round(random.uniform(2000, 3000), 2)

if st.button("🔄 Refresh LTP"):
    ltp = get_ltp(symbol)
    if ltp:
        st.session_state.ltp = ltp
        st.success(f"LTP refreshed: {ltp}")
    else:
        st.warning("Failed to fetch LTP")

if st.session_state.ltp:
    st.metric("Current LTP", st.session_state.ltp)
    if st.button("📌 Set Price = LTP"):
        st.session_state.price = st.session_state.ltp

# -----------------------
# Conditional order entry (only if Buy/Sell selected)
# -----------------------
if side in ["Buy", "Sell"]:
    qty = st.number_input("Quantity", min_value=1, step=1)
    price = st.number_input("Price", value=float(st.session_state.price), step=0.05)
    trigger_price = st.number_input("Trigger Price", value=float(st.session_state.trigger_price), step=0.05)
    order_type = st.selectbox("Order Type", ["LIMIT", "MARKET", "SL", "SL-M"])

    # Save state
    st.session_state.price = price
    st.session_state.trigger_price = trigger_price

    if st.button("Preview Order"):
        st.write("### Order Preview")
        st.json({
            "side": side,
            "symbol": symbol,
            "qty": qty,
            "price": price,
            "trigger_price": trigger_price,
            "order_type": order_type
        })

        if st.button("Confirm & Place Order"):
            st.success("✅ Order placed (dummy simulation)")
