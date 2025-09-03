import streamlit as st
import pandas as pd
import io
import zipfile
from datetime import datetime, timedelta
import re
import requests  # For API requests later

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks & Indices (5 Years)")

# -----------------------
# Robust parser (all-in-one)
# -----------------------
def _clean_dt_str(s: pd.Series) -> pd.Series:
    sc = s.astype(str).str.strip()
    sc = sc.str.replace(r'\.0+$', '', regex=True)
    sc = sc.str.replace(r'["\']', '', regex=True)
    sc = sc.str.replace(r'\s+', '', regex=True)
    return sc

def _looks_like_ddmmyyyy_hhmm(val: str) -> bool:
    return bool(re.fullmatch(r'\d{12}', val)) and 1 <= int(val[0:2]) <= 31

def _looks_like_ddmmyyyy(val: str) -> bool:
    return bool(re.fullmatch(r'\d{8}', val)) and 1 <= int(val[0:2]) <= 31

def _looks_like_epoch_seconds(val: str) -> bool:
    return bool(re.fullmatch(r'\d{10}', val))

def _looks_like_epoch_millis(val: str) -> bool:
    return bool(re.fullmatch(r'\d{13}', val))

def read_hist_csv_to_df(hist_csv: str) -> pd.DataFrame:
    if not hist_csv.strip():
        return pd.DataFrame()
    txt = hist_csv.strip()
    lines = txt.splitlines()
    if not lines:
        return pd.DataFrame()

    # auto-detect header
    first_line = lines[0].lower()
    header_indicators = ("date", "datetime", "open", "high", "low", "close", "volume", "oi", "timestamp")
    use_header = any(h in first_line for h in header_indicators)

    try:
        if use_header:
            df = pd.read_csv(io.StringIO(txt))
        else:
            df = pd.read_csv(io.StringIO(txt), header=None)
    except:
        return pd.DataFrame()

    # Map columns
    cols = [str(c).lower() for c in df.columns]
    col_map = {}
    for c in df.columns:
        lc = str(c).lower()
        if "date" in lc or "time" in lc:
            col_map[c] = "DateTime"
        elif lc.startswith("open"):
            col_map[c] = "Open"
        elif lc.startswith("high"):
            col_map[c] = "High"
        elif lc.startswith("low"):
            col_map[c] = "Low"
        elif lc.startswith("close"):
            col_map[c] = "Close"
        elif "volume" in lc:
            col_map[c] = "Volume"
        elif lc == "oi":
            col_map[c] = "OI"
    if col_map:
        df = df.rename(columns=col_map)
    else:
        if df.shape[1] >= 6:
            df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]

    # Clean DateTime
    series = _clean_dt_str(df["DateTime"])
    dt = pd.to_datetime(series, dayfirst=True, errors="coerce")
    df["DateTime"] = dt
    df = df.dropna(subset=["DateTime"])
    for col in ("Open", "High", "Low", "Close", "Volume", "OI"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Date"] = df["DateTime"].dt.normalize()
    df = df.sort_values("DateTime").drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)
    df["DateStr"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df[["DateTime", "Date", "DateStr", "Open", "High", "Low", "Close", "Volume"]]

# -----------------------
# Prepare OHLCV CSV
# -----------------------
def prepare_ohlcv_for_download(df: pd.DataFrame) -> pd.DataFrame:
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    cols_keep = ["Date", "Open", "High", "Low", "Close", "Volume"]
    return df[cols_keep].copy()

# -----------------------
# ZIP download
# -----------------------
def zip_csv_download(dfs: dict):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for symbol, df in dfs.items():
            df_clean = prepare_ohlcv_for_download(df)
            csv_bytes = df_clean.to_csv(index=False).encode("utf-8")
            zf.writestr(f"{symbol}_OHLCV.csv", csv_bytes)
    zip_buffer.seek(0)
    st.download_button(
        label="Download All 5-Year OHLCV CSVs (ZIP)",
        data=zip_buffer,
        file_name="NSE_5yr_OHLCV.zip",
        mime="application/zip"
    )

# -----------------------
# Load master
# -----------------------
@st.cache_data
def load_master(path="data/master/allmaster.csv"):
    # Corrected: load with header row if present
    return pd.read_csv(path, header=0)

try:
    df_master = load_master()
except Exception as e:
    st.error(f"Master CSV load failed: {e}")
    st.stop()

# Filter for NSE segment (Column 0)
nse_df = df_master[df_master[0].astype(str).str.upper() == "NSE"]

# Define desired instrument types
desired_instruments = ["EQ", "BE", "SM", "IDX"]

# Filter for instrument types (Column 4)
filtered_df = nse_df[nse_df[4].astype(str).str.upper().isin(desired_instruments)]

# Extract symbols (Column 2)
symbols = filtered_df[2].astype(str).unique().tolist()

# Count total symbols
total_symbols = len(symbols)

# Display info
st.info(f"Total NSE symbols with desired instruments: {total_symbols}")
st.write("Symbols:", symbols)

# -----------------------
# Prepare data for API request
# -----------------------

# Extract Segment and Token columns (Column 1 and 2)
segment_series = filtered_df[1].astype(str)
token_series = filtered_df[2].astype(str)

# Create a list of dictionaries for each symbol with required info
api_data_list = []

for idx, symbol in enumerate(symbols):
    segment = segment_series.iloc[idx]
    token = token_series.iloc[idx]
    api_data = {
        "symbol": symbol,
        "segment": segment,
        "token": token
    }
    api_data_list.append(api_data)

# Example: Display the first few entries
st.write("Sample data for API requests:", api_data_list[:5])

# -----------------------
# Example function to fetch historical data
# -----------------------
def fetch_historical_data(symbol, segment, token):
    # Replace with your actual API endpoint
    api_url = "https://api.example.com/historical"
    params = {
        "symbol": symbol,
        "segment": segment,
        "token": token,
    }
    try:
        response = requests.get(api_url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to fetch data for {symbol} with status code {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error fetching data for {symbol}: {e}")
        return None

# -----------------------
# Fetch 5-year historical data
# -----------------------
def fetch_historical_5yr(client, segment, token):
    today = datetime.today()
    frm = (today - timedelta(days=5*365 + 30)).strftime("%d%m%Y%H%M")
    to = today.strftime("%d%m%Y%H%M")
    try:
        raw = client.historical_csv(segment=segment, token=token, timeframe="day", frm=frm, to=to)
    except Exception as e:
        st.warning(f"Failed fetch for {token}: {e}")
        return pd.DataFrame()
    if not raw or not raw.strip():
        return pd.DataFrame()
    return read_hist_csv_to_df(raw)

# -----------------------
# Fetch all on button click
# -----------------------
if st.button("Fetch 5-Year OHLCV for All NSE Symbols"):
    client = st.session_state.get("client")
    if not client:
        st.error("Please login first.")
        st.stop()

    dfs_all = {}
    progress_text = st.empty()
    total = len(symbols)
    for i, sym in enumerate(symbols, 1):
        try:
            token_row = nse_df[nse_df[2] == sym].iloc[0]
            df_sym = fetch_historical_5yr(client, token_row[1], token_row[2])
            if not df_sym.empty:
                dfs_all[sym] = df_sym
            progress_text.text(f"Fetched {i}/{total}: {sym} | collected: {len(dfs_all)}")
        except Exception as e:
            st.warning(f"{sym} fetch failed: {e}")
    progress_text.text(f"Completed fetching {len(dfs_all)}/{total} symbols.")
    
    if dfs_all:
        zip_csv_download(dfs_all)
    else:
        st.warning("No data fetched.")
