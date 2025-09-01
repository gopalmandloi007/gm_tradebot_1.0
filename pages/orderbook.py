import streamlit as st
import traceback
import pandas as pd

st.header("📑 Orderbook — Definedge")

# --- Client check ---
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

try:
    resp = client.get_orders()  # calls /orders
    if not resp:
        st.warning("⚠️ API returned empty response")
        st.stop()

    orders = resp.get("orders", [])
    df = pd.DataFrame(orders) if orders else pd.DataFrame()

    if df.empty:
        st.info("No orders found in orderbook today.")
        st.stop()

    # --- Normalize order status ---
    if "order_status" in df.columns:
        df["normalized_status"] = (
            df["order_status"].astype(str)
            .str.replace("_", " ")
            .str.strip()
            .str.upper()
        )
    else:
        df["normalized_status"] = None

    # --- Sidebar Filters ---
    st.sidebar.header("🔍 Filters")
    status_filter = st.sidebar.multiselect("Filter by Status", sorted(df["normalized_status"].dropna().unique()))
    symbol_filter = st.sidebar.text_input("Search by Symbol")

    filtered_df = df.copy()
    if status_filter:
        filtered_df = filtered_df[filtered_df["normalized_status"].isin(status_filter)]
    if symbol_filter:
        filtered_df = filtered_df[filtered_df["tradingsymbol"].str.contains(symbol_filter, case=False, na=False)]

    # --- KPI Summary ---
    st.subheader("📊 Order Summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Orders", len(df))
    col2.metric("Active Orders", len(df[df["normalized_status"].isin(["OPEN", "NEW"])]))
    col3.metric("Completed Orders", len(df[df["normalized_status"] == "COMPLETE"]))

    # --- Download options ---
    st.download_button("⬇️ Download CSV", df.to_csv(index=False), "orderbook.csv", "text/csv")
    st.download_button("⬇️ Download JSON", df.to_json(orient="records"), "orderbook.json", "application/json")

    # --- Full Orderbook ---
    st.subheader("📋 Orderbook")
    st.dataframe(filtered_df, use_container_width=True)

    # --- Orders by Status ---
    st.subheader("📂 Orders by Status")
    status_categories = ["OPEN", "NEW", "COMPLETE", "CANCELED", "REJECTED", "REPLACED"]

    for status in status_categories:
        subset = filtered_df[filtered_df["normalized_status"] == status]
        with st.expander(f"{status} Orders ({len(subset)})", expanded=(status in ["OPEN", "NEW"])):
            if not subset.empty:
                display_cols = [
                    "order_id", "tradingsymbol", "order_type",
                    "quantity", "price", "product_type",
                    "order_status", "pending_qty"
                ]
                display_cols = [c for c in display_cols if c in subset.columns]
                st.dataframe(subset[display_cols], use_container_width=True)

                if status in ["OPEN", "NEW"]:
                    selected_order = st.selectbox(
                        f"Select {status} order to manage",
                        subset["order_id"],
                        key=f"sel_{status}"
                    )
                    if selected_order:
                        order = subset[subset["order_id"] == selected_order].iloc[0]

                        st.write(f"**Order ID:** {order['order_id']} | Symbol: {order.get('tradingsymbol','')} | Qty: {order.get('quantity','')} | Price: {order.get('price','')}")

                        col1, col2 = st.columns(2)

                        # Cancel Order
                        with col1:
                            if st.button("❌ Cancel Order", key=f"cancel_{order['order_id']}"):
                                try:
                                    cancel_resp = client.cancel_order(order['order_id'])
                                    st.write("🔎 Cancel API Response:", cancel_resp)
                                    if cancel_resp.get("status") == "SUCCESS":
                                        st.success("Order cancelled successfully ✅")
                                        st.rerun()
                                    else:
                                        st.error(f"Cancel failed: {cancel_resp}")
                                except Exception as e:
                                    st.error(f"Cancel API failed: {e}")
                                    st.text(traceback.format_exc())

                        # Modify Order
                        with col2:
                            with st.form(key=f"modify_{order['order_id']}"):
                                st.write("✏️ Modify Order")
                                new_price = st.text_input("New Price", str(order.get("price", "")))
                                new_qty = st.text_input("New Quantity", str(order.get("quantity", "")))

                                new_trigger = None
                                if order.get("price_type") in ["SL-LIMIT", "SL-MARKET"]:
                                    new_trigger = st.text_input("New Trigger Price", str(order.get("trigger_price", "")))

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
                                        if new_trigger:
                                            payload["trigger_price"] = float(new_trigger)

                                        payload = {k: v for k, v in payload.items() if v not in [None, ""]}

                                        modify_resp = client.modify_order(payload)
                                        st.write("🔎 Modify API Response:", modify_resp)
                                        if modify_resp.get("status") == "SUCCESS":
                                            st.success("Order modified successfully ✅")
                                            st.rerun()
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
        manual_trigger = st.text_input("Trigger Price (only for SL orders)", "")
        submitted = st.form_submit_button("Submit")

        if submitted and manual_order_id:
            try:
                order_row = df[df["order_id"] == manual_order_id]
                order_data = order_row.iloc[0].to_dict() if not order_row.empty else {}

                if action == "Cancel":
                    cancel_resp = client.cancel_order(manual_order_id)
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
                    if manual_trigger:
                        payload["trigger_price"] = float(manual_trigger)

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
