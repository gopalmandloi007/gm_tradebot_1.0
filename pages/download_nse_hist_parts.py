# pages/download_nse_hist_parts.py
import streamlit as st
import pandas as pd
import io
import zipfile
import requests
import time
from datetime import datetime, timedelta
from typing import List

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks & Indices (Daily, Part-wise)")

# ----------------------
# Config
# ----------------------
MASTER_URL = "https://app.definedgesecurities.com/public/allmaster.zip"
MASTER_FILE_COLS = [
    "SEGMENT","TOKEN","SYMBOL","TRADINGSYM","INSTRUMENT","EXPIRY",
    "TICKSIZE","LOTSIZE","OPTIONTYPE","STRIKE","PRICEPREC","MULTIPLIER",
    "ISIN","PRICEMULT","COMPANY"
]
ALLOWED_SEGMENT = "NSE"
ALLOWED_INSTRUMENTS = {"EQ", "BE", "SM", "IDX"}

# ----------------------
# Helpers
# ----------------------
@st.cache_data(show_spinner=True)
def download_master_df() -> pd.DataFrame:
    r = requests.get(MASTER_URL, timeout=30)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = [n for n in z.namelist() if n.lower().endswith('.csv')][0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f, header=None, dtype=str)
    if df.shape[1] >= len(MASTER_FILE_COLS):
        df.columns = MASTER_FILE_COLS + [f"EXTRA_{i}" for i in range(df.shape[1]-len(MASTER_FILE_COLS))]
    else:
        df.columns = MASTER_FILE_COLS[:df.shape[1]]
    return df

def parse_definedge_csv_text(csv_text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(csv_text), header=None, dtype=str)
    if df.shape[1] < 6:
        return pd.DataFrame()
    df = df.rename(columns={0: "DateTime", 1: "Open", 2: "High", 3: "Low", 4: "Close", 5: "Volume"})
    df = df[["DateTime","Open","High","Low","Close","Volume"]].copy()
    try:
        df["Date"] = pd.to_datetime(df["DateTime"], format="%d%m%Y%H%M").dt.strftime("%d/%m/%Y")
        df = df[["Date","Open","High","Low","Close","Volume"]]
    except Exception:
        pass
    return df
def get_api_session_key_from_client(client) -> str:
    if client is None:
        return None
    for a in ["api_session_key","api_key","session_key","token"]:
        if hasattr(client, a):
            val = getattr(client, a)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None

def chunk_df(df: pd.DataFrame, part_size: int) -> List[pd.DataFrame]:
    return [df.iloc[i:i+part_size].copy() for i in range(0, len(df), part_size)]

def fetch_hist_from_api(api_key: str, segment: str, token: str, days_back: int) -> pd.DataFrame:
    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=days_back)
    from_str = start_dt.strftime("%d%m%Y") + "0000"
    to_str = end_dt.strftime("%d%m%Y") + "1530"
    url = f"https://data.definedgesecurities.com/sds/history/{segment}/{token}/day/{from_str}/{to_str}"
    headers = {"Authorization": api_key}
    resp = requests.get(url, headers=headers, timeout=25)
    if resp.status_code == 200 and resp.text.strip():
        return parse_definedge_csv_text(resp.text)
    return pd.DataFrame()

def build_zip(rows: pd.DataFrame, days_back: int, api_key: str, part_name: str) -> io.BytesIO:
    zip_buffer = io.BytesIO()
    total = len(rows)
    progress = st.progress(0.0, text="Fetching data...")
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, (_, row) in enumerate(rows.iterrows(), start=1):
            token = str(row["TOKEN"])
            sym = str(row.get("TRADINGSYM") or row.get("SYMBOL"))
            df = fetch_hist_from_api(api_key, ALLOWED_SEGMENT, token, days_back)
            if df.empty:
                csv_bytes = "NO DATA\n".encode("utf-8")
            else:
                csv_bytes = df.to_csv(index=False).encode("utf-8")
            zf.writestr(f"{sym}_{token}.csv", csv_bytes)
            progress.progress(i/total, text=f"[{i}/{total}] {sym}")
            time.sleep(0.05)
    zip_buffer.seek(0)
    st.success(f"ZIP for {part_name} ready")
    return zip_buffer

# ----------------------
# Main UI
# ----------------------
with st.spinner("Downloading master…"):
    master_df = download_master_df()

df_seg = master_df[master_df["SEGMENT"].astype(str).str.upper() == ALLOWED_SEGMENT]
df_filtered = df_seg[df_seg["INSTRUMENT"].astype(str).str.upper().isin(ALLOWED_INSTRUMENTS)].copy()
st.write(f"Filtered rows: {len(df_filtered)}")

days_back = st.number_input("Days back", min_value=10, max_value=3650, value=365)
part_size = st.number_input("Part size", min_value=10, max_value=2000, value=300, step=50)

client = st.session_state.get("client")
api_key = get_api_session_key_from_client(client)
if not api_key:
    api_key = st.text_input("Definedge API Session Key", type="password")

# --- Split parts always visible ---
if not df_filtered.empty:
    parts = chunk_df(df_filtered.reset_index(drop=True), int(part_size))
    st.subheader(f"Parts: {len(parts)} (≈ {part_size} symbols each)")

    for idx, part_df in enumerate(parts):
        if st.button(f"Download Part {idx+1} ({len(part_df)} symbols)"):
            if not api_key:
                st.error("❌ Please enter API Session Key first.")
            else:
                buf = build_zip(part_df, int(days_back), api_key, f"Part {idx+1}")
                st.download_button(
                    label=f"⬇️ Save Part {idx+1}",
                    data=buf.getvalue(),
                    file_name=f"nse_part_{idx+1:02d}.zip",
                    mime="application/zip"
                )

    if st.button("⬇️ Download ALL"):
        if not api_key:
            st.error("❌ Please enter API Session Key first.")
        else:
            buf = build_zip(df_filtered, int(days_back), api_key, "ALL")
            st.download_button(
                label="⬇️ Save ALL",
                data=buf.getvalue(),
                file_name="nse_all.zip",
                mime="application/zip"
            )
