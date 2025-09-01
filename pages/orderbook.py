# pages/orderbook.py
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Order Book", layout="wide")

# ---- Client from session ----
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in")
    st.stop()


# ---- Status normalization ----
def normalize_status(status: str, pending_qty: int) -> str:
    status = (status or "").strip().upper()
    if status in ["OPEN", "NEW", "PARTIALLY_FILLED", "PARTIALLY_FILLED", "PARTIALLY_FILLED"]:
        return "ACTIVE"
    elif status == "REJECTED":
        return "REJECTED"
    elif status in ["CANCELED", "COMPLETE"]:
        return "COMPLETE"
    elif status == "REPLACED":
        return "REPLACED"
    # fallback - agar rejected hai aur pending_qty > 0
    if pending_qty > 0 and status == "REJECTED":
        return "REJECTED"
    return status


# ---- Fetch orders ----
def load_orders():
    try:
        data = client.get_orders()
        df = pd.DataFrame(data)
        if df.empty:
            return df
        if "pending_qty" not in df.columns:
            df["pending_qty"] = 0
        df["normalized_status"] = df.apply(
            lambda x: normalize_status(x.get("order_status"), x.get("pending_qty", 0)),
            axis=1
        )
        return df
    except Exception as e:
        st.error(f"⚠️ Failed to load orders: {e}")
        return pd.DataFrame()


# ---- Modify Order ----
def modify_order(order_id, price=None, qty=None):
    payload = {"order_id": order_id}
    if price: 
        payload["price"] = price
    if qty:
        payload["quantity"] = qty
    try:
        res = client.modify_order(payload)
        if res.get("status") == "SUCCESS":
            st.success(f"Order {order_id} modified successfully ✅")
            st.rerun()
        else:
            st.error(f"Modify failed: {res}")
    except Exception as e:
        st.error(f"Modify API failed: {e}")


# ---- Cancel Order ----
def cancel_order(order_id):
    try:
        res = client.cancel_order(order_id)
        if res.get("status") == "SUCCESS":
            st.success(f"Order {order_id} cancelled ✅")
            st.rerun()
        else:
            st.error(f"Cancel failed: {res}")
    except Exception as e:
        st.error(f"Cancel API failed: {e}")


# ---- Main ----
df = load_orders()
if df.empty:
    st.info("📭 No orders found")
    st.stop()

# Active Orders
active_orders = df[df["normalized_status"] == "ACTIVE"]
if not active_orders.empty:
    st.subheader("⚙️ Active Orders (Open / Partially Filled)")
    for _, row in active_orders.iterrows():
        with st.expander(f"{row['tradingsymbol']} | Qty: {row['quantity']} | Price: {row['price']}"):
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                if st.button("✏️ Modify", key=f"mod_{row['order_id']}"):
                    with st.form(f"modify_form_{row['order_id']}"):
                        new_price = st.number_input("New Price", value=float(row["price"]), key=f"price_{row['order_id']}")
                        new_qty = st.number_input("New Quantity", value=int(row["pending_qty"]), key=f"qty_{row['order_id']}")
                        submitted = st.form_submit_button("Submit Modification")
                        if submitted:
                            modify_order(row["order_id"], new_price, new_qty)
            with col2:
                if st.button("❌ Cancel", key=f"cancel_{row['order_id']}"):
                    cancel_order(row["order_id"])
            with col3:
                st.json(row.to_dict())

# Rejected Orders
rejected_orders = df[df["normalized_status"] == "REJECTED"]
if not rejected_orders.empty:
    st.subheader("🚫 Rejected Orders")
    st.dataframe(rejected_orders)

# Completed Orders
completed_orders = df[df["normalized_status"] == "COMPLETE"]
if not completed_orders.empty:
    st.subheader("✅ Completed Orders")
    st.dataframe(completed_orders)
