import requests
import zipfile
import io
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

BASE_FILES = "https://app.definedgesecurities.com/public"
BASE_DATA = "https://data.definedgesecurities.com/sds"
MASTER_FILE = "allmaster.zip"
OUTPUT_FOLDER = "nse_historical_data"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

MAX_THREADS = 10  # adjust threads based on your network

# ------------------ HELPERS ------------------

def download_master_all(segment_zip: str) -> pd.DataFrame:
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
    url = f"{BASE_DATA}/history/{segment}/{token}/{timeframe}/{start}/{end}"
    headers = {"Authorization": session_key}
    r = requests.get(url, headers=headers, timeout=120)
    r.raise_for_status()
    
    df = pd.read_csv(io.StringIO(r.text), header=None)
    if df.shape[1] == 6:
        df.columns = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
    elif df.shape[1] == 7:
        df.columns = ["Datetime", "Open", "High", "Low", "Close", "Volume", "OI"]
    else:
        raise ValueError(f"Unexpected number of columns: {df.shape[1]} for token {token}")
    
    df["Datetime"] = pd.to_datetime(df["Datetime"], format="%d-%m-%Y %H:%M:%S")
    return df

def fetch_and_save(symbol: str, token: str, session_key: str, frm: str, to: str):
    try:
        df_hist = fetch_history(session_key, "NSE", token, "day", frm, to)
        csv_name = os.path.join(OUTPUT_FOLDER, f"{symbol}.csv")
        df_hist.to_csv(csv_name, index=False)
        return f"✅ {symbol} saved"
    except Exception as e:
        return f"⚠️ {symbol} error: {e}"

# ------------------ MAIN ------------------

def main():
    session_key = st.session_state.get("api_session_key")
    if not session_key:
        st.error("⚠️ API session key not found. Login first.")
        return

    st.info("📥 Downloading master file...")
    master_df = download_master_all(MASTER_FILE)
    st.success(f"✅ Master file loaded, total rows: {len(master_df)}")

    # Filter NSE segment
    nse_df = master_df[master_df["SEGMENT"].str.upper() == "NSE"]
    st.write(f"Total NSE rows: {len(nse_df)}")

    # Date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    frm = start_date.strftime("%d%m%Y0000")
    to = end_date.strftime("%d%m%Y1530")

    st.write(f"📊 Fetching historical data for {len(nse_df)} symbols using {MAX_THREADS} threads...")

    results_placeholder = st.empty()

    # Multi-threaded fetch
    messages = []
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_symbol = {
            executor.submit(fetch_and_save, row["SYMBOL"], str(row["TOKEN"]), session_key, frm, to): row["SYMBOL"]
            for idx, row in nse_df.iterrows()
        }
        for i, future in enumerate(as_completed(future_to_symbol), 1):
            symbol = future_to_symbol[future]
            try:
                msg = future.result()
                messages.append(msg)
                results_placeholder.text("\n".join(messages[-20:]))  # show last 20 messages
            except Exception as e:
                messages.append(f"⚠️ {symbol} error: {e}")
                results_placeholder.text("\n".join(messages[-20:]))

    st.success("🎉 All NSE historical data fetching completed!")

if __name__ == "__main__":
    main()
