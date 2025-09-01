import streamlit as st

st.title("🛒 Place Order — Definedge")

# --- Exchange Selection with 4 Columns ---
exch_cols = st.columns(4)
exchanges = ["NSE", "BSE", "NFO", "MCX"]
exchange = None
for i, exch in enumerate(exchanges):
    with exch_cols[i]:
        # Using a single radio for each column with a unique key
        selected_exch = st.radio("Exchange", [exch], index=0, key=f"exchange_{exch}", horizontal=True)
        if selected_exch == exch:
            exchange = exch
if exchange is None:
    exchange = exchanges[0]

st.write(f"Selected Exchange: **{exchange}**")

# --- Trading Symbol ---
trading_symbols = ["ZYDUSWELL-EQ", "TATAMOTORS-EQ"]
trading_symbol = st.selectbox("Trading Symbol", trading_symbols, key="trading_symbol")

# --- Price and LTP ---
col_price, col_ltp = st.columns([2, 1])
with col_price:
    price = st.number_input("Price", min_value=0.0, value=2217.80, step=0.05, key="price_input")
with col_ltp:
    st.metric("📈 LTP", "2217.80")  # Replace with dynamic data if available

# --- Cash Available ---
st.info("💰 Cash Available: ₹1,226,663.61")  # Replace with actual data

# --- Order Type ---
col_order_type, col_price_type, col_product = st.columns(3)
with col_order_type:
    order_type = st.radio("Order Type", ["BUY", "SELL"], index=0, horizontal=True, key="order_type")
with col_price_type:
    # Display Price Type in two rows with unique keys
    st.markdown("**Price Type**")
    col_pt1, col_pt2 = st.columns(2)
    with col_pt1:
        price_type = st.radio("Price Type", ["LIMIT", "MARKET"], index=0, horizontal=True, key="price_type")
    with col_pt2:
        price_type2 = st.radio("Price Type", ["SL-LIMIT", "SL-MARKET"], index=0, horizontal=True, key="price_type2")
    # For simplicity, we'll just use one of these based on user choice
    # You could implement logic to select between them if needed
with col_product:
    product_type = st.radio("Product", ["NORMAL", "INTRADAY", "CNC"], index=2, horizontal=True, key="product_type")

# --- Compact Inputs for Trading Symbol, Price, Qty, Trigger Price ---
col_trad, col_prc, col_qty, col_trg = st.columns([2, 1, 1, 1])

with col_trad:
    trading_symbol = st.selectbox("Trading Symbol", trading_symbols, key="trading_symbol_compact")
with col_prc:
    price = st.number_input("Price", min_value=0.0, value=2217.80, step=0.05, key="price_input_compact")
with col_qty:
    quantity = st.number_input("Qty", min_value=1, step=1, value=1, key="qty_input")
with col_trg:
    trigger_price = st.number_input("Trigger Price", min_value=0.0, step=0.05, key="trigger_price_input")

# --- Price Type in Two Rows ---
st.markdown("**Price Type**")
col_pt1, col_pt2 = st.columns(2)
with col_pt1:
    price_type = st.radio("Price Type", ["LIMIT", "MARKET"], index=0, horizontal=True, key="price_type_row1")
with col_pt2:
    price_type2 = st.radio("Price Type", ["SL-LIMIT", "SL-MARKET"], index=0, horizontal=True, key="price_type_row2")

# --- Validity ---
validity = st.selectbox("Validity", ["DAY", "IOC", "EOS"], key="validity")

# --- Remarks ---
remarks = st.text_input("Remarks", "", key="remarks_input")

# --- Submit Button ---
if st.button("🚀 Place Order"):
    # Prepare payload for demonstration
    selected_price_type = price_type if price_type else price_type2
    order_payload = {
        "exchange": exchange,
        "trading_symbol": trading_symbol,
        "price": price,
        "order_type": order_type,
        "price_type": selected_price_type,
        "product_type": product_type,
        "quantity": quantity,
        "trigger_price": trigger_price,
        "validity": validity,
        "remarks": remarks,
    }
    st.write("### Order Payload")
    st.json(order_payload)

    # Here, replace with your order submission logic
    # resp = client.place_order(order_payload)
    # st.write("API Response:", resp)
