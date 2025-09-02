import requests
import zipfile
import io
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st
import os
import time

BASE_FILES = "https://app.definedgesecurities.com/public"
BASE_DATA = "https://data.definedgesecurities.com/sds"
MASTER_FILE = "allmaster.zip"

# Output folder for CSVs
OUTPUT_FOLDER = "nse_historical_data"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ------------------ HELPERS ------------------

def download_master_all(segment_zip: str) -> pd.DataFrame:
    """Download & extract allmaster zip"""
    url = f"{BASE_FILES}/{segment_zip}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = z.namelist()[0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f, header=None)
            df.columns = ["SEGMENT","TOKEN","SYMBOL","TRADINGSYM","INSTRUMENT","EXPIRY",
                          "TICKSIZE","LOTSIZE","OPTIONTYPE","STRIKE","PRICEPREC","MULTIPLIER",
                          "ISIN","PRICEMULT","COMPANY"]
    return df

def fetch_history(session_key: str, segment: str, token: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
    """Fetch historical OHLCV from Definedge"""
    url = f"{BASE_DATA}/history/{segment}/{token}/{timeframe}/{start}/{end}"
    headers = {"Authorization": session_key}
    r = requests.get(url, headers=headers, timeout=120)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), header=None)
    df.columns = ["Datetime", "Open", "High", "Low", "Close", "Volume", "OI"]
    df["Datetime"] = pd.to_datetime(df["Datetime"], format="%d-%m-%Y %H:%M:%S")
    return df

# ------------------ MAIN ------------------

def main():
    session_key = st.session_state.get("api_session_key")
    if not session_key:
        st.error("⚠️ API session key not found in session state. Please login first.")
        return

    st.info("📥 Downloading master file...")
    master_df = download_master_all(MASTER_FILE)
    st.success(f"✅ Master file loaded, total rows: {len(master_df)}")

    # Filter only NSE segment
    nse_df = master_df[master_df["SEGMENT"].str.upper() == "NSE"]
    st.write(f"Total NSE rows: {len(nse_df)}")

    # Date range last 1 year
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    frm = start_date.strftime("%d%m%Y0000")
    to = end_date.strftime("%d%m%Y1530")

    total = len(nse_df)
    st.write(f"📊 Fetching historical data for {total} symbols...")

    for idx, row in nse_df.iterrows():
        symbol = row["SYMBOL"]
        token = str(row["TOKEN"])
        try:
            st.write(f"⏳ Fetching {symbol} ({idx+1}/{total})...")
            df_hist = fetch_history(session_key, "NSE", token, "day", frm, to)
            csv_name = os.path.join(OUTPUT_FOLDER, f"{symbol}.csv")
            df_hist.to_csv(csv_name, index=False)
            st.success(f"Saved {symbol}.csv")
            time.sleep(0.2)  # small delay to avoid API rate limits
        except Exception as e:
            st.error(f"⚠️ Error for {symbol}: {e}")
            continue

    st.success("🎉 All NSE historical data fetching completed!")

if __name__ == "__main__":
    main()
