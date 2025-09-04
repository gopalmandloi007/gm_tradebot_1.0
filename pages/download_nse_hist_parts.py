# pages/download_nse_hist_parts.py
import streamlit as st
import pandas as pd
import numpy as np
import io
import zipfile
import requests
from datetime import datetime, timedelta
from typing import List, Tuple

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks & Indices (Daily, Part-wise)")

# =========================
# Config
# =========================
MASTER_URL = "https://app.definedgesecurities.com/public/allmaster.zip"
MASTER_FILE_COLS = [
    "SEGMENT","TOKEN","SYMBOL","TRADINGSYM","INSTRUMENT","EXPIRY",
    "TICKSIZE","LOTSIZE","OPTIONTYPE","STRIKE","PRICEPREC","MULTIPLIER",
    "ISIN","PRICEMULT","COMPANY"
]
ALLOWED_SEGMENT = "NSE"
ALLOWED_INSTRUMENTS = {"EQ", "BE", "SM", "IDX"}   # Filter-2 as requested

# =========================
# Helpers
# =========================
@st.cache_data(show_spinner=True)
def download_master_df() -> pd.DataFrame:
    """
    Download and extract the big master CSV (80k+ rows). Cached.
    """
    r = requests.get(MASTER_URL, timeout=30)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f, header=None)
    # apply friendly col names if size matches, else best-effort
    if df.shape[1] >= len(MASTER_FILE_COLS):
        df.columns = MASTER_FILE_COLS + [f"EXTRA_{i}" for i in range(df.shape[1]-len(MASTER_FILE_COLS))]
    else:
        # Pad unknown columns
        base = MASTER_FILE_COLS[:df.shape[1]]
        df.columns = base
    return df

def clean_hist_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize OHLCV frame."""
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

def make_symbol_key(row: pd.Series) -> str:
    """
    Choose a safe display/file key: prefer TRADINGSYM, fall back to SYMBOL or TOKEN.
    """
    for c in ("TRADINGSYM", "SYMBOL"):
        v = str(row.get(c, "") or "").strip()
        if v:
            return v
    return f"TOKEN_{row.get('TOKEN')}"

def chunk_df(df: pd.DataFrame, part_size: int) -> List[pd.DataFrame]:
    return [df.iloc[i:i+part_size].copy() for i in range(0, len(df), part_size)]

def _mock_hist(days_back: int) -> pd.DataFrame:
    """
    Fallback generator when no client/historical API is available.
    Generates business-day OHLCV.
    """
    today = datetime.today()
    dates = pd.date_range(end=today, periods=days_back, freq="B")
    df = pd.DataFrame({
        "DateTime": dates,
        "Open": 100 + np.random.rand(len(dates)) * 10,
        "High": 105 + np.random.rand(len(dates)) * 10,
        "Low":  95 + np.random.rand(len(dates)) * 10,
        "Close":100 + np.random.rand(len(dates)) * 10,
        "Volume": np.random.randint(5_000, 150_000, len(dates))
    })
    return clean_hist_df(df)

def fetch_hist_daily(client, exchange: str, token: str, days_back: int) -> pd.DataFrame:
    """
    Plug your real historical daily OHLCV here.
    Expected output columns: DateTime, Open, High, Low, Close, Volume
    """
    # --- EXAMPLE PLACEHOLDER ---
    # If you have a real method, e.g.:
    # raw = client.get_ohlc_daily(exchange, token, from_date, to_date)
    # df = pd.DataFrame(raw)  # normalize to expected columns
    # return clean_hist_df(df)
    # Fallback (mock data):
    return _mock_hist(days_back)

def build_zip_for_rows(rows: pd.DataFrame, days_back: int, client, exchange: str) -> io.BytesIO:
    """
    Given a subset of master rows, fetch daily OHLCV for each and pack into a ZIP.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        progress = st.progress(0.0, text="Preparing files...")
        total = len(rows)
        for i, (_, r) in enumerate(rows.iterrows(), start=1):
            sym = make_symbol_key(r)
            token = str(r.get("TOKEN"))
            try:
                df = fetch_hist_daily(client, exchange, token, days_back)
                if df.empty:
                    # write an empty stub to indicate attempt
                    csv_bytes = pd.DataFrame(columns=["DateTime","Open","High","Low","Close","Volume"]).to_csv(index=False).encode("utf-8")
                else:
                    csv_bytes = df.to_csv(index=False).encode("utf-8")
                zf.writestr(f"{sym}.csv", csv_bytes)
            except Exception as e:
                # write error marker file
                msg = f"symbol={sym} token={token} error={e}"
                zf.writestr(f"{sym}__ERROR.txt", msg.encode("utf-8"))
            progress.progress(i/total, text=f"Processed {i}/{total}: {sym}")
    zip_buffer.seek(0)
    return zip_buffer

