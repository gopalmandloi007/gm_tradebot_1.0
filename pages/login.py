import streamlit as st
import traceback
from typing import Optional

try:
    import pyotp
except ImportError:
    pyotp = None

from definedge_api import DefinedgeClient

st.set_page_config(layout="centered")
st.title("🔐 Login — Definedge")

# -----------------------
# Helpers
# -----------------------
def extract_value(d: dict, candidates):
    if not isinstance(d, dict):
        return None
    low = {k.lower(): k for k in d.keys()}
    for key in candidates:
        k = key.lower()
        if k in low:
            return d.get(low[k])
    return None

def mask_secret(s: Optional[str], keep=4):
    if not s:
        return "—"
    s = str(s)
    if len(s) <= keep:
        return "*" * len(s)
    return f"{s[:keep]}{'*'*(len(s)-keep)}"

def safe_client():
    return DefinedgeClient(
        api_token=st.secrets["DEFINEDGE_API_TOKEN"],
        api_secret=st.secrets["DEFINEDGE_API_SECRET"]
    )

def set_session(client, session_key: str, susertoken: Optional[str] = None, uid: Optional[str] = None):
    client.set_session_key(session_key)
    st.session_state["api_session_key"] = session_key
    if susertoken:
        st.session_state["susertoken"] = susertoken
    if uid:
        st.session_state["uid"] = uid
    st.session_state["client"] = client

# -----------------------
# Config & secrets
# -----------------------
totp_secret = st.secrets.get("DEFINEDGE_TOTP_SECRET")
SHOW_DEBUG = st.checkbox("Developer debug (show API responses)", value=False)

# -----------------------
# Session status
# -----------------------
st.markdown("---")
st.subheader("Session status")

if st.session_state.get("api_session_key"):
    st.success("✅ Logged in")
    st.write("UID:", st.session_state.get("uid", "—"))
    st.write("Session key:", mask_secret(st.session_state.get("api_session_key")))
    if st.button("Logout"):
        for k in ["api_session_key", "susertoken", "uid", "client"]:
            st.session_state.pop(k, None)
        st.experimental_rerun()
else:
    st.info("Not logged in yet.")

st.markdown("---")

# -----------------------
# Login options
# -----------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("TOTP Login (automatic)")
    if st.button("Login with TOTP"):
        try:
            if not totp_secret:
                st.error("No TOTP secret available in secrets.toml")
            elif pyotp is None:
                st.error("Install pyotp to use TOTP login.")
            else:
                client = safe_client()
                s1 = client.auth_step1()
                if SHOW_DEBUG:
                    st.write("auth_step1:", s1)
                otp_token = extract_value(s1 or {}, ["otp_token", "otpToken", "request_token"])
                otp_code = pyotp.TOTP(totp_secret).now()
                s2 = client.auth_step2(otp_token or "", otp_code)
                if SHOW_DEBUG:
                    st.write("auth_step2:", s2)
                session_key = extract_value(s2, ["api_session_key", "apiSessionKey", "api_key"])
                susertoken = extract_value(s2, ["susertoken"])
                uid = extract_value(s2, ["uid", "actid", "user"])
                if session_key:
                    set_session(client, session_key, susertoken, uid)
                    st.success("✅ Logged in via TOTP.")
                else:
                    st.error("Login failed, no session key.")
        except Exception as e:
            st.error(f"TOTP login failed: {e}")
            if SHOW_DEBUG:
                st.text(traceback.format_exc())

with col2:
    st.subheader("Manual OTP (SMS)")
    if st.button("Request OTP"):
        try:
            client = safe_client()
            r = client.auth_step1()
            st.session_state["last_auth_step1"] = r
            st.success("OTP requested. Check your SMS.")
            if SHOW_DEBUG:
                st.write("auth_step1:", r)
        except Exception as e:
            st.error(f"OTP request failed: {e}")
            if SHOW_DEBUG:
                st.text(traceback.format_exc())

    otp = st.text_input("Paste SMS OTP", key="otp_input")
    if st.button("Complete OTP login"):
        try:
            client = safe_client()
            otp_token = None
            if st.session_state.get("last_auth_step1"):
                otp_token = extract_value(st.session_state["last_auth_step1"], ["otp_token", "otpToken", "request_token"])
            if not otp_token:
                s1 = client.auth_step1()
                otp_token = extract_value(s1, ["otp_token", "otpToken", "request_token"])
            s2 = client.auth_step2(otp_token or "", otp)
            if SHOW_DEBUG:
                st.write("auth_step2:", s2)
            session_key = extract_value(s2, ["api_session_key", "apiSessionKey", "api_key"])
            susertoken = extract_value(s2, ["susertoken"])
            uid = extract_value(s2, ["uid", "actid", "user"])
            if session_key:
                set_session(client, session_key, susertoken, uid)
                st.success("✅ Logged in via SMS OTP.")
            else:
                st.error("Login failed, no session key.")
        except Exception as e:
            st.error(f"OTP login failed: {e}")
            if SHOW_DEBUG:
                st.text(traceback.format_exc())
