import sys

print("🚀 Script start ho chuki hai... Please wait.")

try:
    import requests
    print("✅ Requests module successfully loaded.")
except ImportError:
    print("❌ ERROR: 'requests' library install nahi hai! Terminal mein 'pip install requests' chalayein.")
    sys.exit()

url = "https://integrate.definedgesecurities.com/dart/v1/placeorder"

# Aapka session key (Maine .strip() laga diya hai taaki koi hidden space na jaye)
SESSION_KEY = "LlTDl91Z9TvPsWWpLYRNqdKvBWWSvqMpAmQRh14VQd8ci++UUt/UD5/+H9I0mUMurobUU1rCYi9FMmJ/m9R7tSdaQ4GEOHfUJydSbfuxRoX6vMA/jOIPUQ==".strip()

# API documentation ke hisaab se hum bina 'Bearer' ke test kar rahe hain pehle
headers = {
    "Content-Type": "application/json",
    "Authorization": SESSION_KEY  
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

print("📦 Payload set ho gaya hai. Server ko request bhej rahe hain...")

try:
    response = requests.post(url, json=payload, headers=headers, timeout=15)
    print("\n" + "="*50)
    print("📡 SERVER KA JAWAB (RESPONSE):")
    print(f"Status Code : {response.status_code}")
    print(f"Message     : {response.text}")
    print("="*50 + "\n")
except Exception as e:
    print(f"\n❌ SCRIPT CRASH HO GAYI! Error details: {e}\n")
