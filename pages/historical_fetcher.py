import streamlit as st
import pandas as pd
import io
import zipfile
import os
from datetime import datetime, timedelta
import re

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks & Indices (5 Years)")

# --- Your helper functions start here ---

def _clean_dt_str(s: pd.Series) -> pd.Series:
    sc = s.astype(str).str.strip()
    sc = sc.str.replace(r'\.0+$', '', regex=True)
    sc = sc.str.replace(r'["\']', '', regex=True)
    sc = sc.str.replace(r'\s+', '', regex=True)
    return sc

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

def prepare_ohlcv_for_download(df: pd.DataFrame) -> pd.DataFrame:
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    cols_keep = ["Date", "Open", "High", "Low", "Close", "Volume"]
    return df[cols_keep].copy()

# --- Your other helper functions as needed ---

# ... (rest of your helper functions) ...

# --- End of helper functions ---

# Your main code continues here...

# Load master CSV
@st.cache_data
def load_master(path="data/master/allmaster.csv"):
    return pd.read_csv(path)

try:
    df_master = load_master()
except Exception as e:
    st.error(f"Master CSV load failed: {e}")
    st.stop()

# Print unique values to understand data
st.write("Unique SEGMENT values before normalization:", df_master["SEGMENT"].dropna().unique())

# Normalize 'SEGMENT' column: strip spaces and convert to uppercase
df_master["SEGMENT"] = df_master["SEGMENT"].astype(str).str.strip().str.upper()

# Check again after normalization
st.write("Unique SEGMENT values after normalization:", df_master["SEGMENT"].dropna().unique())

# Filter based on allowed segments
allowed_segments = ["BE", "EQ", "SM", "IDX"]
filtered_df = df_master[df_master["SEGMENT"].isin(allowed_segments)]

# Show filtered shape for debugging
st.write("Filtered data shape:", filtered_df.shape)

# Extract symbols
symbols = filtered_df["TRADINGSYM"].astype(str).unique().tolist()
st.info(f"Total symbols after filtering: {len(symbols)}")

# Function to fetch 5-year historical data
def fetch_historical_5yr(client, segment, token):
    today = datetime.today()
    frm = (today - timedelta(days=1*365 + 30)).strftime("%d%m%Y%H%M")
    to = today.strftime("%d%m%Y%H%M")
    try:
        raw = client.historical_csv(segment=segment, token=token, timeframe="day", frm=frm, to=to)
    except Exception as e:
        st.warning(f"Failed fetch for token {token}: {e}")
        return pd.DataFrame()
    if not raw or not raw.strip():
        return pd.DataFrame()
    return read_hist_csv_to_df(raw)

# Function to create a ZIP file from a batch of symbols
def create_zip_for_chunk(dfs_chunk, zip_path):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for symbol, df in dfs_chunk.items():
            df_clean = prepare_ohlcv_for_download(df)
            csv_bytes = df_clean.to_csv(index=False).encode("utf-8")
            zf.writestr(f"{symbol}_OHLCV.csv", csv_bytes)
    # Save to disk
    with open(zip_path, 'wb') as f:
        f.write(zip_buffer.getvalue())

# Main process on button click
if st.button("Fetch 5-Year OHLCV for All NSE Symbols"):
    client = st.session_state.get("client")
    if not client:
        st.error("Please login first.")
        st.stop()

    # Chunk size for batch processing
    CHUNK_SIZE = 100  # Adjust as needed
    total_symbols = len(symbols)

    # Make sure to define chunks here
    chunks = [symbols[i:i + CHUNK_SIZE] for i in range(0, total_symbols, CHUNK_SIZE)]

    total_chunks = len(chunks)
    zip_files = []

    progress_bar = st.progress(0)
    for idx, chunk in enumerate(chunks, 1):
        dfs_chunk = {}
        for sym in chunk:
            try:
                token_row = nse_df[nse_df["TRADINGSYM"] == sym].iloc[0]
                df_sym = fetch_historical_5yr(client, token_row["SEGMENT"], token_row["TOKEN"])
                if not df_sym.empty:
                    dfs_chunk[sym] = df_sym
            except Exception as e:
                st.warning(f"Fetch failed for {sym}: {e}")
        zip_name = f"nse_chunk_{idx}.zip"
        try:
            create_zip_for_chunk(dfs_chunk, zip_name)
            zip_files.append(zip_name)
        except Exception as e:
            st.error(f"Failed to create ZIP for chunk {idx}: {e}")

        # Update progress bar
        progress_bar.progress(idx / total_chunks)
        st.write(f"Processed chunk {idx}/{total_chunks}")

    st.success(f"Created {len(zip_files)} ZIP files.")
    for zf in zip_files:
        with open(zf, 'rb') as f:
            st.download_button(
                label=f"Download {zf}",
                data=f.read(),
                file_name=zf,
                mime="application/zip"
            )
