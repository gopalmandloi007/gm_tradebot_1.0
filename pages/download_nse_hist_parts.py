# pages/download_nse_hist_parts.py
import streamlit as st
import pandas as pd
import numpy as np
import io
import zipfile
import requests
import os
import time
import traceback
from datetime import datetime, timedelta
from typing import List, Tuple

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks & Indices (Daily, Part-wise)")

# ----------------------
# Configuration
# ----------------------
MASTER_URL = "https://app.definedgesecurities.com/public/allmaster.zip"
MASTER_FILE_COLS = [
    "SEGMENT","TOKEN","SYMBOL","TRADINGSYM","INSTRUMENT","EXPIRY",
    "TICKSIZE","LOTSIZE","OPTIONTYPE","STRIKE","PRICEPREC","MULTIPLIER",
    "ISIN","PRICEMULT","COMPANY"
]
ALLOWED_SEGMENT = "NSE"
ALLOWED_INSTRUMENTS = {"EQ", "BE", "SM", "IDX"}

# ensure session caches exist
if "_hist_cache" not in st.session_state:
    st.session_state["_hist_cache"] = {}   # key -> bytes (csv)
if "_zip_cache" not in st.session_state:
    st.session_state["_zip_cache"] = {}    # key -> bytes (zip)

# ----------------------
# Helpers
# ----------------------
@st.cache_data(show_spinner=True)
def download_master_df() -> pd.DataFrame:
    """
    Download and parse master.zip (headerless). Cached across runs.
    """
    r = requests.get(MASTER_URL, timeout=30)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = [n for n in z.namelist() if n.lower().endswith('.csv')][0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f, header=None, dtype=str)
    # set friendly column names best-effort
    if df.shape[1] >= len(MASTER_FILE_COLS):
        df.columns = MASTER_FILE_COLS + [f"EXTRA_{i}" for i in range(df.shape[1]-len(MASTER_FILE_COLS))]
    else:
        df.columns = MASTER_FILE_COLS[:df.shape[1]]
    return df

