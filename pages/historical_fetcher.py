import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta
import zipfile

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks (Daily)")

# ------------------------
# Utilities
# ------------------------
def read_hist_csv_to_df(raw_csv: str) -> pd.DataFrame:
    """Basic robust parser for historical CSV (similar to your chart code)."""
    if not raw_csv.strip():
        return pd.DataFrame()
    try:
        df = pd.read_csv(io.StringIO(raw_csv), header=None)
    except Exception:
        df = pd.read_csv(io.StringIO(raw_csv), header=None, delim_whitespace=True)
    if df.shape[1] >= 6:
        df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"] + (["OI"] if df.shape[1]==7 else [])
    else:
        return pd.DataFrame()
    # Numeric conversion
    for c in ["Open","High","Low","Close","Volume","OI"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def clean_hist_df(df: pd.DataFrame) -> pd.DataFrame:
    """Clean historical OHLCV dataframe: deduplicate, remove future dates, keep only valid rows."""
    if df.empty:
        return df
    # Convert DateTime
    if "DateTime" in df.columns:
        df["Date"] = pd.to_datetime(df["DateTime"], errors="coerce").dt.normalize()
    elif "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
    else:
        return pd.DataFrame()
    # Keep only rows with Close > 0
    df = df.dropna(subset=["Close"])
    df = df[df["Close"] > 0]
    # Keep only past dates
    today = pd.to_datetime(datetime.today().date())
    df = df[df["Date"] <= today]
    # Sort and deduplicate
    df = df.sort_values("Date").drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)
    # Optional: keep DateStr for categorical axis
    df["DateStr"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df

# ------------------------
# UI Controls
# ------------------------
days_back = st.number_input("Number of days to fetch", min_value=10, max_value=2000, value=365, step=1)

# Simulated list of NSE symbols for demo (replace with your master.csv & token API)
symbols = ["ZYDUSWELL", "ZYDUSLIFE", "ZUARIIND"]
tokens = [17635, 7929, 3827]

if st.button("Fetch Historical OHLCV"):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for symbol, token in zip(symbols, tokens):
            st.info(f"Fetching {symbol}...")
            try:
                # ------------------------
                # Replace this with actual API call: client.historical_csv(...)
                # For demo, let's generate fake CSV
                fake_csv = "\n".join([
                    "28-08-2025,2026.3,2041.2,1992.9,2031,34530",
                    "29-08-2025,2040,2045,2005,2018.7,28546",
                    "10-09-2025,2070,2249.7,2065,2217.8,1267867",
                    "20-09-2025,2237.6,2286,2221.3,2253.5,215386",
                ])
                df = read_hist_csv_to_df(fake_csv)
                df = clean_hist_df(df)
                if df.empty:
                    st.warning(f"No historical data for {symbol}")
                    continue
                csv_bytes = df.to_csv(index=False).encode("utf-8")
                zf.writestr(f"{symbol}.csv", csv_bytes)
                st.success(f"{symbol} processed and added to ZIP")
            except Exception as e:
                st.error(f"Error for {symbol}: {e}")
    zip_buffer.seek(0)
    st.download_button(
        label="Download All Historical CSVs (ZIP)",
        data=zip_buffer,
        file_name=f"nse_ohlcv_{datetime.today().strftime('%Y%m%d')}.zip",
        mime="application/zip"
    )
