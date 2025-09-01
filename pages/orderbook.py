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
        # Fetch orderbook immediately
        resp = client.get_orders()  # calls /orders
        if not resp:
            st.warning("⚠️ API returned empty response")
        else:
            orders = resp.get("orders", [])
            if not orders:
                st.info("No orders found in orderbook today.")
            else:
                df = pd.DataFrame(orders)

                # Show columns for debugging
                st.caption(f"Available columns: {list(df.columns)}")

                # Detect status column
                status_col = None
                for col in ["status", "order_status"]:
                    if col in df.columns:
                        status_col = col
                        break

                # Normalize status if present
                if status_col:
                    df["normalized_status"] = (
                        df[status_col].astype(str)
                        .str.replace("_", " ")
                        .str.strip()
                        .str.upper()
                    )
                else:
                    df["normalized_status"] = None

                # --- Full Orderbook ---
                st.subheader("📋 Complete Orderbook")
                st.dataframe(df, use_container_width=True)

                # --- Filter Active Orders (OPEN / PARTIAL / pending_qty > 0) ---
                st.subheader("⚙️ Active Orders (Open / Partially Filled)")

                def is_active(row):
                    status_val = str(row.get("normalized_status", "")).upper()
                    pending_qty = float(row.get("pending_qty", 0) or 0)

                    return (
                        "OPEN" in status_val
                        or "PARTIALLY" in status_val
                        or pending_qty > 0
                    )

                active_orders = df[df.apply(is_active, axis=1)]

                if active_orders.empty:
                    st.info("✅ No active orders to manage.")
                else:
                    # Compact table view
                    display_cols = [
                        "order_id", "tradingsymbol", "order_type",
                        "quantity", "price", "product_type",
                        status_col if status_col else "pending_qty"
                    ]
                    display_cols = [c for c in display_cols if c in active_orders.columns]

                    st.dataframe(active_orders[display_cols], use_container_width=True)

                    # Inline action rows
                    for idx, order in active_orders.iterrows():
                        st.markdown("---")
                        st.write(
                            f"**Order ID:** {order['order_id']} | "
                            f"Symbol: {order.get('tradingsymbol','')} | "
                            f"Qty: {order.get('quantity','')} | Price: {order.get('price','')} | "
                            f"Status: {order.get(status_col,'') if status_col else ''} | "
                            f"Pending Qty: {order.get('pending_qty','')}"
                        )

                        col1, col2 = st.columns(2)

                        # Cancel Order
                        with col1:
                            if st.button(f"❌ Cancel {order['order_id']}", key=f"cancel_{order['order_id']}"):
                                try:
                                    cancel_resp = client.cancel_order(order_id=order['order_id'])  # calls /cancel/{id}
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
                                            "exchange": order.get("exchange"),
                                            "order_id": order["order_id"],
                                            "tradingsymbol": order.get("tradingsymbol"),
                                            "quantity": int(new_qty) if new_qty else order.get("quantity"),
                                            "price": float(new_price) if new_price else order.get("price"),
                                            "product_type": order.get("product_type", "NORMAL"),
                                            "order_type": order.get("order_type"),
                                            "price_type": order.get("price_type", "LIMIT"),
                                        }
                                        # remove None/empty
                                        payload = {k: v for k, v in payload.items() if v not in [None, ""]}

                                        modify_resp = client.modify_order(payload)  # calls /modify
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