def clean_hist_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize historical data returned by API.
    Expects at least columns: DateTime, Open, High, Low, Close, Volume
    """
    if "DateTime" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    # try robust parsing
    df["DateTime"] = pd.to_datetime(df["DateTime"], errors="coerce", dayfirst=True)
    df = df.dropna(subset=["DateTime"])
    # keep expected columns & convert numeric
    for c in ["Open","High","Low","Close","Volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values("DateTime").reset_index(drop=True)
    return df[["DateTime","Open","High","Low","Close","Volume"]]

def sanitize_filename(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        s = s.replace(ch, '_')
    s = s.replace(' ', '_')
    return s

def chunk_df(df: pd.DataFrame, part_size: int) -> List[pd.DataFrame]:
    return [df.iloc[i:i+part_size].copy() for i in range(0, len(df), part_size)]

def get_api_session_key_from_client(client) -> str:
    """
    Tries common attribute/method names on client to retrieve API session key.
    If not found, returns None.
    """
    if client is None:
        return None
    # common attribute names
    attrs = [
        "api_session_key", "api_key", "session_key", "session", "token",
        "auth_token", "access_token", "apikey", "authorization"
    ]
    for a in attrs:
        if hasattr(client, a):
            val = getattr(client, a)
            try:
                if callable(val):
                    val = val()
            except Exception:
                val = None
            if isinstance(val, str) and val.strip():
                return val.strip()
    # check client.headers-like dict
    for a in ["headers", "_headers", "default_headers"]:
        if hasattr(client, a):
            hdrs = getattr(client, a)
            if isinstance(hdrs, dict):
                for key in ("Authorization","authorization","Auth","auth"):
                    if key in hdrs and isinstance(hdrs[key], str) and hdrs[key].strip():
                        return hdrs[key].strip()
    # try common getter methods
    methods = ["get_api_key","get_session_key","get_token","get_auth","get_headers"]
    for m in methods:
        if hasattr(client, m) and callable(getattr(client, m)):
            try:
                out = getattr(client, m)()
                if isinstance(out, str) and out.strip():
                    return out.strip()
                if isinstance(out, dict):
                    for k in ("Authorization","authorization","api_key","token"):
                        if k in out and isinstance(out[k], str) and out[k].strip():
                            return out[k].strip()
            except Exception:
                pass
    return None

def parse_definedge_csv_text(csv_text: str) -> pd.DataFrame:
    """
    Parse CSV without headers from Definedge Historical API.
    Columns for daily/minute: Dateandtime, Open, High, Low, Close, Volume, OI
    We'll accept 6 or 7 columns and map first 6 accordingly.
    """
    if not csv_text or not csv_text.strip():
        return pd.DataFrame()
    try:
        df = pd.read_csv(io.StringIO(csv_text), header=None, dtype=str)
        # If there are at least 6 columns
        if df.shape[1] >= 6:
            # name first 6
            colmap = {0: "DateTime", 1: "Open", 2: "High", 3: "Low", 4: "Close", 5: "Volume"}
            df = df.rename(columns=colmap)
            # drop extra columns (like OI)
            keep_cols = [c for c in ["DateTime","Open","High","Low","Close","Volume"] if c in df.columns]
            df = df[keep_cols]
            return clean_hist_df(df)
    except Exception:
        # fallback: try pandas with sep='[,;]'? but keep simple
        pass
    return pd.DataFrame()

def fetch_hist_from_api(api_key: str, segment: str, token: str, days_back: int,
                        retries: int = 2, timeout: int = 25) -> pd.DataFrame:
    """
    Call Definedge Historical API and return normalized DataFrame (DateTime, Open, High, Low, Close, Volume).
    Uses simple retries and returns empty df on failure.
    """
    if not api_key or not token:
        return pd.DataFrame()
    # compute from/to in ddMMyyyyHHmm
    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=days_back)
    from_str = start_dt.strftime("%d%m%Y") + "0000"
    to_str = end_dt.strftime("%d%m%Y") + "1530"
    url = f"https://data.definedgesecurities.com/sds/history/{segment}/{token}/day/{from_str}/{to_str}"
    headers = {"Authorization": api_key}
    last_err = None
    for attempt in range(1, retries+1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200 and resp.text and resp.text.strip():
                df = parse_definedge_csv_text(resp.text)
                # sometimes API returns single-line message or HTML - guard
                if not df.empty:
                    return df
                else:
                    # empty but 200: treat as no-data
                    return pd.DataFrame()
            else:
                last_err = f"HTTP {resp.status_code}"
        except Exception as e:
            last_err = str(e)
        # simple backoff
        time.sleep(0.25 * attempt)
    # all retries failed
    st.warning(f"Failed to fetch token {token} after {retries} attempts: {last_err}")
    return pd.DataFrame()

def build_zip_for_rows(rows: pd.DataFrame, days_back: int, api_key: str, segment: str,
                       delay_sec: float = 0.02, retries: int = 2) -> io.BytesIO:
    """
    Build ZIP (in memory) for provided master rows (each row must contain TOKEN and TRADINGSYM or SYMBOL).
    Uses st.session_state cache to avoid re-downloading the same token/day combination within session.
    Returns BytesIO containing zip bytes.
    """
    zip_buffer = io.BytesIO()
    total = len(rows)
    progress = st.progress(0.0, text="Preparing files...")
    status_box = st.empty()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, (_, row) in enumerate(rows.iterrows(), start=1):
            token = str(row.get("TOKEN", "") or "")
            trad = str(row.get("TRADINGSYM", "") or "") or str(row.get("SYMBOL", "") or "")
            company = str(row.get("COMPANY", "") or "")
            fname_base = sanitize_filename(f"{trad}_{token}")
            cache_key = (token, days_back)
            csv_bytes = None
            # Use cache if available
            if cache_key in st.session_state["_hist_cache"]:
                csv_bytes = st.session_state["_hist_cache"][cache_key]
                status = f"Using cached data for {trad} ({token})"
            else:
                try:
                    df = fetch_hist_from_api(api_key, segment, token, days_back, retries=retries)
                    if df.empty:
                        # write an empty stub file to signal no-data
                        csv_bytes = pd.DataFrame(columns=["DateTime","Open","High","Low","Close","Volume"]).to_csv(index=False).encode("utf-8")
                        status = f"No data for {trad} ({token})"
                    else:
                        csv_bytes = df.to_csv(index=False).encode("utf-8")
                        status = f"Fetched {len(df)} rows for {trad} ({token})"
                    # cache it
                    st.session_state["_hist_cache"][cache_key] = csv_bytes
                except Exception as e:
                    csv_bytes = f"ERROR fetching {trad} ({token}): {e}\n{traceback.format_exc()}".encode("utf-8")
                    status = f"Error for {trad} ({token})"
            # write file to zip
            zf.writestr(f"{fname_base}.csv", csv_bytes)
            # update progress & status
            progress.progress(i/total, text=f"[{i}/{total}] {status}")
            status_box.text(status)
            # polite delay to avoid hammering API
            if delay_sec > 0:
                time.sleep(delay_sec)
    zip_buffer.seek(0)
    return zip_buffer

# ----------------------
# Load & filter master
# ----------------------
with st.spinner("Downloading master (this may take a few seconds)…"):
    master_df = download_master_df()

total_master = len(master_df)
df_seg = master_df[master_df["SEGMENT"].astype(str).str.upper() == ALLOWED_SEGMENT]
after_seg = len(df_seg)
df_filtered = df_seg[df_seg["INSTRUMENT"].astype(str).str.upper().isin(ALLOWED_INSTRUMENTS)].copy()
# remove duplicates
if {"TRADINGSYM","TOKEN"}.issubset(df_filtered.columns):
    df_filtered = df_filtered.drop_duplicates(subset=["TRADINGSYM","TOKEN"])
after_instr = len(df_filtered)

st.markdown(f"""
**Master loaded:** {total_master:,} rows  
**After Filter-1 (SEGMENT = {ALLOWED_SEGMENT}):** {after_seg:,} rows  
**After Filter-2 (INSTRUMENT in {sorted(ALLOWED_INSTRUMENTS)}):** **{after_instr:,}** rows
""")

# ----------------------
# Controls
# ----------------------
c1, c2, c3 = st.columns([1,1,1])
with c1:
    days_back = st.number_input("Number of days to fetch (calendar days)", min_value=30, max_value=3650, value=365, step=1)
with c2:
    part_size = st.number_input("Part size (symbols per ZIP)", min_value=10, max_value=2000, value=300, step=10)
with c3:
    delay_sec = st.number_input("Delay between requests (s)", min_value=0.0, max_value=5.0, value=0.02, step=0.01)

retries = st.number_input("Retries per request", min_value=0, max_value=5, value=2, step=1)

# try to extract api_key from client
client = st.session_state.get("client")
api_key = get_api_session_key_from_client(client)
if not api_key:
    st.info("API session key not found in client. Paste your Definedge api_session_key below (will be used to call history API).")
    api_key = st.text_input("Definedge API Session Key (Authorization header)", type="password")

# chunk into parts
parts = chunk_df(df_filtered.reset_index(drop=True), int(part_size))
num_parts = len(parts)
st.subheader(f"Parts: {num_parts} (approx. {part_size} symbols per part)")

# part buttons grid
cols_per_row = 8 if num_parts >= 8 else max(3, num_parts)
rows_needed = (num_parts + cols_per_row - 1) // cols_per_row

part_clicked = None
idx = 0
for _ in range(rows_needed):
    cols = st.columns(cols_per_row)
    for c in cols:
        if idx < num_parts:
            label = f"Part {idx+1} ({len(parts[idx])})"
            if c.button(label, key=f"part_btn_{idx+1}"):
                part_clicked = idx
        idx += 1

download_area = st.empty()

# If part clicked -> build or serve cached zip
if part_clicked is not None:
    cache_key = ("part_zip", part_clicked, days_back, part_size, delay_sec, retries)
    if cache_key in st.session_state["_zip_cache"]:
        zip_bytes = st.session_state["_zip_cache"][cache_key]
        st.success(f"ZIP for Part {part_clicked+1} is ready (from cache).")
        download_area.download_button(
            label=f"⬇️ Download Part {part_clicked+1} (ZIP)",
            data=zip_bytes,
            file_name=f"nse_daily_part_{part_clicked+1:02d}.zip",
            mime="application/zip"
        )
    else:
        st.info(f"Building ZIP for Part {part_clicked+1} (this will fetch {len(parts[part_clicked])} symbols)...")
        try:
            zip_buf = build_zip_for_rows(parts[part_clicked], days_back, api_key, ALLOWED_SEGMENT,
                                         delay_sec=float(delay_sec), retries=int(retries))
            zip_bytes = zip_buf.getvalue()
            st.session_state["_zip_cache"][cache_key] = zip_bytes
            download_area.download_button(
                label=f"⬇️ Download Part {part_clicked+1} (ZIP)",
                data=zip_bytes,
                file_name=f"nse_daily_part_{part_clicked+1:02d}.zip",
                mime="application/zip"
            )
            st.success("Part ZIP ready.")
        except Exception as e:
            st.error(f"Failed to build ZIP for part {part_clicked+1}: {e}")
            st.text(traceback.format_exc())

st.markdown("---")
st.warning("**Download ALL**: building one ZIP for all filtered symbols can be slow and memory-heavy. Use parts for large data.", icon="⚠️")
if st.button("⬇️ Build & Download ALL (one ZIP)"):
    cache_key_all = ("all_zip", days_back, part_size, delay_sec, retries)
    if cache_key_all in st.session_state["_zip_cache"]:
        st.success("ALL ZIP ready (from cache).")
        st.download_button(
            label="⬇️ Download ALL (ZIP)",
            data=st.session_state["_zip_cache"][cache_key_all],
            file_name="nse_daily_all.zip",
            mime="application/zip"
        )
    else:
        st.info(f"Building ALL ZIP for {len(df_filtered)} symbols...")
        try:
            zip_buf = build_zip_for_rows(df_filtered, days_back, api_key, ALLOWED_SEGMENT,
                                         delay_sec=float(delay_sec), retries=int(retries))
            zip_bytes = zip_buf.getvalue()
            st.session_state["_zip_cache"][cache_key_all] = zip_bytes
            st.download_button(
                label="⬇️ Download ALL (ZIP)",
                data=zip_bytes,
                file_name="nse_daily_all.zip",
                mime="application/zip"
            )
            st.success("ALL ZIP ready.")
        except Exception as e:
            st.error(f"Failed to build ALL ZIP: {e}")
            st.text(traceback.format_exc())

# small preview of filtered symbols
with st.expander("Preview filtered symbols (first 100)"):
    preview_cols = [c for c in ["SEGMENT","INSTRUMENT","TRADINGSYM","SYMBOL","TOKEN","COMPANY"] if c in df_filtered.columns]
    st.dataframe(df_filtered[preview_cols].head(100), use_container_width=True)

st.info("Notes: The page will cache per-token CSVs and built ZIPs for the active session to avoid re-downloading repeatedly. Adjust 'Delay between requests' and 'Retries' if you hit rate-limits or transient errors.")
