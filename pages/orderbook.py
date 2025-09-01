import streamlit as st
import pandas as pd

# Example: assume df is your orderbook DataFrame
# df = pd.DataFrame(orderbook_response["data"])  

# --- Normalize Status ---
def normalize_status(status):
    if not status:
        return "UNKNOWN"
    s = str(status).strip().upper()
    if "PARTIALLY" in s:
        return "PARTIALLY FILLED"
    elif "OPEN" in s or "NEW" in s:
        return "OPEN"
    elif "CANCEL" in s:
        return "CANCELED"
    elif "REJECT" in s:
        return "REJECTED"
    elif "COMPLETE" in s:
        return "COMPLETE"
    elif "REPLACE" in s:
        return "REPLACED"
    return s

df["normalized_status"] = df["order_status"].apply(normalize_status)

# --- Helper functions ---
def is_active(row):
    status_val = row["normalized_status"]
    pending_qty = float(row.get("pending_qty", 0) or 0)

    if status_val in ["REJECTED", "CANCELED", "COMPLETE"]:
        return False
    return status_val in ["OPEN", "PARTIALLY FILLED", "NEW"] or pending_qty > 0

def is_rejected(row):
    return row["normalized_status"] == "REJECTED"

def is_completed(row):
    return row["normalized_status"] == "COMPLETE"

# --- Tabs ---
tab1, tab2, tab3 = st.tabs(["⚙️ Active Orders", "❌ Rejected Orders", "✅ Completed Orders"])

# --- Active Orders ---
with tab1:
    active_orders = df[df.apply(is_active, axis=1)]
    st.subheader("⚙️ Active Orders (Open / Partially Filled / New)")

    if active_orders.empty:
        st.info("No active orders.")
    else:
        for _, row in active_orders.iterrows():
            cols = st.columns([2, 2, 2, 2, 2, 1, 1])
            cols[0].write(row["tradingsymbol"])
            cols[1].write(f"Qty: {row['quantity']}")
            cols[2].write(f"Pending: {row['pending_qty']}")
            cols[3].write(f"Price: {row['price']}")
            cols[4].write(row["normalized_status"])

            # Modify button
            if cols[5].button("✏️ Modify", key=f"mod_{row['order_id']}"):
                new_price = st.number_input(
                    f"New price for {row['tradingsymbol']} (Order {row['order_id']})",
                    value=float(row["price"]),
                    key=f"price_in_{row['order_id']}"
                )
                new_qty = st.number_input(
                    f"New qty for {row['tradingsymbol']} (Order {row['order_id']})",
                    value=int(row["pending_qty"]),
                    key=f"qty_in_{row['order_id']}"
                )
                if st.button(f"Confirm Modify {row['order_id']}", key=f"confirm_mod_{row['order_id']}"):
                    st.success(f"Order {row['order_id']} modified: Price={new_price}, Qty={new_qty}")
                    st.rerun()

            # Cancel button
            if cols[6].button("🗑 Cancel", key=f"cancel_{row['order_id']}"):
                st.warning(f"Order {row['order_id']} cancelled ✅")
                st.rerun()

# --- Rejected Orders ---
with tab2:
    rejected_orders = df[df.apply(is_rejected, axis=1)]
    st.subheader("❌ Rejected Orders")

    if rejected_orders.empty:
        st.info("No rejected orders.")
    else:
        st.dataframe(
            rejected_orders[
                ["order_id", "tradingsymbol", "quantity", "price", "order_status", "pending_qty"]
            ],
            use_container_width=True
        )

# --- Completed Orders ---
with tab3:
    completed_orders = df[df.apply(is_completed, axis=1)]
    st.subheader("✅ Completed Orders")

    if completed_orders.empty:
        st.info("No completed orders.")
    else:
        st.dataframe(
            completed_orders[
                ["order_id", "tradingsymbol", "quantity", "price", "order_status"]
            ],
            use_container_width=True
        )
