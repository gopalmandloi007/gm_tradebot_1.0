# pages/orderbook.py
import streamlit as st
import traceback
import pandas as pd

def show():
    st.header("📑 Orderbook — Definedge (Manage by Symbol)")

    client = st.session_state.get("client")
    if not client:
        st.error("⚠️ Not logged in. Please login first from the Login page.")
        return

    if st.button("🔄 Fetch Orderbook"):
        try:
            resp = client.get_orders()   # calls /orders
            if not resp:
                st.warning("⚠️ API returned empty response")
                return

            status = resp.get("status")
            orders = resp.get("orders", [])

            if status != "SUCCESS":
                st.error(f"❌ API returned error. Response: {resp}")
                return

            if not orders:
                st.info("No orders found in orderbook today.")
                return

            df = pd.DataFrame(orders)
            st.success(f"✅ Orderbook fetched ({len(df)} orders)")
            st.dataframe(df, use_container_width=True)

            # --- Manage Orders by Symbol ---
            st.subheader("⚙️ Manage Orders by Symbol")
            symbols = df["tradingsymbol"].unique().tolist() if "tradingsymbol" in df.columns else []
            if not symbols:
                st.info("⚠️ No tradingsymbol found in response to manage.")
                return

            selected_symbol = st.selectbox("Select a symbol to manage:", symbols)
            symbol_orders = df[df["tradingsymbol"] == selected_symbol]

            if symbol_orders.empty:
                st.warning("⚠️ No orders found for this symbol")
                return

            st.write(f"📋 Orders for {selected_symbol}:")
            for idx, order in symbol_orders.iterrows():
                st.markdown("---")
                st.write(f"**Order ID:** {order['order_id']}")
                st.write(f"Exchange: {order.get('exchange', '')}, Type: {order.get('order_type', '')}, "
                         f"Qty: {order.get('quantity', '')}, Price: {order.get('price', '')}, "
                         f"Product: {order.get('product_type', '')}, Status: {order.get('status', '')}")

                col1, col2 = st.columns(2)

                # Cancel Button
                with col1:
                    if st.button(f"❌ Cancel {order['order_id']}"):
                        try:
                            cancel_resp = client.cancel_order(order_id=order['order_id'])
                            st.write("🔎 Cancel API Response:", cancel_resp)
                            if cancel_resp.get("status") == "SUCCESS":
                                st.success(f"Order {order['order_id']} cancelled successfully ✅")
                            else:
                                st.error(f"Cancel failed: {cancel_resp}")
                        except Exception as e:
                            st.error(f"Cancel API failed: {e}")
                            st.text(traceback.format_exc())

                # Modify Form
                with col2:
                    with st.form(f"modify_form_{order['order_id']}"):
                        st.write("✏️ Modify Order")
                        new_price = st.text_input("New Price", str(order.get("price", "")), key=f"price_{order['order_id']}")
                        new_qty = st.text_input("New Quantity", str(order.get("quantity", "")), key=f"qty_{order['order_id']}")
                        submitted = st.form_submit_button("Update Order", key=f"submit_{order['order_id']}")

                        if submitted:
                            try:
                                payload = {
                                    "order_id": order['order_id'],
                                    "exchange": order.get("exchange"),
                                    "tradingsymbol": selected_symbol,
                                    "order_type": order.get("order_type"),
                                    "price": float(new_price) if new_price else None,
                                    "quantity": int(new_qty) if new_qty else None,
                                    "product_type": order.get("product_type", "NORMAL"),
                                    "price_type": order.get("price_type", "LIMIT"),
                                }
                                modify_resp = client.modify_order(payload)
                                st.write("🔎 Modify API Response:", modify_resp)
                                if modify_resp.get("status") == "SUCCESS":
                                    st.success(f"Order {order['order_id']} modified successfully ✅")
                                else:
                                    st.error(f"Modify failed: {modify_resp}")
                            except Exception as e:
                                st.error(f"Modify API failed: {e}")
                                st.text(traceback.format_exc())

        except Exception as e:
            st.error(f"Fetching orderbook failed: {e}")
            st.text(traceback.format_exc())
            
