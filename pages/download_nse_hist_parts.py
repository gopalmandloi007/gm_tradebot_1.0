# pages/download_nse_hist_parts.py
import streamlit as st
import pandas as pd
import numpy as np
import io
import zipfile
import requests
import os
import time
import traceback
from datetime import datetime, timedelta
from typing import List, Tuple

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks & Indices (Daily, Part-wise, Debug)")

# ----------------------
# Configuration
# ----------------------
MASTER_URL = "https://app.definedgesecurities.com/public/allmaster.zip"
MASTER_FILE_COLS = [
    "SEGMENT","TOKEN","SYMBOL","TRADINGSYM","INSTRUMENT","EXPIRY",
    "TICKSIZE","LOTSIZE","OPTIONTYPE","STRIKE","PRICEPREC","MULTIPLIER",
    "ISIN","PRICEMULT","COMPANY"
]
ALLOWED_SEGMENT = "NSE"
ALLOWED_INSTRUMENTS = {"EQ", "BE", "SM", "IDX"}

# ensure session caches exist
if "_hist_cache" not in st.session_state:
    st.session_state["_hist_cache"] = {}   # key -> bytes (csv)
if "_zip_cache" not in st.session_state:
    st.session_state["_zip_cache"] = {}    # key -> bytes (zip)

# ----------------------
# Helpers
# ----------------------
@st.cache_data(show_spinner=True)
def download_master_df() -> pd.DataFrame:
    r = requests.get(MASTER_URL, timeout=30)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = [n for n in z.namelist() if n.lower().endswith('.csv')][0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f, header=None, dtype=str)
    if df.shape[1] >= len(MASTER_FILE_COLS):
        df.columns = MASTER_FILE_COLS + [f"EXTRA_{i}" for i in range(df.shape[1]-len(MASTER_FILE_COLS))]
    else:
        df.columns = MASTER_FILE_COLS[:df.shape[1]]
    return df

def parse_definedge_csv_text(csv_text: str) -> pd.DataFrame:
    if not csv_text or not csv_text.strip():
        return pd.DataFrame()
    try:
        df = pd.read_csv(io.StringIO(csv_text), header=None, dtype=str)
        if df.shape[1] >= 6:
            colmap = {0: "DateTime", 1: "Open", 2: "High", 3: "Low", 4: "Close", 5: "Volume"}
            df = df.rename(columns=colmap)
            keep_cols = [c for c in ["DateTime","Open","High","Low","Close","Volume"] if c in df.columns]
            df = df[keep_cols]
            return df
    except Exception:
        pass
    return pd.DataFrame()

def get_api_session_key_from_client(client) -> str:
    if client is None:
        return None
    for a in ["api_session_key","api_key","session_key","token"]:
        if hasattr(client, a):
            val = getattr(client, a)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None

# ----------------------
# Load & filter master
# ----------------------
with st.spinner("Downloading master…"):
    master_df = download_master_df()

df_seg = master_df[master_df["SEGMENT"].astype(str).str.upper() == ALLOWED_SEGMENT]
df_filtered = df_seg[df_seg["INSTRUMENT"].astype(str).str.upper().isin(ALLOWED_INSTRUMENTS)].copy()

st.write(f"Filtered rows: {len(df_filtered)}")

# ----------------------
# Controls
# ----------------------
days_back = st.number_input("Number of days back", min_value=30, max_value=3650, value=365)
client = st.session_state.get("client")
api_key = get_api_session_key_from_client(client)
if not api_key:
    api_key = st.text_input("Definedge API Session Key", type="password")

# ----------------------
# 🔎 Debug test call
# ----------------------
if api_key and not df_filtered.empty:
    test_row = df_filtered.iloc[0]
    token = str(test_row["TOKEN"])
    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=int(days_back))
    from_str = start_dt.strftime("%d%m%Y") + "0000"
    to_str = end_dt.strftime("%d%m%Y") + "1530"
    url = f"https://data.definedgesecurities.com/sds/history/NSE/{token}/day/{from_str}/{to_str}"
    headers = {"Authorization": api_key}

    st.subheader("🔎 Test API Call")
    st.code(f"URL: {url}\nHeaders: {headers}")
    try:
        resp = requests.get(url, headers=headers, timeout=25)
        st.write("Status:", resp.status_code)
        st.write("Response length:", len(resp.text))
        st.text(resp.text[:500])  # show first 500 chars
        df_test = parse_definedge_csv_text(resp.text)
        if not df_test.empty:
            st.success(f"Parsed {len(df_test)} rows")
            st.dataframe(df_test.head(10))
        else:
            st.error("Parsed DataFrame is empty ❌")
    except Exception as e:
        st.error(f"Error calling API: {e}")
