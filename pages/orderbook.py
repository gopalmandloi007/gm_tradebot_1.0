# pages/orderbook.py
import streamlit as st
import traceback
import pandas as pd

st.header("📑 Orderbook — Definedge")

client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
else:
    try:
        resp = client.get_orders()  # calls /orders
        if not resp:
            st.warning("⚠️ API returned empty response")
        else:
            orders = resp.get("orders", [])
            df = pd.DataFrame(orders) if orders else pd.DataFrame()

            if df.empty:
                st.info("No orders found in orderbook today.")
            else:
                st.caption(f"Available columns: {list(df.columns)}")

                if "order_status" in df.columns:
                    df["normalized_status"] = (
                        df["order_status"].astype(str)
                        .str.replace("_", " ")
                        .str.strip()
                        .str.upper()
                    )
                else:
                    df["normalized_status"] = None

                # --- Full Orderbook ---
                st.subheader("📋 Complete Orderbook")
                st.dataframe(df, use_container_width=True)

                # --- Segregated Orderbook by Status ---
                st.subheader("📊 Orders Segregated by Status")

                status_categories = ["CANCELED", "COMPLETE", "NEW", "OPEN", "REJECTED", "REPLACED"]

                for status in status_categories:
                    subset = df[df["normalized_status"] == status]
                    st.markdown(f"### 🔹 {status} Orders")
                    if not subset.empty:
                        display_cols = [
                            "order_id", "tradingsymbol", "order_type",
                            "quantity", "price", "product_type",
                            "order_status", "pending_qty"
                        ]
                        display_cols = [c for c in display_cols if c in subset.columns]
                        st.dataframe(subset[display_cols], use_container_width=True)

                        # Only allow actions for OPEN / NEW orders
                        if status in ["OPEN", "NEW"]:
                            for idx, order in subset.iterrows():
                                st.markdown("---")
                                st.write(
                                    f"**Order ID:** {order['order_id']} | "
                                    f"Symbol: {order.get('tradingsymbol','')} | "
                                    f"Qty: {order.get('quantity','')} | Price: {order.get('price','')} | "
                                    f"Status: {order.get('order_status','')} | "
                                    f"Pending Qty: {order.get('pending_qty','')}"
                                )

                                col1, col2 = st.columns(2)

                                # Cancel Order
                                with col1:
                                    if st.button(f"❌ Cancel {order['order_id']}", key=f"cancel_{order['order_id']}"):
                                        try:
                                            cancel_resp = client.cancel_order(order_id=order['order_id'])
                                            st.write("🔎 Cancel API Response:", cancel_resp)
                                            if cancel_resp.get("status") == "SUCCESS":
                                                st.success(f"Order {order['order_id']} cancelled successfully ✅")
                                                st.experimental_rerun()
                                            else:
                                                st.error(f"Cancel failed: {cancel_resp}")
                                        except Exception as e:
                                            st.error(f"Cancel API failed: {e}")
                                            st.text(traceback.format_exc())

                                # Modify Order
                                with col2:
                                    with st.form(key=f"modify_{order['order_id']}"):
                                        st.write("✏️ Modify Order")
                                        new_price = st.text_input("New Price", str(order.get("price", "")), key=f"price_{order['order_id']}")
                                        new_qty = st.text_input("New Quantity", str(order.get("quantity", "")), key=f"qty_{order['order_id']}")
                                        submitted = st.form_submit_button("Update Order")

                                        if submitted:
                                            try:
                                                payload = {
                                                    "exchange": order.get("exchange"),
                                                    "order_id": order["order_id"],
                                                    "tradingsymbol": order.get("tradingsymbol"),
                                                    "quantity": int(new_qty) if new_qty else order.get("quantity"),
                                                    "price": float(new_price) if new_price else order.get("price"),
                                                    "product_type": order.get("product_type", "NORMAL"),
                                                    "order_type": order.get("order_type"),
                                                    "price_type": order.get("price_type", "LIMIT"),
                                                }
                                                payload = {k: v for k, v in payload.items() if v not in [None, ""]}

                                                modify_resp = client.modify_order(payload)
                                                st.write("🔎 Modify API Response:", modify_resp)
                                                if modify_resp.get("status") == "SUCCESS":
                                                    st.success(f"Order {order['order_id']} modified successfully ✅")
                                                    st.experimental_rerun()
                                                else:
                                                    st.error(f"Modify failed: {modify_resp}")
                                            except Exception as e:
                                                st.error(f"Modify API failed: {e}")
                                                st.text(traceback.format_exc())
                    else:
                        st.info(f"No {status} orders found.")

                # --- Manual Action Section ---
                st.subheader("🛠️ Manual Cancel / Modify by Order ID")

                with st.form("manual_action"):
                    manual_order_id = st.text_input("Enter Order ID")
                    action = st.radio("Select Action", ["Cancel", "Modify"])
                    new_price = st.text_input("New Price (for Modify)", "")
                    new_qty = st.text_input("New Quantity (for Modify)", "")
                    submitted = st.form_submit_button("Submit")

                    if submitted and manual_order_id:
                        try:
                            # Try to find details in df
                            order_row = df[df["order_id"] == manual_order_id]
                            if not order_row.empty:
                                order_data = order_row.iloc[0].to_dict()
                                st.info(f"🔎 Found details for Order {manual_order_id}: {order_data}")
                            else:
                                order_data = {}

                            if action == "Cancel":
                                cancel_resp = client.cancel_order(order_id=manual_order_id)
                                st.write("🔎 Cancel API Response:", cancel_resp)
                                if cancel_resp.get("status") == "SUCCESS":
                                    st.success(f"Order {manual_order_id} cancelled successfully ✅")
                                else:
                                    st.error(f"Cancel failed: {cancel_resp}")

                            elif action == "Modify":
                                payload = {
                                    "exchange": order_data.get("exchange", st.text_input("Exchange", "NSE")),
                                    "order_id": manual_order_id,
                                    "tradingsymbol": order_data.get("tradingsymbol", st.text_input("Trading Symbol", "")),
                                    "quantity": int(new_qty) if new_qty else order_data.get("quantity"),
                                    "price": float(new_price) if new_price else order_data.get("price"),
                                    "product_type": order_data.get("product_type", st.selectbox("Product Type", ["CNC", "INTRADAY", "NORMAL"])),
                                    "order_type": order_data.get("order_type", st.selectbox("Order Type", ["BUY", "SELL"])),
                                    "price_type": order_data.get("price_type", st.selectbox("Price Type", ["LIMIT", "MARKET", "SL-LIMIT", "SL-MARKET"])),
                                }
                                payload = {k: v for k, v in payload.items() if v not in [None, ""]}

                                modify_resp = client.modify_order(payload)
                                st.write("🔎 Modify API Response:", modify_resp)
                                if modify_resp.get("status") == "SUCCESS":
                                    st.success(f"Order {manual_order_id} modified successfully ✅")
                                else:
                                    st.error(f"Modify failed: {modify_resp}")

                        except Exception as e:
                            st.error(f"Manual action failed: {e}")
                            st.text(traceback.format_exc())
    except Exception as e:
        st.error(f"Fetching orderbook failed: {e}")
        st.text(traceback.format_exc())
