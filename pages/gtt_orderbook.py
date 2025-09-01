# pages/gtt_orderbook.py
import streamlit as st
import pandas as pd
import traceback

def show():
    st.header("⏰ GTT & OCO Order Book — Definedge")

    client = st.session_state.get("client")
    if not client:
        st.error("⚠️ Not logged in. Please login first from the Login page.")
        st.stop()

    debug = st.checkbox("Show debug info", value=False)

    try:
        resp = client.gtt_orders()  # GTT + OCO orders API

        if debug:
            st.write("🔎 Raw API response:", resp)

        if not isinstance(resp, dict) or resp.get("status") != "SUCCESS":
            st.error(f"❌ API returned non-success status. Full response: {resp}")
            st.stop()

        rows = resp.get("pendingGTTOrderBook") or []

        if not rows:
            st.info("✅ No pending GTT / OCO orders found.")
            return

        # Build DataFrame
        df = pd.DataFrame(rows)

        # Preferred column order
        preferred_cols = [
            "alert_id", "order_time", "tradingsymbol", "exchange", "token",
            "order_type", "price_type", "product_type", "quantity", "lotsize",
            "trigger_price", "price", "condition", "remarks",
            "stoploss_quantity", "target_quantity",
            "stoploss_price", "target_price",
            "stoploss_trigger", "target_trigger",
        ]
        cols = [c for c in preferred_cols if c in df.columns] + \
               [c for c in df.columns if c not in preferred_cols]
        df = df[cols]

        # Optional search/filter
        search_symbol = st.text_input("Search by Trading Symbol").strip().upper()
        if search_symbol:
            df = df[df["tradingsymbol"].str.upper().str.contains(search_symbol)]

        st.success(f"✅ Found {len(df)} GTT/OCO orders")
        st.dataframe(df, use_container_width=True)

        # Download CSV
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download GTT/OCO orders (CSV)", csv, "gtt_oco_orders.csv", "text/csv")

        # ---- Action buttons ----
        st.markdown("---")
        st.subheader("⚡ Order Actions")

        selected_alert_id = st.text_input("Enter alert_id to modify/cancel order").strip()
        if selected_alert_id:
            st.write(f"Selected alert_id: `{selected_alert_id}`")

            # Modify Order
            with st.expander("Modify Order"):
                new_price = st.number_input("New Price", min_value=0.0, step=0.05)
                new_quantity = st.number_input("New Quantity", min_value=1, step=1)
                if st.button("🚀 Modify Order"):
                    try:
                        order_row = df[df["alert_id"] == selected_alert_id].iloc[0]
                        payload = {
                            "exchange": order_row["exchange"],
                            "alert_id": selected_alert_id,
                            "tradingsymbol": order_row["tradingsymbol"],
                            "condition": order_row.get("condition", ""),
                            "alert_price": str(new_price),
                            "order_type": order_row["order_type"],
                            "quantity": str(int(new_quantity)),
                            "price": str(new_price),
                            "product_type": order_row.get("product_type", "NORMAL")
                        }
                        resp_modify = client.gtt_modify(payload)
                        st.write(resp_modify)
                        if resp_modify.get("status") == "SUCCESS":
                            st.success(f"✅ Order Modified Successfully — Alert ID: {selected_alert_id}")
                        else:
                            st.error(f"❌ Failed to modify order: {resp_modify.get('message')}")
                    except Exception as e:
                        st.error(f"🚨 Exception: {e}")
                        st.text(traceback.format_exc())

            # Cancel Order
            with st.expander("Cancel Order"):
                if st.button("🛑 Cancel Order"):
                    try:
                        resp_cancel = client.gtt_cancel(selected_alert_id)
                        st.write(resp_cancel)
                        if resp_cancel.get("status") == "SUCCESS":
                            st.success(f"✅ Order Cancelled Successfully — Alert ID: {selected_alert_id}")
                        else:
                            st.error(f"❌ Failed to cancel order: {resp_cancel.get('message')}")
                    except Exception as e:
                        st.error(f"🚨 Exception: {e}")
                        st.text(traceback.format_exc())

    except Exception as e:
        st.error(f"⚠️ GTT order fetch failed: {e}")
        st.text(traceback.format_exc())
        
