import streamlit as st
import pandas as pd
import traceback

st.header("📈 Positions — Definedge")

# --- Client check ---
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

try:
    resp = client.get_positions()
    if not resp or resp.get("status") != "SUCCESS":
        st.error("⚠️ Positions API failed or returned empty response")
        st.stop()

    data = resp.get("data", [])
    records = []
    for pos in data:
        base = {k: v for k, v in pos.items() if k != "tradingsymbol"}
        for ts in pos.get("tradingsymbol", []):
            if ts.get("exchange") == "NSE":
                records.append({**base, **ts})

    if not records:
        st.warning("⚠️ No NSE positions found")
        st.stop()

    df = pd.DataFrame(records)

    # --- Normalize columns ---
    df.rename(columns={"net_qty": "NetQty", "unrealized_pnl": "UnrealizedPnL", "realized_pnl": "RealizedPnL"}, inplace=True)

    # --- Sidebar Filters ---
    st.sidebar.header("🔍 Filters")
    symbol_filter = st.sidebar.text_input("Search by Symbol")
    product_filter = st.sidebar.multiselect("Filter by Product Type", sorted(df["product_type"].dropna().unique()))

    filtered_df = df.copy()
    if symbol_filter:
        filtered_df = filtered_df[filtered_df["tradingsymbol"].str.contains(symbol_filter, case=False, na=False)]
    if product_filter:
        filtered_df = filtered_df[filtered_df["product_type"].isin(product_filter)]

    # --- KPI Metrics ---
    st.subheader("📊 Position Summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Positions", len(df))
    col2.metric("Total Net Qty", df["NetQty"].sum())
    col3.metric("Total Unrealized P&L", round(df["UnrealizedPnL"].sum(), 2))

    # --- Download options ---
    st.download_button("⬇️ Download CSV", df.to_csv(index=False), "positions.csv", "text/csv")
    st.download_button("⬇️ Download JSON", df.to_json(orient="records"), "positions.json", "application/json")

    # --- Full Positions ---
    st.subheader("📋 Current Positions")
    st.dataframe(filtered_df, use_container_width=True)

    # --- Segregated by Net Position ---
    st.subheader("📂 Positions by Type")
    long_positions = filtered_df[filtered_df["NetQty"] > 0]
    short_positions = filtered_df[filtered_df["NetQty"] < 0]
    closed_positions = filtered_df[filtered_df["NetQty"] == 0]

    with st.expander(f"📈 Long Positions ({len(long_positions)})", expanded=True):
        st.dataframe(long_positions, use_container_width=True)

    with st.expander(f"📉 Short Positions ({len(short_positions)})", expanded=False):
        st.dataframe(short_positions, use_container_width=True)

    with st.expander(f"✅ Closed Positions ({len(closed_positions)})", expanded=False):
        st.dataframe(closed_positions, use_container_width=True)

    # --- Manual Square-off ---
    st.subheader("🛠️ Manual Square-off")
    with st.form("manual_squareoff"):
        sq_symbol = st.text_input("Enter Trading Symbol")
        sq_exchange = st.selectbox("Exchange", ["NSE", "BSE"])
        sq_qty = st.text_input("Quantity to Square-off")
        submitted = st.form_submit_button("Square-off")

        if submitted and sq_symbol and sq_qty:
            try:
                payload = {
                    "exchange": sq_exchange,
                    "tradingsymbol": sq_symbol,
                    "quantity": int(sq_qty),
                    "product_type": "INTRADAY",  # default
                }
                resp = client.square_off_position(payload)
                st.write("🔎 Square-off API Response:", resp)
                if resp.get("status") == "SUCCESS":
                    st.success(f"Position {sq_symbol} squared-off successfully ✅")
                    st.rerun()
                else:
                    st.error(f"Square-off failed: {resp}")
            except Exception as e:
                st.error(f"Square-off failed: {e}")
                st.text(traceback.format_exc())

except Exception as e:
    st.error(f"Fetching positions failed: {e}")
    st.text(traceback.format_exc())
