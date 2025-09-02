import streamlit as st
import pandas as pd
import io
import zipfile
from datetime import datetime, timedelta

# -----------------------
# Clean and prepare OHLCV for download
# -----------------------
def prepare_ohlcv_for_download(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replace messy DateTime with proper ISO dates, keep only OHLCV columns.
    """
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    elif "DateStr" in df.columns:
        df["Date"] = pd.to_datetime(df["DateStr"]).dt.strftime("%Y-%m-%d")
    else:
        df["Date"] = pd.to_datetime(df["DateTime"], errors="coerce").dt.strftime("%Y-%m-%d")

    cols_keep = ["Date", "Open", "High", "Low", "Close", "Volume"]
    df_clean = df[cols_keep].copy()
    return df_clean

# -----------------------
# Single-symbol CSV download
# -----------------------
def single_csv_download(df: pd.DataFrame, symbol: str):
    df_clean = prepare_ohlcv_for_download(df)
    csv_data = df_clean.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"Download {symbol} OHLCV CSV",
        data=csv_data,
        file_name=f"{symbol}_OHLCV.csv",
        mime="text/csv"
    )

# -----------------------
# Multi-symbol ZIP download
# -----------------------
def zip_csv_download(dfs: dict):
    """
    dfs: dict of {symbol: DataFrame}
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for symbol, df in dfs.items():
            df_clean = prepare_ohlcv_for_download(df)
            csv_bytes = df_clean.to_csv(index=False).encode("utf-8")
            zf.writestr(f"{symbol}_OHLCV.csv", csv_bytes)
    zip_buffer.seek(0)
    st.download_button(
        label="Download All OHLCV CSVs (ZIP)",
        data=zip_buffer,
        file_name="OHLCV_data.zip",
        mime="application/zip"
    )

# -----------------------
# Example usage
# -----------------------
st.title("📥 Clean OHLCV Download Demo")

# Fake data for demonstration (replace with your fetched OHLCV)
df1 = pd.DataFrame({
    "DateTime": ["59:44.5", "59:44.5"],
    "Open": [109.78, 106.58],
    "High": [108.9, 114.02],
    "Low": [98.33, 97.89],
    "Close": [109.03, 100.55],
    "Volume": [5901, 8384],
    "Date": ["2025-09-02", "2025-09-01"]
})

df2 = pd.DataFrame({
    "DateTime": ["59:44.5", "59:44.5"],
    "Open": [103.03, 107.67],
    "High": [112.63, 114.32],
    "Low": [95.59, 104.85],
    "Close": [109.06, 102.66],
    "Volume": [4610, 1815],
    "Date": ["2025-08-29", "2025-08-28"]
})

# Single CSV download buttons
single_csv_download(df1, "ZYDUSWELL")
single_csv_download(df2, "ZYARIIND")

# Multi-symbol ZIP download
dfs_all = {"ZYDUSWELL": df1, "ZYARIIND": df2}
zip_csv_download(dfs_all)
