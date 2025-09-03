import streamlit as st
import pandas as pd
import numpy as np  # <-- import numpy
import io
import zipfile
from datetime import datetime, timedelta
import requests  # <-- missing import

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

@st.cache_data
def load_allmaster_symbols(zip_url="https://app.definedgesecurities.com/public/allmaster.zip"):
    # Download the ZIP file
    response = requests.get(zip_url)
    if response.status_code != 200:
        st.error("Failed to download master ZIP file.")
        return None

    # Load ZIP in memory
    zip_bytes = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_bytes, 'r') as zf:
        # List all files in ZIP
        file_list = zf.namelist()
        # Find the CSV file, assuming it's named 'allmaster.csv' or similar
        master_csv_name = None
        for filename in file_list:
            if filename.lower().endswith('.csv'):
                master_csv_name = filename
                break
        if not master_csv_name:
            st.error("No CSV file found in ZIP.")
            return None

        # Read CSV content
        with zf.open(master_csv_name) as f:
            df = pd.read_csv(f)
            return df

# Initialize symbols dictionary
symbols = {}

# Load the master symbols dataframe
master_df = load_allmaster_symbols()

if master_df is not None:
    st.write("Master Data Loaded Successfully.")
    st.write("Columns:", master_df.columns.tolist())

    # Replace 'NSE' and 'ID' with your actual column names
    for _, row in master_df.iterrows():
        symbol_name = row.get('NSE', None)  # Adjust if needed
        token = row.get('ID', None)         # Adjust if needed
        if symbol_name and token:
            symbols[symbol_name] = token

    st.write(f"Total symbols loaded: {len(symbols)}")
else:
    st.warning("Could not load master symbols. Proceeding with empty symbol list.")

# -------------------------
# Fetch & store CSVs in memory
# -------------------------
zip_buffer = io.BytesIO()

if symbols:
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for sym, token in symbols.items():
            try:
                # Replace this dummy data fetch with real data fetch if needed
                today = datetime.today()
                dates = pd.date_range(end=today, periods=days_back, freq='B')
                df = pd.DataFrame({
                    "DateTime": dates,
                    "Open": 100 + np.random.rand(len(dates)) * 10,
                    "High": 105 + np.random.rand(len(dates)) * 10,
                    "Low": 95 + np.random.rand(len(dates)) * 10,
                    "Close": 100 + np.random.rand(len(dates)) * 10,
                    "Volume": np.random.randint(1000, 10000, len(dates))
                })
                df = clean_hist_df(df)

                csv_bytes = df.to_csv(index=False).encode("utf-8")
                zf.writestr(f"{sym}.csv", csv_bytes)
            except Exception as e:
                st.warning(f"{sym} error: {e}")
else:
    st.info("No symbols loaded. Skipping data generation.")

# Prepare ZIP download
zip_buffer.seek(0)
st.download_button(
    label="Download Historical OHLCV ZIP",
    data=zip_buffer,
    file_name="nse_ohlcv_daily.zip",
    mime="application/zip"
)

st.success("✅ ZIP ready! Each CSV has ISO dates (YYYY-MM-DD).")
