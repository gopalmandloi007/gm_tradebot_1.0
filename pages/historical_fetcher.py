import requests
import zipfile
import io
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st

BASE_FILES = "https://app.definedgesecurities.com/public"
BASE_DATA = "https://data.definedgesecurities.com/sds"
MASTER_FILE = "nsecash.zip"

# Index name mapping to SYMBOL in master file
TARGET_INDEXES = {
    "NIFTY 50": "NIFTY",
    "NIFTY 500": "NIFTY500",
    "NIFTY MIDSML 400": "NIFTYMIDSMALL"
}

# ------------------ HELPERS ------------------

def download_master(segment_zip: str) -> pd.DataFrame:
    url = f"{BASE_FILES}/{segment_zip}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = z.namelist()[0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f, header=None)
            df.columns = ["SEGMENT","TOKEN","SYMBOL","TRADINGSYM","INSTRUMENT","EXPIRY",
                          "TICKSIZE","LOTSIZE","OPTIONTYPE","STRIKE","PRICEPREC","MULTIPLIER",
                          "ISIN","PRICEMULT","COMPANY"]
    return df

def get_token_by_symbol(df: pd.DataFrame, symbol: str) -> str:
    df_nse = df[df["SEGMENT"].str.upper() == "NSE"]
    row = df_nse[df_nse["SYMBOL"].str.upper() == symbol.upper()]
    if row.empty:
        raise ValueError(f"❌ Token not found for {symbol}")
    return str(row.iloc[0]["TOKEN"])

def fetch_history(session_key: str, segment: str, token: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
    url = f"{BASE_DATA}/history/{segment}/{token}/{timeframe}/{start}/{end}"
    headers = {"Authorization": session_key}
    r = requests.get(url, headers=headers, timeout=60)
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

    master_df = download_master(MASTER_FILE)
    st.write("✅ Master file loaded, total rows:", len(master_df))

    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    frm = start_date.strftime("%d%m%Y0000")
    to = end_date.strftime("%d%m%Y1530")

    all_data = {}
    for index_name, symbol in TARGET_INDEXES.items():
        try:
            token = get_token_by_symbol(master_df, symbol)
            st.write(f"✅ Fetching {index_name} (Symbol: {symbol}, Token: {token}) ...")
            df_hist = fetch_history(session_key, "NSE", token, "day", frm, to)
            all_data[index_name] = df_hist
            csv_name = f"{index_name.replace(' ', '_')}.csv"
            df_hist.to_csv(csv_name, index=False)
            st.success(f"📂 Saved {csv_name}")
        except Exception as e:
            st.error(f"⚠️ Error for {index_name}: {e}")

    if "NIFTY 50" in all_data:
        st.dataframe(all_data["NIFTY 50"].tail())

if __name__ == "__main__":
    main()
