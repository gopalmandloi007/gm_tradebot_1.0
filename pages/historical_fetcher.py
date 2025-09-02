import requests
import io
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st
import os
import time

BASE_DATA = "https://data.definedgesecurities.com/sds"
OUTPUT_FOLDER = "nse_historical_data"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ------------------ SETTINGS ------------------
TIMEFRAME = "day"
MAX_RETRIES = 2
TEST_SYMBOLS = {
    "ZYDUSWELL": "17635",  # Example token from master
    "ZYDUSLIFE": "7929",    # Example token
    "ZUARIIND": "3827",     # Example token
    "ZUARI": "29050"        # Example token
}

# ------------------ HELPERS ------------------

def fetch_history(session_key: str, segment: str, token: str, frm: str, to: str) -> pd.DataFrame:
    url = f"{BASE_DATA}/history/{segment}/{token}/{TIMEFRAME}/{frm}/{to}"
    headers = {"Authorization": session_key}
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=headers, timeout=120)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text), header=None)
            # Dynamic columns
            if df.shape[1] == 6:
                df.columns = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
            elif df.shape[1] == 7:
                df.columns = ["Datetime", "Open", "High", "Low", "Close", "Volume", "OI"]
            else:
                raise ValueError(f"Unexpected columns: {df.shape[1]} for token {token}")
            df["Datetime"] = pd.to_datetime(df["Datetime"], format="%d-%m-%Y %H:%M:%S")
            return df
        except Exception as e:
            st.warning(f"Attempt {attempt} failed for {token}: {e}")
            time.sleep(2)
    raise ValueError(f"Failed to fetch data for token {token} after {MAX_RETRIES} retries")

# ------------------ MAIN ------------------

def main():
    session_key = st.session_state.get("api_session_key")
    if not session_key:
        st.error("⚠️ API session key not found. Login first.")
        return

    # Last 1 year
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    frm = start_date.strftime("%d%m%Y0000")
    to = end_date.strftime("%d%m%Y1530")

    st.write(f"📊 Test fetching historical data for {len(TEST_SYMBOLS)} symbols...")

    progress_bar = st.progress(0)
    messages_placeholder = st.empty()
    messages = []

    for i, (symbol, token) in enumerate(TEST_SYMBOLS.items(), 1):
        try:
            df_hist = fetch_history(session_key, "NSE", token, frm, to)
            csv_name = os.path.join(OUTPUT_FOLDER, f"{symbol}.csv")
            df_hist.to_csv(csv_name, index=False)
            msg = f"✅ {symbol} saved"
            messages.append(msg)
            messages_placeholder.text("\n".join(messages[-10:]))
        except Exception as e:
            msg = f"⚠️ {symbol} error: {e}"
            messages.append(msg)
            messages_placeholder.text("\n".join(messages[-10:]))

        progress_bar.progress(i / len(TEST_SYMBOLS))

    st.success("🎉 Test fetch completed!")

if __name__ == "__main__":
    main()
