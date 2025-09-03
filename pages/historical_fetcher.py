import streamlit as st
import pandas as pd
import io
import zipfile
import os
from datetime import datetime, timedelta
import re

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks & Indices (5 Years)")

# (Your existing helper functions: _clean_dt_str, _looks_like_ddmmyyyy_hhmm, etc.)
# For brevity, assume they are already included here as in your original code.

# ... [Include your helper functions here: _clean_dt_str, read_hist_csv_to_df, prepare_ohlcv_for_download, etc.] ...

# Load master CSV
@st.cache_data
def load_master(path="data/master/allmaster.csv"):
    return pd.read_csv(path)

try:
    df_master = load_master()
except Exception as e:
    st.error(f"Master CSV load failed: {e}")
    st.stop()

nse_df = df_master[df_master["SEGMENT"].astype(str).str.upper() == "NSE"]
symbols = nse_df["TRADINGSYM"].astype(str).unique().tolist()
st.info(f"Total NSE symbols: {len(symbols)}")

# Function to fetch 5-year historical data
def fetch_historical_5yr(client, segment, token):
    today = datetime.today()
    frm = (today - timedelta(days=5*365 + 30)).strftime("%d%m%Y%H%M")
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
    CHUNK_SIZE = 1000  # Adjust as needed
    total_symbols = len(symbols)
    chunks = [symbols[i:i + CHUNK_SIZE] for i in range(0, total_symbols, CHUNK_SIZE)]
    zip_files = []

    progress_placeholder = st.empty()

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
        create_zip_for_chunk(dfs_chunk, zip_name)
        zip_files.append(zip_name)

        # Update progress
        progress_placeholder.text(f"Processed chunk {idx}/{len(chunks)}: {len(dfs_chunk)} files.")
    
    # Show download buttons for each ZIP
    st.success(f"Created {len(zip_files)} ZIP files.")
    for zf in zip_files:
        with open(zf, 'rb') as f:
            st.download_button(
                label=f"Download {zf}",
                data=f.read(),
                file_name=zf,
                mime="application/zip"
            )

    # Optional cleanup: delete temp ZIP files after download
    # for zf in zip_files:
    #     os.remove(zf)
