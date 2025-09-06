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

# -------------------- Helpers --------------------
def _safe_str(x):
    return "" if x is None else str(x)

def _payload_clean(d: Dict) -> Dict:
    return {k: _safe_str(v) for k, v in d.items() if v is not None and str(v) != ""}

def build_gtt_payload(exchange, tradingsymbol, condition, alert_price, quantity, side, price, product_type, remarks):
    return {
        "exchange": exchange,
        "tradingsymbol": tradingsymbol,
        "condition": condition,
        "alert_price": f"{alert_price:.2f}",
        "quantity": str(int(quantity)),
        "order_type": side,
        "price": f"{price:.2f}",
        **({"product_type": product_type} if product_type else {}),
        **({"remarks": remarks} if remarks else {}),
    }

def build_oco_payload(tradingsymbol, exchange, side, tq, tp, sq, sp, product_type, remarks):
    return {
        "tradingsymbol": tradingsymbol,
        "exchange": exchange,
        "order_type": side,
        "target_quantity": str(int(tq)),
        "target_price": f"{tp:.2f}",
        "stoploss_quantity": str(int(sq)),
        "stoploss_price": f"{sp:.2f}",
        "remarks": remarks or "",
        **({"product_type": product_type} if product_type else {}),
    }

# Layout
gtt_col, oco_col = st.columns(2)

# -------------------- GTT --------------------
with gtt_col:
    with st.expander("📌 Place GTT Order", expanded=True):
        side_choice = st.radio("Select Side", ["BUY", "SELL"], horizontal=True)
        side_color = "green" if side_choice == "BUY" else "red"
        st.markdown(f"**Selected: <span style='color:{side_color}'>{side_choice}</span>**", unsafe_allow_html=True)

        with st.form("gtt_form"):
            st.caption("GTT (Good Till Triggered) — alert that fires into an order.")

            exchange = st.selectbox("Exchange", ["NSE", "BSE", "NFO", "MCX"])
            tradingsymbol = st.text_input("Trading Symbol", placeholder="e.g. TCS-EQ").strip().upper()
            condition = st.selectbox("Condition", ["LTP_ABOVE", "LTP_BELOW"])

            c1, c2 = st.columns(2)
            with c1:
                alert_price = st.number_input("Alert Price", min_value=0.0, step=0.05, format="%.2f")
                quantity = st.number_input("Quantity", min_value=1, step=1, value=1)
            with c2:
                price = st.number_input("Order Price", min_value=0.0, step=0.05, format="%.2f")

            product_type = st.selectbox("Product Type", ["", "CNC", "INTRADAY", "NORMAL"])
            remarks = st.text_input("Remarks (optional)")

            submit = st.form_submit_button("Preview GTT Payload")

        if submit:
            if not tradingsymbol:
                st.error("❌ Trading symbol required.")
            elif alert_price <= 0 or price <= 0:
                st.error("❌ Alert and Order prices must be > 0.")
            else:
                st.session_state["_pending_gtt"] = build_gtt_payload(
                    exchange, tradingsymbol, condition, alert_price, quantity, side_choice, price, product_type, remarks
                )
                st.success("✅ Preview ready. Confirm below.")

        if "_pending_gtt" in st.session_state:
            st.markdown("---")
            st.subheader("Confirm GTT Order")
            st.json(st.session_state["_pending_gtt"])
            c1, c2 = st.columns(2)
            confirm_label = f"✅ Confirm {side_choice} GTT"
            confirm_btn = c1.button(confirm_label, key="confirm_gtt")
            if confirm_btn:
                try:
                    payload = _payload_clean(st.session_state["_pending_gtt"])
                    if debug:
                        st.json({"raw": st.session_state["_pending_gtt"], "clean": payload})

                    resp = client.gtt_place(payload)
                    if debug:
                        st.write(resp)

                    if isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                        st.success(f"✅ GTT placed. ID: {resp.get('alert_id')}")
                        del st.session_state["_pending_gtt"]
                        st.rerun()
                    else:
                        st.error(f"❌ Failed: {resp}")
                except Exception as e:
                    st.error(str(e))
                    st.text(traceback.format_exc())
            if c2.button("❌ Cancel GTT"):
                del st.session_state["_pending_gtt"]
                st.info("Cancelled.")

# -------------------- OCO --------------------
with oco_col:
    with st.expander("🎯 Place OCO Order", expanded=False):
        side_choice = st.radio("Select Side (OCO)", ["BUY", "SELL"], horizontal=True)
        side_color = "green" if side_choice == "BUY" else "red"
        st.markdown(f"**Selected: <span style='color:{side_color}'>{side_choice}</span>**", unsafe_allow_html=True)

        st.caption("OCO = Target + Stoploss. One triggers, other cancels.")

        with st.form("oco_form"):
            remarks = st.text_input("Remarks (optional)")
            tradingsymbol = st.text_input("Trading Symbol", placeholder="e.g. NIFTY29MAR23F").strip().upper()
            exchange = st.selectbox("Exchange", ["NFO", "NSE", "BSE", "MCX"])

            q1, q2 = st.columns(2)
            with q1:
                tq = st.number_input("Target Qty", min_value=1, step=1, value=1)
                tp = st.number_input("Target Price", min_value=0.0, step=0.05, format="%.2f")
            with q2:
                sq = st.number_input("Stop Qty", min_value=1, step=1, value=1)
                sp = st.number_input("Stop Price", min_value=0.0, step=0.05, format="%.2f")

            product_type = st.selectbox("Product Type", ["", "CNC", "INTRADAY", "NORMAL"])

            submit = st.form_submit_button("Preview OCO Payload")

        if submit:
            if not tradingsymbol:
                st.error("❌ Trading symbol required.")
            elif tp <= 0 or sp <= 0 or tp == sp:
                st.error("❌ Target/Stoploss prices invalid.")
            else:
                st.session_state["_pending_oco"] = build_oco_payload(
                    tradingsymbol, exchange, side_choice, tq, tp, sq, sp, product_type, remarks
                )
                st.success("✅ Preview ready. Confirm below.")

        if "_pending_oco" in st.session_state:
            st.markdown("---")
            st.subheader("Confirm OCO Order")
            st.json(st.session_state["_pending_oco"])
            c1, c2 = st.columns(2)
            confirm_label = f"✅ Confirm {side_choice} OCO"
            confirm_btn = c1.button(confirm_label, key="confirm_oco")
            if confirm_btn:
                try:
                    payload = _payload_clean(st.session_state["_pending_oco"])
                    if debug:
                        st.json({"raw": st.session_state["_pending_oco"], "clean": payload})

                    resp = client.oco_place(payload)
                    if debug:
                        st.write(resp)

                    if isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                        st.success(f"✅ OCO placed. ID: {resp.get('alert_id')}")
                        del st.session_state["_pending_oco"]
                        st.rerun()
                    else:
                        st.error(f"❌ Failed: {resp}")
                except Exception as e:
                    st.error(str(e))
                    st.text(traceback.format_exc())
            if c2.button("❌ Cancel OCO"):
                del st.session_state["_pending_oco"]
                st.info("Cancelled.")

# -------------------- Hints --------------------
st.markdown("---")
st.info("After placing: Check your **GTT / OCO Orderbook** to verify.")

if debug:
    st.markdown("---")
    st.write({k: v for k, v in st.session_state.items() if k.startswith("_pending_")})
