# pages/place_gtt_order.py
"""
Streamlit page: Place GTT and OCO orders (user-friendly, safe preview + confirm flow).

Key features:
- Two separate flows (GTT and OCO) with helpful defaults and validation
- Two-step placement: Preview (build payload) -> Confirm (actual API call)
- Debug toggle to inspect raw payload/response
- All numeric fields are sent as strings (matching API examples)
- Uses session_state to hold pending payload so user can confirm or cancel

Expected client methods on your Definedge client wrapper:
- client.gtt_place(payload)  -> places GTT (/gttplaceorder)
- client.oco_place(payload)  -> places OCO (/ocoplaceorder)

If your wrapper names differ, rename the calls near the bottom of the confirm blocks.
"""
import streamlit as st
import traceback
from typing import Dict

st.set_page_config(layout="wide")
st.header("📌 Place GTT / OCO Orders — Definedge")

client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

# Debug toggle
debug = st.checkbox("Show debug info", value=False)

# Helpers
def _safe_str(x):
    if x is None:
        return ""
    return str(x)

def _payload_clean(d: Dict) -> Dict:
    # Remove empty values (but keep numeric strings like "0" if intentionally set)
    return {k: _safe_str(v) for k, v in d.items() if v is not None and str(v) != ""}

# Layout: two columns for GTT and OCO (desktop friendly)
col_left, col_right = st.columns([1, 1])

# -------------------- GTT ORDER --------------------
with col_left:
    with st.expander("📌 Place GTT Order", expanded=True):
        with st.form("gtt_place_form"):
            st.caption("GTT (Good Till Triggered) — place an alert which places an order when condition matches.")

            exchange = st.selectbox("Exchange", ["NSE", "BSE", "NFO", "MCX"], index=0)
            tradingsymbol = st.text_input("Trading Symbol (example: TCS-EQ)").strip().upper()
            condition = st.selectbox("Condition", ["LTP_ABOVE", "LTP_BELOW"], index=0)

            c1, c2 = st.columns(2)
            with c1:
                alert_price = st.number_input("Alert Price (trigger)", min_value=0.0, format="%.2f", step=0.05, value=0.0)
                quantity = st.number_input("Quantity", min_value=1, step=1, value=1)
            with c2:
                order_type = st.selectbox("Order Type", ["BUY", "SELL"])
                price = st.number_input("Order Price (price to place order)", min_value=0.0, format="%.2f", step=0.05, value=0.0)

            product_type = st.selectbox("Product Type (optional)", ["", "CNC", "INTRADAY", "NORMAL"], index=0)
            remarks = st.text_input("Remarks (optional)")

            submit_gtt = st.form_submit_button("Preview GTT Payload")

        # Preview stage: build payload and store in session_state for confirmation
        if submit_gtt:
            # Basic validation
            if not tradingsymbol:
                st.error("Please enter a trading symbol (e.g. TCS-EQ).")
            elif alert_price <= 0:
                st.error("Alert Price must be > 0.")
            elif price <= 0:
                st.error("Order Price must be > 0. If you want market order, set price same as alert or handle in API wrapper.")
            else:
                payload = {
                    "exchange": exchange,
                    "tradingsymbol": tradingsymbol,
                    "condition": condition,
                    "alert_price": str(round(float(alert_price), 2)),
                    "order_type": order_type,
                    "price": str(round(float(price), 2)),
                    "quantity": str(int(quantity)),
                }
                if product_type:
                    payload["product_type"] = product_type
                if remarks:
                    payload["remarks"] = remarks

                # Store for confirm/cancel
                st.session_state["_pending_gtt_payload"] = payload
                st.success("✅ Preview ready — please confirm below to place the GTT order.")

        # Confirm / Cancel UI
        if "_pending_gtt_payload" in st.session_state:
            st.markdown("---")
            st.subheader("Confirm GTT Order")
            st.json(st.session_state["_pending_gtt_payload"], expanded=False)
            c1, c2 = st.columns([1, 1])
            if c1.button("✅ Confirm & Place GTT", key="confirm_gtt"):
                try:
                    payload = _payload_clean(st.session_state["_pending_gtt_payload"])
                    if debug:
                        st.write("🔧 Payload sent to API:")
                        st.json(payload)

                    # Actual API call (ensure your client wrapper method name matches)
                    resp = client.gtt_place(payload)

                    if debug:
                        st.write("🔎 Raw response:")
                        st.write(resp)

                    if isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                        st.success(f"✅ GTT placed. Alert ID: {resp.get('alert_id')} — {resp.get('message','')}")
                        del st.session_state["_pending_gtt_payload"]
                        st.rerun()
                    else:
                        st.error(f"❌ Failed to place GTT: {resp}")
                except Exception as e:
                    st.error(f"🚨 Exception while placing GTT: {e}")
                    st.text(traceback.format_exc())

            if c2.button("❌ Cancel", key="cancel_gtt"):
                del st.session_state["_pending_gtt_payload"]
                st.info("Cancelled GTT placement.")

