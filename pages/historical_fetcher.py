import requests
import zipfile
import io
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st

# ------------------ CONFIG ------------------
BASE_FILES = "https://app.definedgesecurities.com/public"
BASE_DATA = "https://data.definedgesecurities.com/sds"
MASTER_FILE = "nsecash.zip"

# आप जो indexes चाहते हो
TARGET_INDEXES = ["NIFTY 50", "NIFTY 500", "NIFTY MIDSML 400"]

# ------------------ HELPERS ------------------

def download_master(segment_zip: str) -> pd.DataFrame:
    """Download & extract master file from Definedge"""
    url = f"{BASE_FILES}/{segment_zip}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = z.namelist()[0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f)
    return df

def get_token(df: pd.DataFrame, company_name: str) -> str:
    """Get token of given index/company from master"""
    row = df[df["COMPANY"].str.upper() == company_name.upper()]
    if row.empty:
        raise ValueError(f"❌ Token not found for {company_name}")
    return str(row.iloc[0]["TOKEN"])

def fetch_history(session_key: str, segment: str, token: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
    """Fetch historical OHLCV from Definedge"""
    url = f"{BASE_DATA}/history/{segment}/{token}/{timeframe}/{start}/{end}"
    headers = {"Authorization": session_key}
    r = requests.get(url, headers=headers, timeout=60)
    r.raise_for_status()
    
    # Convert CSV (no header) to DataFrame
    df = pd.read_csv(io.StringIO(r.text), header=None)
    df.columns = ["Datetime", "Open", "High", "Low", "Close", "Volume", "OI"]
    df["Datetime"] = pd.to_datetime(df["Datetime"], format="%d-%m-%Y %H:%M:%S")
    return df

# ------------------ MAIN ------------------

def main():
    # Step 0: Session key from Streamlit session
    session_key = st.session_state.get("api_session_key")
    if not session_key:
        st.error("⚠️ API session key not found in session state. Please login first.")
        return

    # Step 1: Download NSE Cash master
    master_df = download_master(MASTER_FILE)

    # Step 2: Date range (last 1 year)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    frm = start_date.strftime("%d%m%Y0000")
    to = end_date.strftime("%d%m%Y1530")

    # Step 3: Fetch data for each index
    all_data = {}
    for index in TARGET_INDEXES:
        try:
            token = get_token(master_df, index)
            st.write(f"✅ Fetching {index} (Token: {token}) ...")
            df_hist = fetch_history(session_key, "NSE", token, "day", frm, to)
            all_data[index] = df_hist

            # Save to CSV
            csv_name = f"{index.replace(' ', '_')}.csv"
            df_hist.to_csv(csv_name, index=False)
            st.success(f"📂 Saved {csv_name}")
        except Exception as e:
            st.error(f"⚠️ Error for {index}: {e}")

    # Example: Show NIFTY 50 last 5 rows
    if "NIFTY 50" in all_data:
        st.dataframe(all_data["NIFTY 50"].tail())

if __name__ == "__main__":
    main()
