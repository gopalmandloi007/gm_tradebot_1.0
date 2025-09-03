import streamlit as st
import pandas as pd
import io
import zipfile
from datetime import datetime, timedelta
import traceback
import re

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
    if not hist_csv.strip(): return pd.DataFrame()
    txt = hist_csv.strip()
    lines = txt.splitlines()
    if not lines: return pd.DataFrame()

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
        if "date" in lc or "time" in lc: col_map[c] = "DateTime"
        elif lc.startswith("open"): col_map[c] = "Open"
        elif lc.startswith("high"): col_map[c] = "High"
        elif lc.startswith("low"): col_map[c] = "Low"
        elif lc.startswith("close"): col_map[c] = "Close"
        elif "volume" in lc: col_map[c] = "Volume"
        elif lc == "oi": col_map[c] = "OI"
    if col_map: df = df.rename(columns=col_map)
    else:
        if df.shape[1] >= 6:
            df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]

    # Clean DateTime
    series = _clean_dt_str(df["DateTime"])
    dt = pd.to_datetime(series, dayfirst=True, errors="coerce")
    df["DateTime"] = dt
    df = df.dropna(subset=["DateTime"])
    for col in ("Open","High","Low","Close","Volume","OI"):
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Date"] = df["DateTime"].dt.normalize()
    df = df.sort_values("DateTime").drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)
    df["DateStr"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df[["DateTime","Date","DateStr","Open","High","Low","Close","Volume"]]

# -----------------------
# Prepare OHLCV CSV
# -----------------------
def prepare_ohlcv_for_download(df: pd.DataFrame) -> pd.DataFrame:
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    cols_keep = ["Date","Open","High","Low","Close","Volume"]
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

@st.cache_data
def load_master(path="data/master/allmaster.csv"):
    return pd.read_csv(path)

try:
    df_master = load_master()
except Exception as e:
    st.error(f"Master CSV load failed: {e}")
    st.stop()

# Normalize column names: strip spaces and convert to uppercase
df_master.columns = df_master.columns.str.strip().str.upper()

# Optional: display column names for debugging
st.write("Columns in DataFrame:", df_master.columns)

# Check if expected columns exist
required_columns = ["TRADINGSYM", "SEGMENT", "INSTRUMENT TYPE"]
missing_columns = [col for col in required_columns if col not in df_master.columns]

if missing_columns:
    st.error(f"Missing columns in data: {missing_columns}")
    st.stop()

# Filter for NSE segment
nse_df = df_master[df_master["SEGMENT"].astype(str).str.upper() == "NSE"]
# Filter for Instrument Type 'EQ'
instrument_type_df = df_master[df_master["INSTRUMENT TYPE"].astype(str).str.upper() == "EQ"]

# Extract unique trading symbols from NSE stocks
symbols = nse_df["TRADINGSYM"].astype(str).unique().tolist()

# Display total NSE symbols
st.info(f"Total NSE symbols: {len(symbols)}")

# -----------------------
# Fetch 5-year historical
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
    if not raw or not raw.strip(): return pd.DataFrame()
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
            token_row = nse_df[nse_df["TRADINGSYM"] == sym].iloc[0]
            df_sym = fetch_historical_5yr(client, token_row["SEGMENT"], token_row["TOKEN"])
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
