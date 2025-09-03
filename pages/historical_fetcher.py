import streamlit as st
import pandas as pd
import numpy as np  # <-- import numpy
import io
import zipfile
from datetime import datetime, timedelta

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks (Daily)")

# -------------------------
# Helper: Clean & normalize OHLCV CSV
# -------------------------
def clean_hist_df(df: pd.DataFrame) -> pd.DataFrame:
    if "DateTime" not in df.columns:
        return pd.DataFrame()
    df["DateTime"] = pd.to_datetime(df["DateTime"], errors="coerce")
    df = df.dropna(subset=["DateTime"])
    df["Date"] = df["DateTime"].dt.normalize()
    df["DateStr"] = df["Date"].dt.strftime("%Y-%m-%d")
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("Date").reset_index(drop=True)
    return df

# -------------------------
# UI: Number of days & sample symbols
# -------------------------
days_back = st.number_input("Number of days to fetch", min_value=30, max_value=2000, value=365, step=1)

# Sample NSE symbols (replace with actual master list)
symbols = {
    "NIFTY MIDSML 400": 26063,
    "Nifty 50": 26000,
    "Nifty 500": 26004,
    "ZYDUSWELL": 17635,
    "ZYDUSLIFE": 7929,
    "ZUARIIND": 3827
}

st.write(f"Fetching daily OHLCV for {len(symbols)} symbols...")

# -------------------------
# Fetch & store CSVs in memory
# -------------------------
zip_buffer = io.BytesIO()

with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
    for sym, token in symbols.items():
        try:
            # --- Replace below with actual client fetch ---
            today = datetime.today()
            dates = pd.date_range(end=today, periods=days_back, freq='B')
            df = pd.DataFrame({
                "DateTime": dates,
                "Open": 100 + np.random.rand(len(dates))*10,   # <-- use np.random
                "High": 105 + np.random.rand(len(dates))*10,
                "Low": 95 + np.random.rand(len(dates))*10,
                "Close": 100 + np.random.rand(len(dates))*10,
                "Volume": np.random.randint(1000,10000, len(dates))
            })
            df = clean_hist_df(df)
            
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            zf.writestr(f"{sym}.csv", csv_bytes)
        except Exception as e:
            st.warning(f"{sym} error: {e}")

zip_buffer.seek(0)
st.download_button(
    label="Download Historical OHLCV ZIP",
    data=zip_buffer,
    file_name="nse_ohlcv_daily.zip",
    mime="application/zip"
)

st.success("✅ ZIP ready! Each CSV has ISO dates (YYYY-MM-DD).")
