import streamlit as st
import pandas as pd
import requests
import io
import zipfile
from datetime import datetime, timedelta

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks (Daily)")

# ----------------------------
# Helper: Get API key from client (same as place order code)
# ----------------------------
def get_api_session_key(client):
    try:
        return client._api_session_key  # <-- same property we used earlier
    except Exception:
        return None

# ----------------------------
# Helper: Clean & normalize OHLCV CSV
# ----------------------------
def clean_hist_df(text: str) -> pd.DataFrame:
    if not text.strip():
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(text), header=None)
    if df.shape[1] < 6:
        return pd.DataFrame()
    df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume", "OI"]
    df["DateTime"] = pd.to_datetime(df["DateTime"], errors="coerce")
    df = df.dropna(subset=["DateTime"])
    df["Date"] = df["DateTime"].dt.normalize()
    df = df.sort_values("Date").reset_index(drop=True)
    return df

# ----------------------------
# UI: Master file upload
# ----------------------------
master_file = st.file_uploader("📂 Upload Master CSV", type=["csv"])

if master_file is not None:
    master_df = pd.read_csv(master_file)

    st.write(f"🔎 Total rows in master: {len(master_df)}")

    # --- Filter 1: only NSE
    master_df = master_df[master_df["segment"] == "NSE"]
    st.write(f"➡️ After Filter-1 (segment = NSE): {len(master_df)} rows")

    # --- Filter 2: instrument type
    allowed_types = ["EQ", "BE", "SM", "IDX"]
    master_df = master_df[master_df["instrumenttype"].isin(allowed_types)]
    st.write(f"➡️ After Filter-2 (InstrumentType EQ/BE/SM/IDX): {len(master_df)} rows")

    # --- Partition logic
    part_size = 300
    total_parts = (len(master_df) // part_size) + 1
    option = st.selectbox("📌 Select Download Option", ["Download All"] + [f"Part {i}" for i in range(1, total_parts+1)])

    # --- Date range
    days_back = st.number_input("Number of days to fetch", min_value=30, max_value=2000, value=365)

    # --- Client API key
    client = st.session_state.get("client", None)  # assuming client already saved in session
    api_key = get_api_session_key(client)
    if not api_key:
        st.error("❌ API session key not found from client. Please login again.")
    else:
        st.success("🔑 API key found from client")

    # --- Fetch data
    if st.button("🚀 Start Download"):
        zip_buffer = io.BytesIO()
        end_dt = datetime.today()
        start_dt = end_dt - timedelta(days=days_back)
        from_str = start_dt.strftime("%d%m%Y") + "0000"
        to_str = end_dt.strftime("%d%m%Y") + "1530"

        # Select subset
        if option == "Download All":
            subset_df = master_df
        else:
            part_no = int(option.split()[-1])
            start_idx = (part_no - 1) * part_size
            end_idx = start_idx + part_size
            subset_df = master_df.iloc[start_idx:end_idx]

        st.write(f"📊 Downloading {len(subset_df)} symbols...")

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, row in subset_df.iterrows():
                sym = row["tradingsymbol"]
                token = row["token"]
                segment = row["segment"]

                try:
                    url = f"https://data.definedgesecurities.com/sds/history/{segment}/{token}/day/{from_str}/{to_str}"
                    resp = requests.get(url, headers={"Authorization": api_key}, timeout=20)

                    if resp.status_code == 200 and resp.text.strip():
                        df = clean_hist_df(resp.text)
                        if not df.empty:
                            csv_bytes = df.to_csv(index=False).encode("utf-8")
                            zf.writestr(f"{sym}.csv", csv_bytes)
                        else:
                            st.warning(f"{sym}: No data in response")
                    else:
                        st.warning(f"{sym}: API empty or error {resp.status_code}")

                except Exception as e:
                    st.warning(f"{sym} error: {e}")

        zip_buffer.seek(0)
        st.download_button(
            label="⬇️ Download Historical OHLCV ZIP",
            data=zip_buffer,
            file_name="nse_ohlcv_daily.zip",
            mime="application/zip"
        )
        st.success("✅ ZIP ready! Each CSV has OHLCV data")
