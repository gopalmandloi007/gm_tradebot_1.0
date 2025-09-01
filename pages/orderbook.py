# pages/orderbook.py
import streamlit as st
import pandas as pd

st.title("📑 Order Book")

client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in")
    st.stop()

# -----------------------------
# Fetch Orderbook
# -----------------------------
try:
    resp = client.api_get("/orders")
    orders = resp.get("data", [])
except Exception as e:
    st.error(f"❌ Failed to fetch orderbook: {e}")
    st.stop()

if not orders:
    st.info("No orders found for today.")
    st.stop()

df = pd.DataFrame(orders)

# Normalize status
df["normalized_status"] = df["order_status"].str.upper().fillna("UNKNOWN")

# Ranking for sorting
status_order = {"OPEN": 0, "PARTIALLY_FILLED": 0, "COMPLETE": 1}
df["status_rank"] = df["normalized_status"].map(status_order).fillna(2)

# Sort → Open first, then complete, then rest
df = df.sort_values(["status_rank", "order_entry_time"], ascending=[True, False])

st.subheader("📊 All Orders (sorted)")
st.dataframe(df[
    ["order_id","tradingsymbol","order_type","price_type","quantity",
     "pending_qty","price","product_type","order_status","order_entry_time"]
])

# -----------------------------
# Manual Cancel / Modify by Order ID
# -----------------------------
st.subheader("🛠️ Manual Cancel / Modify by Order ID")

manual_order_id = st.text_input("Enter Order ID")

if manual_order_id:
    row = df[df["order_id"] == manual_order_id]

    if row.empty:
        st.warning(f"⚠️ Order {manual_order_id} not found in today’s orderbook.")
    else:
        details = row.iloc[0].to_dict()
        st.write("🔎 Found details for this order:")
        st.json(details)

        action = st.radio("Select Action", ["Cancel", "Modify"])

        if action == "Cancel":
            if st.button("🚫 Cancel Order"):
                try:
                    cancel_resp = client.cancel_order(orderid=manual_order_id)
                    st.success("✅ Cancel request sent!")
                    st.json(cancel_resp)
                except Exception as e:
                    st.error(f"❌ Cancel failed: {e}")

        elif action == "Modify":
            old_qty = int(details.get("quantity", 0))
            old_price = float(details.get("price", 0.0)) if details.get("price") else 0.0
            old_price_type = details.get("price_type", "LIMIT")

            new_qty = st.number_input("New Quantity", min_value=1, value=old_qty)
            new_price = 0.0

            if old_price_type == "LIMIT":
                new_price = st.number_input("New Price (enter 0 for MARKET)", value=old_price)

            if st.button("✏️ Submit Modify"):
                try:
                    price_type = "MARKET" if new_price == 0 else "LIMIT"
                    modify_payload = {
                        "orderid": manual_order_id,
                        "quantity": str(new_qty),
                        "price": str(new_price),
                        "price_type": price_type,
                    }
                    modify_resp = client.modify_order(**modify_payload)
                    st.success("✅ Modify request sent!")
                    st.json(modify_resp)
                except Exception as e:
                    st.error(f"❌ Modify failed: {e}")
