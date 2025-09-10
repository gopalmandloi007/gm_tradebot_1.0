import streamlit as st
import pandas as pd
import requests
import json
import traceback

st.set_page_config(layout="wide")
st.title("📊 NSE Holdings Dashboard — Debug Mode")

# -------------------- API call --------------------
def fetch_holdings():
    try:
        url = "https://api.kite.trade/portfolio/holdings"  # example endpoint
        headers = {"Authorization": "token your_api_key:your_access_token"}
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            st.error(f"❌ API error {resp.status_code}: {resp.text}")
            return []
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        st.error(f"⚠️ Exception while fetching holdings: {e}")
        st.text(traceback.format_exc())
        return []

# Fetch holdings first
holdings = fetch_holdings()

# ------------------ DEBUG MODE: Inspect raw API response ------------------
if holdings:
    st.subheader("🔎 Raw Holdings Response (first 2 items)")
    st.text(json.dumps(holdings[:2], indent=2))
else:
    st.warning("⚠️ No holdings returned from API.")

# ------------------ Convert API to rows (no aggregation yet) ------------------
rows = []

for item in holdings:
    avg_buy_price = float(item.get('avg_buy_price') or 0)
    dp_qty = float(item.get('dp_qty') or 0)
    t1_qty = float(item.get('t1_qty') or 0)
    holding_used = float(item.get('holding_used') or 0)
    total_qty = int(round(dp_qty + t1_qty + holding_used))

    tradings = item.get('tradingsymbol') or item.get('tradings') or []
    symbols = []

    if isinstance(tradings, str):
        symbols = [{'symbol': tradings, 'token': item.get('token')}]
    elif isinstance(tradings, dict):
        symbols = [{'symbol': tradings.get('tradingsymbol') or tradings.get('symbol'),
                    'token': tradings.get('token') or item.get('token')}]
    elif isinstance(tradings, (list, tuple)):
        for sym in tradings:
            if isinstance(sym, dict):
                symbols.append({'symbol': sym.get('tradingsymbol') or sym.get('symbol'),
                                'token': sym.get('token') or item.get('token')})
            else:
                symbols.append({'symbol': str(sym), 'token': item.get('token')})

    if not symbols and item.get('tradingsymbol'):
        symbols = [{'symbol': item.get('tradingsymbol'), 'token': item.get('token')}]

    for s in symbols:
        rows.append({
            'symbol': s['symbol'],
            'token': s['token'],
            'avg_buy_price': avg_buy_price,
            'quantity': total_qty,
            'product_type': item.get('product_type', '')
        })

df_debug = pd.DataFrame(rows)

st.subheader("📝 Parsed Rows (before aggregation)")
st.dataframe(df_debug)

# Optional: allow CSV download of raw parsed rows
if not df_debug.empty:
    st.download_button(
        "⬇️ Download Parsed Rows (CSV)",
        data=df_debug.to_csv(index=False),
        file_name="parsed_holdings_debug.csv",
        mime="text/csv"
    )
