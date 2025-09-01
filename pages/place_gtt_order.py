# pages/place_gtt_order.py
import streamlit as st
import traceback

def show_place_gtt_order():
    st.header("📌 Place GTT Order — Definedge")

    client = st.session_state.get("client")
    if not client:
        st.error("⚠️ Not logged in. Please login first from the Login page.")
        st.stop()

    # Optional debug toggle
    debug = st.checkbox("Show debug info", value=False)

    with st.form("gtt_place_form"):
        exchange = st.selectbox("Exchange", ["NSE", "BSE", "NFO", "MCX"], index=0)
        tradingsymbol = st.text_input("Trading Symbol (e.g. TCS-EQ)", value="")
        condition = st.selectbox("Condition", ["LTP_ABOVE", "LTP_BELOW"], index=0)
        alert_price = st.number_input("Alert Price", min_value=0.0, format="%.2f", step=0.05)
        order_type = st.selectbox("Order Type", ["BUY", "SELL"])
        price = st.number_input("Order Price (price to place order)", min_value=0.0, format="%.2f", step=0.05, value=alert_price)
        quantity = st.number_input("Quantity", min_value=1, step=1, value=1)
        product_type = st.selectbox("Product Type (optional)", ["", "CNC", "INTRADAY", "NORMAL"], index=0)
        remarks = st.text_input("Remarks (optional)", "")
        submitted = st.form_submit_button("🚀 Place GTT Order")

    if submitted:
        # basic validation
        if not tradingsymbol.strip():
            st.error("Please provide a trading symbol.")
            return

        payload = {
            "exchange": exchange,
            "tradingsymbol": tradingsymbol.strip(),
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

        if debug:
            st.write("🔎 Debug: payload to send")
            st.json(payload)

        try:
            # Use your Definedge client's wrapper (no base URL or manual headers here)
            resp = client.gtt_place(payload)

            if debug:
                st.write("🔎 Debug: raw API response")
                st.write(resp)

            # Expected response: { "status": "SUCCESS", "alert_id": "...", "message": "...", "request_time": "..." }
            if isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                alert_id = resp.get("alert_id")
                msg = resp.get("message") or "GTT order placed"
                st.success(f"✅ {msg} — Alert ID: {alert_id}")
                st.write(resp)
            else:
                # If API returns non-success but valid structure, show friendly info
                st.error(f"❌ Failed to place GTT order. Response: {resp}")
        except Exception as e:
            st.error(f"🚨 Exception while placing GTT order: {e}")
            st.text(traceback.format_exc())

    # quick hint
    st.markdown(
        "Hint: After successful placement, you can open **GTT Order Book** page to verify the new alert. "
        "If GTT order doesn't appear immediately, call refresh on that page."
    )
    
