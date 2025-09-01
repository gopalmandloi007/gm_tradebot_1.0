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
        # Directly fetch orderbook on page load
        resp = client.get_orders()  # calls /orders
        if not resp:
            st.warning("⚠️ API returned empty response")
        else:
            orders = resp.get("orders", [])
            if not orders:
                st.info("No orders found in orderbook today.")
            else:
                df = pd.DataFrame(orders)

                # Show raw columns for debugging
                st.caption(f"Available columns: {list(df.columns)}")

                # Detect possible status column
                status_col = None
                for col in ["status", "order_status"]:
                    if col in df.columns:
                        status_col = col
                        break

                # Add normalized_status column
                if status_col:
                    df["normalized_status"] = (
                        df[status_col].astype(str)
                        .str.replace("_", " ")
                        .str.strip()
                        .str.upper()
                    )
                else:
                    df["normalized_status"] = None

                # --- Full Orderbook (compact table) ---
                st.subheader("📋 Complete Orderbook")
                st.dataframe(df, use_container_width=True)

                # --- Manage Open / Partially Filled Orders ---
                st.subheader("⚙️ Manage Open / Partially Filled Orders")

                if status_col:
                    # Define accepted labels
                    open_labels = ["OPEN"]
                    partial_labels = [
                        "PARTIALLY FILLED", "PARTIALLYFILLED", "PARTIALLY FULFILLED"
                    ]

                    open_orders = df[
                        (df["normalized_status"].isin(open_labels + partial_labels))
                        | (("pending_qty" in df.columns) & (df["pending_qty"].astype(float) > 0))
                    ]
                elif "pending_qty" in df.columns:
                    open_orders = df[df["pending_qty"].astype(float) > 0]
                else:
                    open_orders = pd.DataFrame()

                if open_orders.empty:
                    st.info("✅ No OPEN or PARTIALLY FILLED orders to manage.")
                else:
                    st.dataframe(open_orders, use_container_width=True)

                    # Actions for each order
                    for idx, order in open_orders.iterrows():
                        st.markdown("---")
                        st.write(
                            f"**Order ID:** {order['order_id']} | "
                            f"Symbol: {order.get('tradingsymbol','')} | "
                            f"Qty: {order.get('quantity','')} | Price: {order.get('price','')} | "
                            f"Status: {order.get(status_col,'') if status_col else ''} | "
                            f"Pending Qty: {order.get('pending_qty','')}"
                        )

                        col1, col2 = st.columns(2)

                        cancel_key = f"cancel_{order['order_id']}"
                        form_key = f"modify_{order['order_id']}"

                        # Cancel Button
                        with col1:
                            if st.button(f"❌ Cancel {order['order_id']}", key=cancel_key):
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

                        # Modify Order Form
                        with col2:
                            with st.form(form_key):
                                st.write("✏️ Modify Order")
                                new_price = st.text_input(
                                    "New Price", str(order.get("price", "")),
                                    key=f"price_{order['order_id']}"
                                )
                                new_qty = st.text_input(
                                    "New Quantity", str(order.get("quantity", "")),
                                    key=f"qty_{order['order_id']}"
                                )
                                submitted = st.form_submit_button("Update Order")

                                if submitted:
                                    try:
                                        payload = {
                                            "order_id": order['order_id'],
                                            "exchange": order.get("exchange"),
                                            "tradingsymbol": order.get("tradingsymbol"),
                                            "order_type": order.get("order_type"),
                                            "price": float(new_price) if new_price else None,
                                            "quantity": int(new_qty) if new_qty else None,
                                            "product_type": order.get("product_type", "NORMAL"),
                                            "price_type": order.get("price_type", "LIMIT"),
                                        }
                                        payload = {k: v for k, v in payload.items() if v is not None}
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

    except Exception as e:
        st.error(f"Fetching orderbook failed: {e}")
        st.text(traceback.format_exc())
