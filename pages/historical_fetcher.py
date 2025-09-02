import requests
import io
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st
import os
import zipfile
import time

# ------------------ SETTINGS ------------------
BASE_FILES = "https://app.definedgesecurities.com/public"
BASE_DATA = "https://data.definedgesecurities.com/sds"
MASTER_FILE = "allmaster.zip"
OUTPUT_FOLDER = "nse_historical_sample"
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
            r = requests.get(url, headers=headers, timeout=60)
            r.raise_for_status()
            if r.text.strip() == "":
                raise ValueError("Empty response")
            df = pd.read_csv(io.StringIO(r.text), header=None)
            # Dynamic columns
            if df.shape[1] == 6:
                df.columns = ["Datetime","Open","High","Low","Close","Volume"]
            elif df.shape[1] == 7:
                df.columns = ["Datetime","Open","High","Low","Close","Volume","OI"]
            # Clear datetime
            if df["Datetime"].str.contains(":").all():
                df["Datetime"] = pd.date_range(start=start_date, periods=len(df), freq='B')
            else:
                df["Datetime"] = pd.to_datetime(df["Datetime"], dayfirst=True, errors="coerce")
            return df
        except Exception as e:
            st.warning(f"Attempt {attempt} failed for token {token}: {e}")
            time.sleep(2)
    raise ValueError(f"Failed to fetch data for token {token} after {MAX_RETRIES} retries")

# ------------------ STREAMLIT APP ------------------
def main():
    session_key = st.session_state.get("api_session_key")
    if not session_key:
        st.error("⚠️ API session key not found. Login first.")
        return

    st.info("📥 Downloading master file...")
    master_df = download_master()
    st.success(f"✅ Master file loaded, total rows: {len(master_df)}")

    # Filter NSE EQ + IDX
    nse_df = master_df[
        (master_df["SEGMENT"].str.upper() == "NSE") &
        (master_df["INSTRUMENT"].isin(["EQ","IDX"]))
    ].reset_index(drop=True)

    st.write(f"Total NSE EQ + IDX symbols: {len(nse_df)}")

    # Date range last 1 year
    global end_date, start_date
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    frm = start_date.strftime("%d%m%Y0000")
    to = end_date.strftime("%d%m%Y1530")

    st.write("📊 Fetching sample daily OHLCV for first 3 working symbols...")

    fetched = 0
    for idx, row in nse_df.iterrows():
        symbol = row["SYMBOL"]
        token = str(row["TOKEN"])
        try:
            df_hist = fetch_history(session_key, "NSE", token, frm, to)
            csv_name = os.path.join(OUTPUT_FOLDER, f"{symbol}_sample.csv")
            df_hist.to_csv(csv_name, index=False)
            st.write(f"✅ {symbol} saved")
            st.dataframe(df_hist.head(10))
            fetched += 1
        except Exception as e:
            st.write(f"⚠️ {symbol} error: {e}")
        if fetched >= 3:
            break

    st.success("🎉 Sample fetch completed!")

if __name__ == "__main__":
    main()
