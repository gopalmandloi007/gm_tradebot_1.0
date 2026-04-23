import streamlit as st
import requests

st.set_page_config(layout="centered")
st.header("🧪 The Ultimate API Tester")

st.markdown("Pehle apni teeno keys yahan paste karein:")
session_key = st.text_input("1. Session Key (Aaj ka lamba wala token)", type="password")
api_token = st.text_input("2. API Token (Jo secrets.toml mein DEFINEDGE_API_TOKEN hai)", type="password")
uid = st.text_input("3. Client ID / UID (Aapka Definedge login ID)")

payload = {
    "exchange": "NSE",
    "tradingsymbol": "RVNL-EQ",
    "order_type": "BUY",
    "price": "498.85",
    "price_type": "LIMIT",
    "product_type": "CNC",
    "quantity": "1",
    "validity": "DAY",
    "algo_id": "99999"
}

url = "https://integrate.definedgesecurities.com/dart/v1/placeorder"

st.write("---")

if st.button("🚀 Fire All Tests!"):
    if not session_key or not api_token or not uid:
        st.error("Kripya teeno box bharein!")
    else:
        # Test 1: Header with App API Key
        st.subheader("Test 1: App API Key in Headers")
        headers_1 = {
            "Content-Type": "application/json", 
            "Authorization": session_key.strip(),
            "api_key": api_token.strip(),
            "apikey": api_token.strip(),
            "api-key": api_token.strip()
        }
        res_1 = requests.post(url, json=payload, headers=headers_1)
        st.json(res_1.json())

        # Test 2: App API Key + Bearer
        st.subheader("Test 2: App API Key + Bearer")
        headers_2 = {
            "Content-Type": "application/json", 
            "Authorization": f"Bearer {session_key.strip()}",
            "api_key": api_token.strip(),
            "apikey": api_token.strip(),
            "api-key": api_token.strip()
        }
        res_2 = requests.post(url, json=payload, headers=headers_2)
        st.json(res_2.json())

        # Test 3: API Key + UID inside Headers
        st.subheader("Test 3: App API Key + UID in Headers")
        headers_3 = headers_1.copy()
        headers_3["uid"] = uid.strip()
        headers_3["user"] = uid.strip()
        res_3 = requests.post(url, json=payload, headers=headers_3)
        st.json(res_3.json())
