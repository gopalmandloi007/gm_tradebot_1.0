import requests
import io
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st
import os

BASE_DATA = "https://data.definedgesecurities.com/sds"
OUTPUT_FOLDER = "nse_historical_data"
TIMEFRAME = "day"
MAX_RETRIES = 2
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Sample symbols (replace with actual token from master file)
TEST_SYMBOLS = {
    "ZYDUSWELL": "17635",
    "ZYDUSLIFE": "7929",
    "NIFTY50": "26000"
}

# Last 1 year
end_date = datetime.now()
start_date = end_date - timedelta(days=365)
frm = start_date.strftime("%d%m%Y0000")
to = end_date.strftime("%d%m%Y1530")

def fetch_history(session_key, segment, token, frm, to):
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

            # Convert Datetime to clear YYYY-MM-DD
            # If only time is coming, assign full dates
            try:
                df["Datetime"] = pd.to_datetime(df["Datetime"], dayfirst=True, errors="coerce")
            except:
                df["Datetime"] = pd.date_range(start=start_date, periods=len(df), freq='D')

            return df
        except Exception as e:
            st.warning(f"Attempt {attempt} failed for {token}: {e}")
            import time; time.sleep(2)
    raise ValueError(f"Failed to fetch data for token {token} after {MAX_RETRIES} retries")

# ------------------ MAIN ------------------
def main():
    session_key = st.session_state.get("api_session_key")
    if not session_key:
        st.error("⚠️ API session key not found. Login first.")
        return

    st.write(f"📊 Fetching sample historical data for {len(TEST_SYMBOLS)} symbols...")
    for symbol, token in TEST_SYMBOLS.items():
        try:
            df_hist = fetch_history(session_key, "NSE", token, frm, to)
            csv_name = os.path.join(OUTPUT_FOLDER, f"{symbol}_sample.csv")
            df_hist.to_csv(csv_name, index=False)
            st.write(f"✅ {symbol} saved")
            st.dataframe(df_hist.head(10))
        except Exception as e:
            st.write(f"⚠️ {symbol} error: {e}")

    st.success("🎉 Sample fetch completed!")

if __name__ == "__main__":
    main()
