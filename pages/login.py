# pages/login.py
import streamlit as st
import traceback
from datetime import datetime
from typing import Optional

# optional import
try:
    import pyotp
except Exception:
    pyotp = None

# Import your Definedge client class (adjust import path if needed)
from definedge_api import DefinedgeClient

st.set_page_config(layout="centered")
st.title("🔐 Login — Definedge")

# -----------------------
# Helpers
# -----------------------
def extract_value(d: dict, candidates):
    """Return first non-empty value from dict for keys in candidates (case-insensitive)."""
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

def safe_client(api_token, api_secret):
    """Create DefinedgeClient and return it. Raise on error."""
    return DefinedgeClient(api_token=api_token, api_secret=api_secret)

def set_session(client, session_key: str, susertoken: Optional[str] = None, uid: Optional[str] = None):
    """Set client session and store into st.session_state."""
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
# Prefer values from secrets.toml but allow overrides in UI
secrets_api_token = st.secrets.get("DEFINEDGE_API_TOKEN")
secrets_api_secret = st.secrets.get("DEFINEDGE_API_SECRET")
secrets_totp = st.secrets.get("DEFINEDGE_TOTP_SECRET")

st.info("This page uses `.streamlit/secrets.toml` by default. You can override below if needed.")

with st.form("creds_form", clear_on_submit=False):
    col_a, col_b = st.columns(2)
    with col_a:
        api_token = st.text_input("API Token", value=secrets_api_token or "", placeholder="DEFINEDGE_API_TOKEN")
    with col_b:
        api_secret = st.text_input("API Secret", value=secrets_api_secret or "", placeholder="DEFINEDGE_API_SECRET", type="password")

    use_totp_secret = st.checkbox("Use TOTP secret from secrets.toml", value=bool(secrets_totp))
    if use_totp_secret:
        totp_secret = secrets_totp or ""
        if not totp_secret:
            st.warning("TOTP secret selected but not present in secrets. You can paste it manually below.")
            totp_secret = st.text_input("TOTP Secret (manual)", value="", type="password", key="manual_totp")
        else:
            st.markdown("Using TOTP secret from `.streamlit/secrets.toml`.")
    else:
        totp_secret = st.text_input("TOTP Secret (manual, optional)", value="", type="password", key="manual_totp2")

    submitted_creds = st.form_submit_button("Save / Use credentials (in-session)")

if submitted_creds:
    # store in session_state for this app run
    st.session_state["api_token"] = api_token.strip()
    st.session_state["api_secret"] = api_secret.strip()
    st.session_state["totp_secret"] = totp_secret.strip()
    st.success("Credentials saved to session for this browser tab.")

# allow falling back to previously saved session values
api_token = st.session_state.get("api_token", api_token)
api_secret = st.session_state.get("api_secret", api_secret)
totp_secret = st.session_state.get("totp_secret", totp_secret)

SHOW_DEBUG = st.checkbox("Show debug responses & tracebacks", value=False)

# -----------------------
# Quick status & direct session key option
# -----------------------
st.markdown("---")
st.subheader("Session status")

if st.session_state.get("api_session_key"):
    st.success("✅ Logged in")
    st.write("UID:", st.session_state.get("uid", "—"))
    st.write("Session key:", mask_secret(st.session_state.get("api_session_key")))
    if st.button("Logout"):
        # clear relevant keys
        for k in ["api_session_key", "susertoken", "uid", "client", "api_token", "api_secret", "totp_secret"]:
            if k in st.session_state:
                del st.session_state[k]
        st.experimental_rerun()
else:
    st.info("Not logged in.")

st.markdown("---")

# -----------------------
# TOTP automatic login (left) and Manual SMS flow (right)
# -----------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("Login with TOTP (automatic)")
    st.write("Uses TOTP secret to generate code and complete auth_step2 automatically.")
    if st.button("Login with TOTP"):
        try:
            if not api_token or not api_secret:
                st.error("Provide API token & secret (above) before logging in.")
            else:
                client = safe_client(api_token, api_secret)
                # Step 1: request OTP token
                s1 = client.auth_step1()
                if SHOW_DEBUG:
                    st.write("auth_step1 response:", s1)
                otp_token = extract_value(s1 or {}, ["otp_token", "otpToken", "request_token", "requestToken"])
                # Generate TOTP
                if not totp_secret:
                    st.error("No TOTP secret available. Use Manual OTP flow or provide TOTP secret.")
                else:
                    if pyotp is None:
                        st.error("pyotp not installed. Install pyotp to use TOTP login.")
                    else:
                        otp_code = pyotp.TOTP(totp_secret).now()
                        s2 = client.auth_step2(otp_token or "", otp_code)
                        if SHOW_DEBUG:
                            st.write("auth_step2 response:", s2)
                        session_key = extract_value(s2 or {}, ["api_session_key", "apiSessionKey", "api_key", "apiKey", "session_key"])
                        susertoken = extract_value(s2 or {}, ["susertoken", "s_user_token", "sUserToken", "susertoken"])
                        uid = extract_value(s2 or {}, ["uid", "actid", "user", "user_id"])
                        if not session_key:
                            st.error(f"Login failed — no session key in response. Response: {s2}")
                            if SHOW_DEBUG:
                                st.write(s2)
                        else:
                            set_session(client, session_key, susertoken, uid)
                            st.success("✅ Logged in via TOTP.")
        except Exception as e:
            st.error(f"TOTP login failed: {e}")
            if SHOW_DEBUG:
                st.text(traceback.format_exc())

