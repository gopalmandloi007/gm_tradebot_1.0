# pages/login.py
import streamlit as st
import pyotp
from definedge_api import DefinedgeClient
import traceback

def show():
    st.header("🔐 Login — Definedge")
    st.write("App uses `.streamlit/secrets.toml` for API token/secret and optional TOTP secret.")

    api_token = st.secrets.get("DEFINEDGE_API_TOKEN")
    api_secret = st.secrets.get("DEFINEDGE_API_SECRET")
    totp_secret = st.secrets.get("DEFINEDGE_TOTP_SECRET")

    if not api_token or not api_secret:
        st.error("Add DEFINEDGE_API_TOKEN and DEFINEDGE_API_SECRET to .streamlit/secrets.toml")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Login with TOTP (automatic)")
        if st.button("Login (TOTP)"):
            try:
                client = DefinedgeClient(api_token=api_token, api_secret=api_secret)
                # Step1
                s1 = client.auth_step1()
                otp_token = None
                if isinstance(s1, dict):
                    for k in ("otp_token","otpToken","request_token"):
                        if k in s1:
                            otp_token = s1.get(k)
                            break
                # generate TOTP
                if not totp_secret:
                    st.error("No TOTP secret found in secrets. Use manual OTP option.")
                else:
                    otp_code = pyotp.TOTP(totp_secret).now()
                    s2 = client.auth_step2(otp_token or "", otp_code)
                    # extract api_session_key
                    api_session_key = s2.get("api_session_key") or s2.get("apiSessionKey") or s2.get("api_key") or s2.get("apiKey")
                    susertoken = s2.get("susertoken") or s2.get("susertoken")
                    uid = s2.get("uid") or s2.get("actid") or s2.get("user")
                    if not api_session_key:
                        st.error(f"Login failed — no api_session_key returned. Response: {s2}")
                    else:
                        st.session_state["api_session_key"] = api_session_key
                        st.session_state["susertoken"] = susertoken
                        st.session_state["uid"] = uid
                        client.set_session_key(api_session_key)
                        st.session_state["client"] = client
                        st.success("✅ Logged in (TOTP).")
            except Exception as e:
                st.error(f"Login failed: {e}")
                st.text(traceback.format_exc())

    with col2:
        st.subheader("Manual OTP (SMS) flow")
        if st.button("Request OTP (auth_step1)"):
            try:
                c = DefinedgeClient(api_token=api_token, api_secret=api_secret)
                r = c.auth_step1()
                st.write("Step1 response (server):")
                st.json(r)
                st.success("OTP requested. Check SMS.")
            except Exception as e:
                st.error(f"Request OTP failed: {e}")
        otp = st.text_input("Paste OTP received (SMS)", key="otp_input")
        if st.button("Complete OTP login"):
            try:
                c = DefinedgeClient(api_token=api_token, api_secret=api_secret)
                # we need otp_token possibly from previous step; if not available, pass empty
                # For simplicity, call auth_step1 again to get otp_token
                s1 = c.auth_step1()
                otp_token = None
                if isinstance(s1, dict):
                    for k in ("otp_token","otpToken","request_token"):
                        if k in s1:
                            otp_token = s1.get(k)
                            break
                resp = c.auth_step2(otp_token or "", otp)
                api_session_key = resp.get("api_session_key") or resp.get("apiSessionKey") or resp.get("api_key") or resp.get("apiKey")
                susertoken = resp.get("susertoken")
                uid = resp.get("uid") or resp.get("actid")
                if not api_session_key:
                    st.error(f"Login failed — response did not contain api_session_key: {resp}")
                else:
                    st.session_state["api_session_key"] = api_session_key
                    st.session_state["susertoken"] = susertoken
                    st.session_state["uid"] = uid
                    c.set_session_key(api_session_key)
                    st.session_state["client"] = c
                    st.success("✅ Logged in (OTP).")
            except Exception as e:
                st.error(f"OTP login failed: {e}")
                st.text(traceback.format_exc())

    # show status
    st.markdown("---")
    st.subheader("Session status")
    if st.session_state.get("api_session_key"):
        st.write("UID:", st.session_state.get("uid"))
        st.write("Session key present.")
    else:
        st.info("Not logged in yet.")