# -------------------- OCO ORDER --------------------
with col_right:
    with st.expander("🎯 Place OCO Order (One Cancels Other)", expanded=False):
        st.caption("OCO lets you set both Target and Stoploss. When either side executes fully, the other is cancelled.")

        with st.form("oco_place_form"):
            remarks = st.text_input("Remarks (optional)")
            tradingsymbol = st.text_input("Trading Symbol (example: NIFTY29MAR23F)").strip().upper()
            exchange = st.selectbox("Exchange", ["NFO", "NSE", "BSE", "MCX"], index=0)
            order_type = st.selectbox("Order Type", ["BUY", "SELL"])

            q1, q2 = st.columns(2)
            with q1:
                target_quantity = st.number_input("Target Quantity", min_value=1, step=1, value=1)
                target_price = st.number_input("Target Price", min_value=0.0, format="%.2f", step=0.05, value=0.0)
            with q2:
                stoploss_quantity = st.number_input("Stoploss Quantity", min_value=1, step=1, value=1)
                stoploss_price = st.number_input("Stoploss Price", min_value=0.0, format="%.2f", step=0.05, value=0.0)

            product_type = st.selectbox("Product Type (optional)", ["", "CNC", "INTRADAY", "NORMAL"], index=0)

            submit_oco = st.form_submit_button("Preview OCO Payload")

        if submit_oco:
            # Validation
            if not tradingsymbol:
                st.error("Please enter trading symbol for OCO.")
            elif target_price <= 0 or stoploss_price <= 0:
                st.error("Target and Stoploss prices must be > 0.")
            else:
                payload = {
                    "remarks": remarks or "",
                    "tradingsymbol": tradingsymbol,
                    "exchange": exchange,
                    "order_type": order_type,
                    "target_quantity": str(int(target_quantity)),
                    "stoploss_quantity": str(int(stoploss_quantity)),
                    "target_price": str(round(float(target_price), 2)),
                    "stoploss_price": str(round(float(stoploss_price), 2)),
                }
                if product_type:
                    payload["product_type"] = product_type

                st.session_state["_pending_oco_payload"] = payload
                st.success("✅ Preview ready — please confirm below to place the OCO order.")

        if "_pending_oco_payload" in st.session_state:
            st.markdown("---")
            st.subheader("Confirm OCO Order")
            st.json(st.session_state["_pending_oco_payload"], expanded=False)
            c1, c2 = st.columns([1, 1])
            if c1.button("✅ Confirm & Place OCO", key="confirm_oco"):
                try:
                    payload = _payload_clean(st.session_state["_pending_oco_payload"])
                    if debug:
                        st.write("🔧 Payload sent to API:")
                        st.json(payload)

                    # Actual API call (ensure your client wrapper method name matches)
                    resp = client.oco_place(payload)

                    if debug:
                        st.write("🔎 Raw response:")
                        st.write(resp)

                    if isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                        st.success(f"✅ OCO placed. Alert ID: {resp.get('alert_id')} — {resp.get('message','')}")
                        del st.session_state["_pending_oco_payload"]
                        st.rerun()
                    else:
                        st.error(f"❌ Failed to place OCO: {resp}")
                except Exception as e:
                    st.error(f"🚨 Exception while placing OCO: {e}")
                    st.text(traceback.format_exc())

            if c2.button("❌ Cancel", key="cancel_oco"):
                del st.session_state["_pending_oco_payload"]
                st.info("Cancelled OCO placement.")

# Quick hints and next steps
st.markdown("---")
st.info(
    "After successful placement:\n"
    "• Open **GTT Order Book** to verify the alert.\n"
    "• If order does not appear immediately, press refresh on the orderbook page.\n"
    "• If your Definedge client wrapper uses different method names, adjust `client.gtt_place` / `client.oco_place` to match your wrapper."
)

if debug:
    st.markdown("---")
    st.write("Session state keys:")
    st.write({k: v for k, v in st.session_state.items() if k.startswith("_pending_")})