with col2:
    st.subheader("Manual OTP (SMS) flow")
    st.write("Request OTP to be sent via SMS (auth_step1), then paste it below to complete login.")
    if st.button("Request OTP (auth_step1)"):
        try:
            if not api_token or not api_secret:
                st.error("Provide API token & secret (above) before requesting OTP.")
            else:
                client_req = safe_client(api_token, api_secret)
                r = client_req.auth_step1()
                st.session_state["last_auth_step1"] = r  # keep for reference
                st.success("OTP requested. Check SMS on your registered mobile.")
                if SHOW_DEBUG:
                    st.write("auth_step1 response (saved in session_state['last_auth_step1']):", r)
        except Exception as e:
            st.error(f"Request OTP failed: {e}")
            if SHOW_DEBUG:
                st.text(traceback.format_exc())

    otp_token_from_step1 = None
    if st.session_state.get("last_auth_step1"):
        otp_token_from_step1 = extract_value(st.session_state["last_auth_step1"], ["otp_token", "otpToken", "request_token", "requestToken"])
        if SHOW_DEBUG:
            st.write("Extracted otp_token from saved step1:", otp_token_from_step1)

    otp_input = st.text_input("Paste OTP received (SMS)", key="otp_input")
    if st.button("Complete OTP login"):
        try:
            if not api_token or not api_secret:
                st.error("Provide API token & secret (above) before completing OTP.")
            else:
                client2 = safe_client(api_token, api_secret)
                # if we have otp_token from previous step, use it, otherwise call auth_step1 again to get token
                otp_token = otp_token_from_step1
                if not otp_token:
                    s1 = client2.auth_step1()
                    otp_token = extract_value(s1 or {}, ["otp_token", "otpToken", "request_token", "requestToken"])
                    if SHOW_DEBUG:
                        st.write("auth_step1 automatic (for otp_token):", s1)

                s2 = client2.auth_step2(otp_token or "", otp_input or "")
                if SHOW_DEBUG:
                    st.write("auth_step2 response:", s2)
                session_key = extract_value(s2 or {}, ["api_session_key", "apiSessionKey", "api_key", "apiKey", "session_key"])
                susertoken = extract_value(s2 or {}, ["susertoken", "s_user_token", "sUserToken", "susertoken"])
                uid = extract_value(s2 or {}, ["uid", "actid", "user", "user_id"])
                if not session_key:
                    st.error(f"Login failed — no session key in response. Response: {s2}")
                    if SHOW_DEBUG:
                        st.write(s2)
                else:
                    set_session(client2, session_key, susertoken, uid)
                    st.success("✅ Logged in via OTP (SMS).")
        except Exception as e:
            st.error(f"OTP login failed: {e}")
            if SHOW_DEBUG:
                st.text(traceback.format_exc())

st.markdown("---")

# -----------------------
# Developer / Debug helpers
# -----------------------
st.subheader("Developer / Quick options")

col_a, col_b = st.columns([2, 1])
with col_a:
    pasted_key = st.text_input("Paste api_session_key (direct login/quick test)", key="paste_session")
    if st.button("Use pasted session key"):
        try:
            if not api_token or not api_secret:
                st.warning("Storing session key without client credentials may limit calls. Provide API token & secret first.")
            client_direct = safe_client(api_token or "", api_secret or "")
            sk = pasted_key.strip()
            if not sk:
                st.error("Paste a non-empty session key.")
            else:
                set_session(client_direct, sk, susertoken=None, uid=None)
                st.success("Session key stored in session_state and client.set_session_key called.")
        except Exception as e:
            st.error(f"Failed to set pasted session key: {e}")
            if SHOW_DEBUG:
                st.text(traceback.format_exc())

with col_b:
    if st.button("Clear saved credentials (session only)"):
        for k in ["api_token", "api_secret", "totp_secret", "last_auth_step1"]:
            if k in st.session_state:
                del st.session_state[k]
        st.success("Session-stored credentials cleared.")

st.markdown("---")
st.caption("If you still face login issues: enable debug, attempt auth_step1 and inspect the saved response shown above.")
