# holdings.py
import streamlit as st
import pandas as pd

# Remove the show() function; execute code directly

# Get client from session state
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in")
    st.stop()

# Debug: show current session state keys
st.write("🔎 Debug: Current session_state keys:", list(st.session_state.keys()))

try:
    # Make API call to get holdings data
    resp = client.get_holdings()
    # Debug: show raw API response
    st.write("🔎 Debug: Raw holdings API response:", resp)

    # Check if API response indicates success
    if resp.get("status") != "SUCCESS":
        st.error("⚠️ Holdings API failed")
        st.stop()

    # Extract data list from response
    raw_data = resp.get("data", [])
    # Debug: show extracted data
    st.write("🔎 Debug: Extracted data field:", raw_data)

    # Flatten all fields, focusing on NSE exchange
    records = []
    for h in raw_data:
        # Extract all fields except 'tradingsymbol'
        base = {k: v for k, v in h.items() if k != "tradingsymbol"}
        # Loop through each tradingsymbol entry
        for ts in h.get("tradingsymbol", []):
            if ts.get("exchange") == "NSE":  # Only process NSE
                # Merge base fields with tradingsymbol fields
                row = {**base, **ts}
                records.append(row)

    # Debug: show flattened records
    st.write("🔎 Debug: Flattened records:", records)

    # Display data if available
    if records:
        df = pd.DataFrame(records)
        # Show full DataFrame
        st.success(f"✅ NSE Holdings found: {len(df)}")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("⚠️ No NSE holdings found")

except Exception as e:
    # Catch any unexpected errors
    st.error(f"Holdings fetch failed: {e}")
