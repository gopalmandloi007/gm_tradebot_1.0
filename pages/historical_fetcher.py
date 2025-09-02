import streamlit as st
import pandas as pd
import io
import zipfile
from datetime import datetime, timedelta
import traceback

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks & Indices (5 Years)")

# -----------------------
# Clean and prepare OHLCV for download
# -----------------------
def prepare_ohlcv_for_download(df: pd.DataFrame) -> pd.DataFrame:
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    elif "DateStr" in df.columns:
        df["Date"] = pd.to_datetime(df["DateStr"], errors="coerce").dt.strftime("%Y-%m-%d")
    else:
        df["Date"] = pd.to_datetime(df["DateTime"], errors="coerce").dt.strftime("%Y-%m-%d")
    cols_keep = ["Date", "Open", "High", "Low", "Close", "Volume"]
    df_clean = df[cols_keep].copy()
    return df_clean

# -----------------------
# ZIP download for multiple symbols
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
# Load master file
# -----------------------
@st.cache_data
def load_master_symbols(path="data/master/allmaster.csv"):
    return pd.read_csv(path)

try:
    df_master = load_master_symbols()
except Exception as e:
    st.error(f"Failed to load master CSV: {e}")
    st.stop()

# -----------------------
# Filter NSE stocks + indices
# -----------------------
nse_df = df_master[df_master["SEGMENT"].astype(str).str.upper() == "NSE"].copy()
symbols = nse_df["TRADINGSYM"].astype(str).unique().tolist()

st.info(f"Total NSE symbols (stocks + indices) detected: {len(symbols)}")

# -----------------------
# Historical fetch wrapper (5 years)
# -----------------------
def fetch_historical_5yr(client, segment, token):
    today = datetime.today()
    frm = (today - timedelta(days=5*365 + 30)).strftime("%d%m%Y%H%M")  # 5 years + 30 buffer
    to = today.strftime("%d%m%Y%H%M")
    try:
        raw = client.historical_csv(segment=segment, token=token, timeframe="day", frm=frm, to=to)
    except Exception as e:
        st.warning(f"Failed fetch for {token}: {e}")
        return pd.DataFrame()
    if raw is None or not raw.strip():
        return pd.DataFrame()
    # Use your existing robust parser
    from st_pages_ohlcv_parser import read_hist_csv_to_df  # assume your parser is in separate module
    df = read_hist_csv_to_df(raw)
    return df

# -----------------------
# Fetch all symbols on button click
# -----------------------
if st.button("Fetch 5-Year OHLCV for All NSE Symbols"):
    client = st.session_state.get("client")
    if not client:
        st.error("Please login first (client missing).")
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
        st.warning("No historical data fetched.")
