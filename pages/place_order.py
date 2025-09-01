# pages/place_order.py
import streamlit as st
import pandas as pd
import io
import zipfile
import requests
import time
import os

MASTER_URL = "https://app.definedgesecurities.com/public/allmaster.zip"
MASTER_FILE = "data/master/allmaster.csv"

# ---- Load or update master file ----
def download_and_extract_master():
    try:
        r = requests.get(MASTER_URL)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            csv_name = z.namelist()[0]
            with z.open(csv_name) as f:
                df = pd.read_csv(f, header=None)
        df.columns = ["SEGMENT","TOKEN","SYMBOL","TRADINGSYM","INSTRUMENT","EXPIRY",
                      "TICKSIZE","LOTSIZE","OPTIONTYPE","STRIKE","PRICEPREC","MULTIPLIER","ISIN","PRICEMULT","COMPANY"]
        os.makedirs("data/master", exist_ok=True)
        df.to_csv(MASTER_FILE, index=False)
        return df
    except Exception as e:
        st.error(f"Failed to download master file: {e}")
        return pd.DataFrame()

def load_master_symbols():
    try:
        df = pd.read_csv(MASTER_FILE)
        return df
    except:
        return download_and_extract_master()

# ---- Fetch LTP ----
def fetch_ltp(client, exchange, token):
    try:
        quotes = client.get_quotes(exchange, str(token))
        return float(quotes.get("ltp", 0.0))
    except:
        return 0.0

st.header("🛒 Place Order — Definedge")

client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from Login page.")
else:
    df_symbols = load_master_symbols()

    # --- Exchange selection ---
    exchange = st.radio("Exchange", ["NSE", "BSE", "NFO", "MCX"], index=0, horizontal=True)

    # Filter master for selected exchange
    df_exch = df_symbols[df_symbols["SEGMENT"] == exchange]

    # --- Trading Symbol selection ---
    selected_symbol = st.selectbox(
        "Trading Symbol",
        df_exch["TRADINGSYM"].tolist()
    )

    # --- Fetch token ---
    token_row = df_exch[df_exch["TRADINGSYM"] == selected_symbol]
    token = int(token_row["TOKEN"].values[0]) if not token_row.empty else None

    # --- Fetch user limits ---
    limits = client.api_get("/limits")
    cash_available = float(limits.get("cash", 0.0))

    # --- Fetch current LTP ---
    current_ltp = fetch_ltp(client, exchange, token) if token else 0.0
    price_input = st.number_input("Price", min_value=0.0, step=0.05, value=current_ltp)

    # --- Top info display: Trading Symbol, LTP, Cash ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Trading Symbol**")
        st.text(selected_symbol)
    with col2:
        st.markdown("**📈 LTP**")
        st.metric(label="", value=f"{current_ltp:.2f}")
    with col3:
        st.markdown("**💰 Cash Available:**")
        st.metric(label="", value=f"₹{cash_available:,.2f}")

    # --- Order form ---
    with st.form("place_order_form"):
        st.subheader("Order Details")
        order_type = st.radio("Order Type", ["BUY", "SELL"], index=0, horizontal=True)
        price_type = st.radio("Price Type", ["LIMIT", "MARKET", "SL-LIMIT", "SL-MARKET"], index=0, horizontal=True)
        place_by = st.radio("Place by", ["Quantity", "Amount"], index=0, horizontal=True)

        col_qty, col_amt = st.columns(2)
        with col_qty:
            quantity = st.number_input("Quantity", min_value=1, step=1, value=1)
        with col_amt:
            amount = st.number_input("Amount", min_value=0.0, step=0.05, value=0.0)
        trigger_price = st.number_input("Trigger Price (for SL orders)", min_value=0.0, step=0.05, value=0.0)

        col_prod, col_valid = st.columns(2)
        with col_prod:
            product_type = st.selectbox("Product Type", ["NORMAL", "INTRADAY", "CNC"], index=2)
        with col_valid:
            validity = st.selectbox("Validity", ["DAY", "IOC", "EOS"], index=0)

        remarks = st.text_input("Remarks (optional)", "")

        submitted = st.form_submit_button("🚀 Place Order")

    # --- Auto-refresh LTP ---
    if token:
        current_ltp = fetch_ltp(client, exchange, token)
        st.metric("📈 LTP", f"{current_ltp:.2f}")
        time.sleep(1)

    # --- Handle order placement ---
    if submitted:
        # Calculate quantity if placed by amount
        if place_by == "Amount" and amount > 0 and current_ltp > 0:
            quantity = max(1, int(amount // current_ltp))
        else:
            quantity = max(1, int(quantity))
        payload = {
            "exchange": exchange,
            "tradingsymbol": selected_symbol,
            "order_type": order_type,
            "price": str(price_input),
            "price_type": price_type,
            "product_type": product_type,
            "quantity": str(quantity),
            "validity": validity,
        }
        if trigger_price > 0:
            payload["trigger_price"] = str(trigger_price)
        if remarks:
            payload["remarks"] = remarks

        st.write("📦 Sending payload:")
        st.json(payload)

        resp = client.place_order(payload)
        st.write("📬 API Response:")
        st.json(resp)

        if resp.get("status") == "SUCCESS":
            st.success(f"✅ Order placed successfully. Order ID: {resp.get('order_id')}")
        else:
            st.error(f"❌ Order placement failed. Response: {resp}")
