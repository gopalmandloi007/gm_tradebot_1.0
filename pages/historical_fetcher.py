import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta
import zipfile

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks (Daily)")

# ------------------------- Helper: Clean & Parse Historical CSV -------------------------
def clean_hist_csv(hist_csv: str) -> pd.DataFrame:
    if not hist_csv or not hist_csv.strip():
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(hist_csv), header=None)
    # Map columns: DateTime, Open, High, Low, Close, Volume (7th optional)
    if df.shape[1] == 6:
        df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]
    elif df.shape[1] >= 7:
        df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume", "OI"]
    else:
        return pd.DataFrame()
    # Clean DateTime strings
    df["DateTime"] = df["DateTime"].astype(str).str.strip().str.replace(r'\.0+$', '', regex=True)
    df["DateTime"] = pd.to_datetime(df["DateTime"], format="%d%m%Y%H%M", errors="coerce")
    df = df.dropna(subset=["DateTime"])
    # Create calendar Date
    df["Date"] = df["DateTime"].dt.date
    return df

# ------------------------- Reindex to full calendar (deduplicate first) -------------------------
def reindex_calendar(df: pd.DataFrame):
    if df.empty:
        return df
    # Deduplicate by day (keep last intraday row)
    df = df.sort_values("DateTime").drop_duplicates(subset=["Date"], keep="last")
    # Full calendar index
    full_idx = pd.date_range(df["Date"].min(), df["Date"].max(), freq="D")
    df = df.set_index("Date").reindex(full_idx).rename_axis("Date").reset_index()
    return df

# ------------------------- Fetch & Prepare CSV for Multiple Symbols -------------------------
def fetch_sample_historical(client, symbols, segment="NSE", days_back=365):
    csv_buffers = {}
    today = datetime.today()
    frm = (today - timedelta(days=days_back)).strftime("%d%m%Y%H%M")
    to = today.strftime("%d%m%Y%H%M")

    for sym in symbols:
        try:
            token = sym["TOKEN"]
            raw_csv = client.historical_csv(segment=segment, token=token, timeframe="day", frm=frm, to=to)
            df = clean_hist_csv(raw_csv)
            df = reindex_calendar(df)
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_buffers[sym["TRADINGSYM"]] = csv_buffer.getvalue()
        except Exception as e:
            st.warning(f"{sym['TRADINGSYM']} error: {e}")
    return csv_buffers

# ------------------------- UI -------------------------
# Example symbols list (replace with your NSE master subset)
symbols_list = [
    {"TRADINGSYM": "ZYDUSWELL", "TOKEN": 17635},
    {"TRADINGSYM": "ZYDUSLIFE", "TOKEN": 7929},
    {"TRADINGSYM": "ZUARIIND", "TOKEN": 3827}
]

days_back = st.number_input("Number of days to fetch", min_value=30, max_value=2000, value=365, step=1)

if st.button("Fetch Historical Data"):
    client = st.session_state.get("client")
    if not client:
        st.error("⚠️ Not logged in. Please login first.")
        st.stop()

    st.info(f"Fetching daily OHLCV for {len(symbols_list)} symbols...")
    csv_buffers = fetch_sample_historical(client, symbols_list, days_back=days_back)

    if not csv_buffers:
        st.warning("No historical data fetched.")
        st.stop()

    # ZIP download
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for sym, csv_str in csv_buffers.items():
            zf.writestr(f"{sym}_historical.csv", csv_str)
    zip_buffer.seek(0)
    st.download_button(
        label="📥 Download All Historical CSVs (ZIP)",
        data=zip_buffer,
        file_name="nse_historical_ohlcv.zip",
        mime="application/zip"
    )
    st.success("✅ Historical CSVs ready for download!")
