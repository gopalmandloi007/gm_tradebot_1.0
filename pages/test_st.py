import streamlit as st
import requests

st.set_page_config(layout="centered")
st.header("🧪 API Header Tester")

# Password field taaki aapki key screen par na dikhe
session_key = st.text_input("LlTDl91Z9TtA98GOiqzoHgP2qhc5BTuJX2z0AJObyUGPFki69FrWYHKU8dtrR1WXpVNoOTLubgU7+3WUxZRH33LJB/9ZBHSeg63lvQBs4G+y1k4OOSdkDA==:", type="password")

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
st.write("Test kijiye ki Definedge ko kaisa Header chahiye:")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Test 1")
    st.caption("Strict Doc Format (No Bearer)")
    if st.button("🚀 Run Test 1"):
        if not session_key:
            st.warning("Pehle upar Session Key paste karein!")
        else:
            headers = {
                "Content-Type": "application/json", 
                "Authorization": session_key.strip()
            }
            res = requests.post(url, json=payload, headers=headers)
            st.success(f"Status Code: {res.status_code}")
            st.json(res.json())

with col2:
    st.subheader("Test 2")
    st.caption("Cloud Format (With Bearer)")
    if st.button("🚀 Run Test 2"):
        if not session_key:
            st.warning("Pehle upar Session Key paste karein!")
        else:
            headers = {
                "Content-Type": "application/json", 
                "Authorization": f"Bearer {session_key.strip()}"
            }
            res = requests.post(url, json=payload, headers=headers)
            st.success(f"Status Code: {res.status_code}")
            st.json(res.json())
