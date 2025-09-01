# debug_login.py
import streamlit as st
from definedge_api import DefinedgeClient

st.title("🔑 Definedge Login Debug")

# Secrets से credentials उठाओ
api_token = st.secrets.get("DEFINEDGE_API_TOKEN")
api_secret = st.secrets.get("DEFINEDGE_API_SECRET")

if "client" not in st.session_state:
    st.session_state.client = DefinedgeClient(api_token=api_token, api_secret=api_secret)

client = st.session_state.client

# Step 1 - OTP token fetch
if "otp_token" not in st.session_state:
    try:
        step1 = client.auth_step1()
        st.session_state.otp_token = step1.get("otp_token")
        st.write("✅ Step1 success:", step1)
    except Exception as e:
        st.error(f"Step1 failed: {e}")

# OTP input
otp_code = st.text_input("Enter OTP", type="password")

if st.button("Login"):
    try:
        result = client.auth_step2(st.session_state.otp_token, otp_code)
        session_key = result.get("susertoken") or result.get("session_key") or None
        if session_key:
            client.set_session_key(session_key)
            st.session_state.session_key = session_key
            st.success("✅ Login Success!")
            st.json(result)
        else:
            st.error("⚠️ No session_key/susertoken returned")
    except Exception as e:
        st.error(f"Login failed: {e}")

# Debug session values
st.subheader("🔍 Debug Info")
st.write("Session key in state:", st.session_state.get("session_key"))
st.write("Client session key:", client.api_session_key)
