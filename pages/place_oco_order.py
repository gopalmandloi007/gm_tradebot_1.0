# pages/place_oco_order.py
import streamlit as st
import traceback

def show_place_oco_order():
    st.header("🎯 Place OCO Order — Definedge")

    client = st.session_state.get("client")
    if not client:
        st.error("⚠️ Not logged in. Please login first from the Login page.")
        st.stop()

    debug = st.checkbox("Show debug info", value=False)

    with st.form("oco_place_form"):
        exchange = st.selectbox("Exchange", ["NSE", "BSE", "NFO", "MCX"], index=2)
        tradingsymbol = st.text_input("Trading Symbol (e.g. NIFTY29MAR23F)", value="")
        order_type = st.selectbox("Order Type", ["BUY", "SELL"], index=1)

        target_quantity = st.number_input("Target Quantity", min_value=1, step=1, value=50)
        stoploss_quantity = st.number_input("Stoploss Quantity", min_value=1, step=1, value=50)

        target_price = st.number_input("Target Price", min_value=0.0, step=0.05, format="%.2f")
        stoploss_price = st.number_input("Stoploss Price", min_value=0.0, step=0.05, format="%.2f")

        remarks = st.text_input("Remarks (optional)", value="admin")

        submitted = st.form_submit_button("🚀 Place OCO Order")

    if submitted:
        if not tradingsymbol.strip():
            st.error("Please provide a trading symbol.")
            return

        payload = {
            "exchange": exchange,
            "tradingsymbol": tradingsymbol.strip(),
            "order_type": order_type,
            "target_quantity": str(int(target_quantity)),
            "stoploss_quantity": str(int(stoploss_quantity)),
            "target_price": str(target_price),
            "stoploss_price": str(stoploss_price),
        }
        if remarks:
            payload["remarks"] = remarks

        if debug:
            st.write("🔎 Debug: Payload to send")
            st.json(payload)

        try:
            resp = client.oco_place(payload)

            if debug:
                st.write("🔎 Raw API Response")
                st.write(resp)

            if isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                st.success(f"✅ {resp.get('message')} — Alert ID: {resp.get('alert_id')}")
                st.write(resp)
            else:
                st.error(f"❌ Failed to place OCO order. Response: {resp}")

        except Exception as e:
            st.error(f"🚨 Exception while placing OCO order: {e}")
            st.text(traceback.format_exc())

    st.markdown(
        "💡 Tip: After placement, open **Order Book / GTT Order Book** to verify. "
        "If it does not appear immediately, refresh that page."
                                                                  )
    
