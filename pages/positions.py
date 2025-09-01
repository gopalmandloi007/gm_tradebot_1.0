# positions.py
import streamlit as st
import pandas as pd

def show():
    st.title("📈 Positions")

    client = st.session_state.get("client")
    if not client:
        st.error("⚠️ Not logged in")
        st.stop()

    # Debug keys
    st.write("🔎 Debug: session_state keys:", list(st.session_state.keys()))

    try:
        resp = client.get_positions()
        st.write("🔎 Debug: Raw response:", resp)

        if resp.get("status") != "SUCCESS":
            st.error("⚠️ Positions API failed")
            st.stop()

        data = resp.get("data", [])
        records = []

        for pos in data:
            base = {k: v for k, v in pos.items() if k != "tradingsymbol"}
            for ts in pos.get("tradingsymbol", []):
                if ts.get("exchange") == "NSE":
                    records.append({**base, **ts})

        st.write("🔎 Debug: Flattened records:", records)

        if records:
            df = pd.DataFrame(records)
            st.success(f"✅ NSE Positions found: {len(df)}")
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("⚠️ No NSE positions found")

    except Exception as e:
        st.error(f"Positions fetch failed: {e}")
        
