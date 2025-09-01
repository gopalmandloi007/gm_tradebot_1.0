# trades.py
import streamlit as st
import pandas as pd

def show():
    st.title("💹 Trades Page (All Fields)")

    client = st.session_state.get("client")
    if not client:
        st.error("⚠️ Not logged in")
        st.stop()

    st.write("🔎 Debug: Current session_state keys:", list(st.session_state.keys()))

    try:
        resp = client.get_trades()
        st.write("🔎 Debug: Raw trades API response:", resp)

        if resp.get("status") != "SUCCESS":
            st.error("⚠️ Trades API failed")
            st.stop()

        raw_data = resp.get("data", [])
        st.write("🔎 Debug: Extracted data field:", raw_data)

        # ---- Flatten all fields (Only NSE) ----
        records = []
        for t in raw_data:
            base = {k: v for k, v in t.items() if k != "tradingsymbol"}
            for ts in t.get("tradingsymbol", []):
                if ts.get("exchange") == "NSE":   # ✅ Only NSE
                    row = {**base, **ts}
                    records.append(row)

        st.write("🔎 Debug: Flattened records:", records)

        if records:
            df = pd.DataFrame(records)
            st.success(f"✅ NSE Trades found: {len(df)}")
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("⚠️ No NSE trades found")

    except Exception as e:
        st.error(f"Trades fetch failed: {e}")
