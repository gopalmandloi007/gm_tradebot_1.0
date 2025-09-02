import requests
import io
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import zipfile
import time

# ------------------ SETTINGS ------------------
BASE_FILES = "https://app.definedgesecurities.com/public"
BASE_DATA = "https://data.definedgesecurities.com/sds"
MASTER_FILE = "allmaster.zip"
OUTPUT_FOLDER = "nse_historical_data"
MAX_THREADS = 10
TIMEFRAME = "day"
MAX_RETRIES = 2

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ------------------ HELPERS ------------------

def download_master() -> pd.DataFrame:
    url = f"{BASE_FILES}/{MASTER_FILE}"
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
            df["Datetime"] = pd.to_datetime(df["Datetime"], dayfirst=True, errors="coerce")
            return df
        except Exception as e:
            st.warning(f"Attempt {attempt} failed for {token}: {e}")
            time.sleep(2)
    raise ValueError(f"Failed to fetch data for token {token} after {MAX_RETRIES} retries")

def fetch_and_save(symbol: str, token: str, session_key: str, frm: str, to: str):
    df_hist = fetch_history(session_key, "NSE", token, frm, to)
    csv_name = os.path.join(OUTPUT_FOLDER, f"{symbol}.csv")
    df_hist.to_csv(csv_name, index=False)
    return f"✅ {symbol} saved"

# ------------------ MAIN ------------------

def main():
    session_key = st.session_state.get("api_session_key")
    if not session_key:
        st.error("⚠️ API session key not found. Login first.")
        return

    st.info("📥 Downloading master file...")
    master_df = download_master()
    st.success(f"✅ Master file loaded, total rows: {len(master_df)}")

    # Filter NSE equity stocks + indices (~2500+)
    nse_df = master_df[
        (master_df["SEGMENT"].str.upper() == "NSE") &
        (master_df["INSTRUMENT"].isin(["EQ", "IDX"]))
    ]
    st.write(f"Total NSE stocks + indices: {len(nse_df)}")

    # Date range last 1 year
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    frm = start_date.strftime("%d%m%Y0000")
    to = end_date.strftime("%d%m%Y1530")

    st.write(f"📊 Fetching historical data using {MAX_THREADS} threads...")
    progress_bar = st.progress(0)
    messages_placeholder = st.empty()
    messages = []

    # Multi-threaded fetch
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
                messages_placeholder.text("\n".join(messages[-20:]))
            except Exception as e:
                messages.append(f"⚠️ {symbol} error: {e}")
                messages_placeholder.text("\n".join(messages[-20:]))
            progress_bar.progress(i / len(nse_df))

    st.success("🎉 All NSE historical data fetched!")

    # ------------------ ZIP Download ------------------
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for root, _, files in os.walk(OUTPUT_FOLDER):
            for file in files:
                zipf.write(os.path.join(root, file), arcname=file)
    zip_buffer.seek(0)
    st.download_button(
        label="⬇️ Download all CSVs as ZIP",
        data=zip_buffer,
        file_name="NSE_Historical_Data.zip",
        mime="application/zip"
    )

if __name__ == "__main__":
    main()
