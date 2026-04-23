import requests

# Apna API URL
url = "https://integrate.definedgesecurities.com/dart/v1/placeorder"

# 1. Yahan apna aaj ka FRESH api_session_key paste karein (Jo login ke baad milta hai)
SESSION_KEY = "YAHAN_APNA_SESSION_KEY_PASTE_KAREIN" 

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {SESSION_KEY}"  # Bearer ke sath test
}

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

print("Order bhej rahe hain...")
response = requests.post(url, json=payload, headers=headers)
print("Server ka Jawab:", response.text)
