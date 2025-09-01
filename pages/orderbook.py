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
        # Fetch orderbook
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

                # Normalize status
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

                status_categories = [
                    "CANCELED",
                    "COMPLETE",
                    "NEW",
                    "OPEN",
                    "REJECTED",
                    "REPLACED",
                ]

                for status in status_categories:
                    subset = df[df["normalized_status"] == status]
                    if not subset.empty:
                        st.markdown(f"### 🔹 {status} Orders")
                        display_cols = [
                            "order_id", "tradingsymbol", "order_type",
                            "quantity", "price", "product_type",
                            "order_status", "pending_qty"
                        ]
                        display_cols = [c for c in display_cols if c in subset.columns]
                        st.dataframe(subset[display_cols], use_container_width=True)
                    else:
                        st.markdown(f"### 🔹 {status} Orders")
                        st.info(f"No {status} orders found.")

    except Exception as e:
        st.error(f"Fetching orderbook failed: {e}")
        st.text(traceback.format_exc())