# =========================
# Load & Filter Master
# =========================
with st.spinner("Downloading master…"):
    master_df = download_master_df()

total_master = len(master_df)
df_seg = master_df[master_df["SEGMENT"].astype(str).str.upper() == ALLOWED_SEGMENT]
after_seg = len(df_seg)

df_filtered = df_seg[df_seg["INSTRUMENT"].astype(str).str.upper().isin(ALLOWED_INSTRUMENTS)].copy()
after_instr = len(df_filtered)

# Drop exact duplicates by TRADINGSYM+TOKEN to be safe
if {"TRADINGSYM","TOKEN"}.issubset(df_filtered.columns):
    df_filtered = df_filtered.drop_duplicates(subset=["TRADINGSYM","TOKEN"])

st.markdown(f"""
**Master loaded:** {total_master:,} rows  
**After Filter-1 (SEGMENT = {ALLOWED_SEGMENT}):** {after_seg:,} rows  
**After Filter-2 (INSTRUMENT in {sorted(ALLOWED_INSTRUMENTS)}):** **{len(df_filtered):,}** rows
""")

# =========================
# Controls
# =========================
left, right = st.columns([1,1])
with left:
    days_back = st.number_input("Number of business days to fetch", min_value=30, max_value=2000, value=365, step=1)
with right:
    part_size = st.number_input("Part size (symbols per ZIP)", min_value=50, max_value=1000, value=300, step=50)

# Compute parts
parts = chunk_df(df_filtered, int(part_size))
num_parts = len(parts)

st.subheader(f"Parts: {num_parts} (size ≈ {part_size} each)")
st.caption("Click a part to build a ZIP for that slice. Or use **Download ALL** to build everything in one ZIP (can be large).")

# Render buttons in a neat grid
cols_per_row = 10 if num_parts >= 10 else max(3, num_parts)
rows_needed = (num_parts + cols_per_row - 1) // cols_per_row

# Keep client if present
client = st.session_state.get("client")
exchange = ALLOWED_SEGMENT  # NSE

# Placeholders for download areas
download_placeholder = st.empty()

# Part buttons
part_clicked = None
idx = 0
for _ in range(rows_needed):
    cols = st.columns(cols_per_row)
    for c in cols:
        if idx < num_parts:
            label = f"Part {idx+1} ({len(parts[idx])})"
            if c.button(label, key=f"btn_part_{idx+1}"):
                part_clicked = idx
        idx += 1

# If a part is clicked, build and show its download
if part_clicked is not None:
    subdf = parts[part_clicked]
    st.info(f"Building ZIP for Part {part_clicked+1} with {len(subdf)} symbols…")
    zip_buf = build_zip_for_rows(subdf, days_back, client, exchange)
    download_placeholder.download_button(
        label=f"⬇️ Download Part {part_clicked+1} (ZIP)",
        data=zip_buf.getvalue(),
        file_name=f"nse_daily_part_{part_clicked+1:02d}.zip",
        mime="application/zip"
    )

st.markdown("---")
# Download ALL
st.warning("**Download ALL** may take significant time/memory depending on symbols and days.", icon="⚠️")
if st.button("⬇️ Build & Download ALL (one ZIP)"):
    st.info(f"Building ALL parts… ({len(df_filtered)} symbols)")
    zip_all = build_zip_for_rows(df_filtered, days_back, client, exchange)
    st.download_button(
        label="⬇️ Download ALL (ZIP)",
        data=zip_all.getvalue(),
        file_name="nse_daily_all.zip",
        mime="application/zip"
    )

# Small peek of current filter result
with st.expander("Preview filtered symbols (first 50)"):
    preview_cols = [c for c in ["SEGMENT","INSTRUMENT","TRADINGSYM","SYMBOL","TOKEN","COMPANY"] if c in df_filtered.columns]
    st.dataframe(df_filtered[preview_cols].head(50), use_container_width=True)

st.success("✅ Ready. Use the buttons above to download specific parts or ALL.")
