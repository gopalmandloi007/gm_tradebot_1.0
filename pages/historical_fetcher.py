# pages/historical_fetcher.py
import streamlit as st
import pandas as pd
import io
import os
import zipfile
import time
import requests
import traceback
import re
from datetime import datetime, timedelta

st.set_page_config(layout="wide")
st.title("📥 Historical Fetcher — Definedge (NSE multi-symbol, last N years)")

# -------------------------
# Robust CSV -> DataFrame parser (handles many date formats including ddMMyyyyHHmm)
# -------------------------
def _clean_dt_str(s: pd.Series) -> pd.Series:
    sc = s.astype(str).str.strip()
    sc = sc.str.replace(r'\.0+$', '', regex=True)
    sc = sc.str.replace(r'["\']', '', regex=True)
    sc = sc.str.replace(r'\s+', '', regex=True)
    return sc

def _looks_like_ddmmyyyy_hhmm(val: str) -> bool:
    return bool(re.fullmatch(r'\d{12}', val)) and 1 <= int(val[0:2]) <= 31 and 1 <= int(val[2:4]) <= 12 and 1900 <= int(val[4:8]) <= 2100

def _looks_like_ddmmyyyy(val: str) -> bool:
    return bool(re.fullmatch(r'\d{8}', val)) and 1 <= int(val[0:2]) <= 31 and 1 <= int(val[2:4]) <= 12 and 1900 <= int(val[4:8]) <= 2100

def _looks_like_epoch_seconds(val: str) -> bool:
    return bool(re.fullmatch(r'\d{10}', val))

def _looks_like_epoch_millis(val: str) -> bool:
    return bool(re.fullmatch(r'\d{13}', val))

def read_hist_csv_to_df(hist_csv: str) -> pd.DataFrame:
    """
    Robust parser for Definedge historical CSV (no header or with header).
    Returns DataFrame with columns: DateTime, Date, DateStr, Open, High, Low, Close, Volume (if available).
    Dedupes per calendar day keeping the last intraday row.
    """
    if not isinstance(hist_csv, str) or not hist_csv.strip():
        return pd.DataFrame()

    txt = hist_csv.strip()
    lines = txt.splitlines()
    if not lines:
        return pd.DataFrame()

    first_line = lines[0].lower()
    header_indicators = ("date", "datetime", "open", "high", "low", "close", "volume", "oi", "timestamp")
    use_header = any(h in first_line for h in header_indicators)

    # read CSV
    try:
        if use_header:
            df = pd.read_csv(io.StringIO(txt))
        else:
            df = pd.read_csv(io.StringIO(txt), header=None)
    except Exception:
        try:
            df = pd.read_csv(io.StringIO(txt), header=None, delim_whitespace=True)
        except Exception:
            return pd.DataFrame()

    cols = [str(c).lower() for c in df.columns.astype(str)]
    if any("date" in c or "time" in c for c in cols):
        col_map = {}
        for c in df.columns:
            lc = str(c).lower()
            if "date" in lc or "time" in lc:
                col_map[c] = "DateTime"
            elif lc.startswith("open"):
                col_map[c] = "Open"
            elif lc.startswith("high"):
                col_map[c] = "High"
            elif lc.startswith("low"):
                col_map[c] = "Low"
            elif lc.startswith("close"):
                col_map[c] = "Close"
            elif "volume" in lc:
                col_map[c] = "Volume"
            elif lc == "oi":
                col_map[c] = "OI"
        df = df.rename(columns=col_map)
    else:
        # assume standard positions
        if df.shape[1] >= 6:
            if df.shape[1] == 7:
                df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume", "OI"]
            else:
                df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]
        else:
            return pd.DataFrame()

    if "DateTime" not in df.columns:
        return pd.DataFrame()

    # parse DateTime robustly
    series = _clean_dt_str(df["DateTime"])
    dt = pd.Series([pd.NaT] * len(series), index=series.index, dtype="datetime64[ns]")

    sample = series.dropna()
    n = len(sample)
    if n == 0:
        return pd.DataFrame()

    n_ddmmhh = sample.apply(lambda v: _looks_like_ddmmyyyy_hhmm(v)).sum()
    n_ddmm = sample.apply(lambda v: _looks_like_ddmmyyyy(v)).sum()

    # try ddMMyyyyHHmm first if many look like that
    if n_ddmmhh >= max(1, int(0.35 * n)):
        parsed = pd.to_datetime(series, format="%d%m%Y%H%M", errors="coerce")
        dt = dt.fillna(parsed)

    # then ddMMyyyy
    if n_ddmm >= max(1, int(0.35 * n)):
        parsed = pd.to_datetime(series, format="%d%m%Y", errors="coerce")
        dt = dt.fillna(parsed)

    # explicit formats
    if dt.isna().any():
        formats_to_try = [
            "%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y", "%d/%m/%Y", "%d/%m/%Y %H:%M",
            "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
            "%d%m%Y%H%M", "%d%m%Y"
        ]
        for fmt in formats_to_try:
            if not dt.isna().any():
                break
            parsed = pd.to_datetime(series, format=fmt, dayfirst=True, errors="coerce")
            dt = dt.fillna(parsed)

    # pandas infer
    if dt.isna().any():
        parsed = pd.to_datetime(series, dayfirst=True, infer_datetime_format=True, errors="coerce")
        dt = dt.fillna(parsed)

    # epoch heuristics last
    if dt.isna().any():
        def try_epoch_parse(v):
            if not isinstance(v, str) or not v.isdigit():
                return pd.NaT
            if _looks_like_epoch_millis(v):
                return pd.to_datetime(int(v), unit="ms", errors="coerce")
            if _looks_like_epoch_seconds(v):
                return pd.to_datetime(int(v), unit="s", errors="coerce")
            return pd.NaT
        parsed_epoch = series.apply(lambda v: try_epoch_parse(v))
        dt = dt.fillna(parsed_epoch)

    # fallback
    if dt.isna().any():
        parsed = pd.to_datetime(series, infer_datetime_format=True, errors="coerce")
        dt = dt.fillna(parsed)

    df["DateTime"] = dt
    df = df.dropna(subset=["DateTime"]).copy()
    if df.empty:
        return pd.DataFrame()

    # numeric conversion
    for col in ("Open", "High", "Low", "Close", "Volume", "OI"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Normalize to daily (calendar day) and keep last intraday record per day
    df["Date"] = df["DateTime"].dt.normalize()
    df = df.sort_values("DateTime").drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)
    df["DateStr"] = df["Date"].dt.strftime("%Y-%m-%d")

    cols_keep = [c for c in ["DateTime", "Date", "DateStr", "Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    return df[cols_keep].copy()

# -------------------------
# Master download & loader
# -------------------------
MASTER_URLS = {
    "NSE Cash (nsecash.zip)": "https://app.definedgesecurities.com/public/nsecash.zip",
    "NSE FNO (nsefno.zip)": "https://app.definedgesecurities.com/public/nsefno.zip",
    "All master (allmaster.zip)": "https://app.definedgesecurities.com/public/allmaster.zip"
}

@st.cache_data(show_spinner=False)
def download_and_load_master(url: str) -> pd.DataFrame:
    """
    Download master zip from Definedge public URL and return master DataFrame.
    """
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    # find first .csv file inside
    csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]
    if not csv_names:
        raise RuntimeError("No CSV found in master zip")
    csv_name = csv_names[0]
    raw = z.read(csv_name)
    # read csv as text
    df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
    # normalize column names
    df.columns = [c.strip() for c in df.columns]
    # try to map required fields
    cols = {c.upper(): c for c in df.columns}
    def safe_col(*cands):
        for c in cands:
            if c.upper() in cols:
                return cols[c.upper()]
        return None
    trad_col = safe_col("TRADINGSYM", "TRADINGSYMBOL", "SYMBOL")
    seg_col = safe_col("SEGMENT")
    token_col = safe_col("TOKEN")
    # Ensure canonical columns exist
    if trad_col:
        df = df.rename(columns={trad_col: "TRADINGSYM"})
    else:
        df["TRADINGSYM"] = ""
    if seg_col:
        df = df.rename(columns={seg_col: "SEGMENT"})
    else:
        df["SEGMENT"] = ""
    if token_col:
        df = df.rename(columns={token_col: "TOKEN"})
    else:
        df["TOKEN"] = ""
    # Keep minimal columns
    df = df[["SEGMENT", "TOKEN", "TRADINGSYM"]].copy()
    # normalize content
    df["SEGMENT"] = df["SEGMENT"].astype(str).str.strip().str.upper()
    df["TRADINGSYM"] = df["TRADINGSYM"].astype(str).str.strip()
    df["TOKEN"] = df["TOKEN"].astype(str).str.strip()
    return df

# -------------------------
# Helper: token lookup
# -------------------------
def token_for_symbol(master_df: pd.DataFrame, symbol: str) -> str:
    row = master_df[master_df["TRADINGSYM"] == symbol]
    if not row.empty:
        return str(row.iloc[0]["TOKEN"])
    return ""

# -------------------------
# UI: controls
# -------------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Please login first (Login page). The Definedge client must be in st.session_state['client'].")
    st.stop()

st.sidebar.header("Master & Fetch options")
master_choice = st.sidebar.selectbox("Which master file to download", list(MASTER_URLS.keys()), index=0)
years_back = st.sidebar.number_input("Years back (calendar years)", min_value=1, max_value=20, value=5)
append_today = st.sidebar.checkbox("Append today's live quote (optional)", value=True)
rate_sleep = st.sidebar.number_input("Seconds between API calls (rate-limit)", min_value=0.0, max_value=5.0, value=0.5, step=0.1)
buffer_days = st.sidebar.number_input("Buffer days for historical request", min_value=10, max_value=120, value=40)
show_raw_hist = st.sidebar.checkbox("Show raw historical CSV (debug)", value=False)

# Download and show master
with st.spinner("Downloading master..."):
    try:
        master_df = download_and_load_master(MASTER_URLS[master_choice])
    except Exception as e:
        st.error(f"Failed to download/load master: {e}")
        st.stop()

# Normalize segment names
master_df["SEGMENT"] = master_df["SEGMENT"].astype(str).str.strip().str.upper()

# Allow NSE CASH, NSE-EQ, etc.
nse_df = master_df[master_df["SEGMENT"].str.contains("NSE")].copy()

if nse_df.empty:
    st.error("⚠️ No NSE rows found in master. Please check the master file content.")
    st.dataframe(master_df.head(20))  # show sample for debug
    st.stop()

st.sidebar.markdown(f"🔹 NSE symbols in master: **{len(nse_df)}**")

# symbol search & multiselect
search = st.sidebar.text_input("Search symbols (substring filter)", value="")
candidates = sorted(nse_df["TRADINGSYM"].unique())
if search:
    candidates = [s for s in candidates if search.lower() in s.lower()]

# default selection logic: prefer NIFTY 500 symbol if present else top 20 samples
default_selection = []
for s in candidates:
    if "NIFTY" in s.upper() and "500" in s.upper():
        default_selection = [s]; break
if not default_selection:
    default_selection = candidates[:20]  # first 20 by master order

selected_symbols = st.sidebar.multiselect("Select NSE symbols to fetch", options=candidates, default=default_selection)

if not selected_symbols:
    st.info("Please select one or more symbols from the sidebar to fetch historical data.")
    st.stop()

# main action
if st.button("⬇️ Fetch historical and prepare ZIP"):
    years = int(years_back)
    days_needed = int(years * 365)  # approximate
    today = datetime.today()
    start_date_cutoff = (today - timedelta(days=years * 365)).date()

    progress = st.progress(0)
    status = st.empty()
    csv_map = {}
    summary = []

    total = len(selected_symbols)
    for idx, sym in enumerate(selected_symbols, start=1):
        status.info(f"Fetching ({idx}/{total}): {sym}")
        try:
            token = token_for_symbol(nse_df, sym)
            if not token:
                raise RuntimeError("Token not found in master for symbol")

            # build from/to with buffer
            frm_dt = (today - timedelta(days=days_needed + int(buffer_days)))
            frm = frm_dt.strftime("%d%m%Y%H%M")
            to = today.strftime("%d%m%Y%H%M")

            # call historical API
            raw_csv = client.historical_csv(segment="NSE", token=str(token), timeframe="day", frm=frm, to=to)
            if not raw_csv or not str(raw_csv).strip():
                raise RuntimeError("Historical API returned empty for this token")

            # optional debug show
            if show_raw_hist:
                st.text_area(f"Raw CSV for {sym} (first 4000 chars)", str(raw_csv)[:4000], height=180)

            df_hist = read_hist_csv_to_df(str(raw_csv))
            if df_hist.empty:
                raise RuntimeError("Parsed historical CSV is empty or failed to parse")

            # filter to cutoff (keep dates >= start_date_cutoff)
            df_hist = df_hist[df_hist["Date"] >= pd.to_datetime(start_date_cutoff)].sort_values("Date").reset_index(drop=True)

            # Optionally append today's live quote (safe: only if quote returns valid ltp)
            if append_today:
                try:
                    q = client.get_quotes(exchange="NSE", token=str(token))
                    if isinstance(q, dict):
                        q_open = float(q.get("day_open") or q.get("open") or 0)
                        q_high = float(q.get("day_high") or q.get("high") or 0)
                        q_low  = float(q.get("day_low") or q.get("low") or 0)
                        q_close = float(q.get("ltp") or q.get("last_price") or 0)
                        q_vol = float(q.get("volume") or q.get("vol") or 0)
                        if q_close and q_close > 0:
                            today_norm = pd.to_datetime(today.date())
                            today_str = today_norm.strftime("%Y-%m-%d")
                            today_row = pd.DataFrame([{
                                "DateTime": pd.to_datetime(datetime.now()),
                                "Date": today_norm,
                                "DateStr": today_str,
                                "Open": q_open,
                                "High": q_high,
                                "Low": q_low,
                                "Close": q_close,
                                "Volume": q_vol
                            }])
                            # remove existing today row then concat using pd.concat
                            df_hist = pd.concat([df_hist[df_hist["Date"] < today_norm], today_row], ignore_index=True)
                except Exception:
                    # ignore append failures for overall run
                    pass

            # final numeric enforcement & cleaning
            for c in ["Open", "High", "Low", "Close", "Volume"]:
                if c in df_hist.columns:
                    df_hist[c] = pd.to_numeric(df_hist[c], errors="coerce")
            df_hist = df_hist.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)

            # store CSV bytes
            csv_bytes = df_hist.to_csv(index=False).encode("utf-8")
            csv_map[sym] = csv_bytes

            summary.append({
                "symbol": sym,
                "token": token,
                "rows": len(df_hist),
                "start": df_hist["Date"].min().strftime("%Y-%m-%d") if not df_hist.empty else None,
                "end": df_hist["Date"].max().strftime("%Y-%m-%d") if not df_hist.empty else None,
                "status": "OK"
            })
        except Exception as e:
            summary.append({
                "symbol": sym,
                "token": token if 'token' in locals() else None,
                "rows": 0,
                "start": None,
                "end": None,
                "status": f"ERROR: {e}"
            })
            st.error(f"Failed for {sym}: {e}")
            if show_raw_hist:
                st.text(traceback.format_exc())

        progress.progress(int(idx/total * 100))
        time.sleep(rate_sleep)  # rate limit between calls

    # summary
    st.subheader("Fetch Summary")
    summary_df = pd.DataFrame(summary)
    st.dataframe(summary_df, use_container_width=True)

    # build zip
    if csv_map:
        zip_buf = io.BytesIO()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"definedge_nse_{years_back}yrs_{stamp}.zip"
        with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
            for sym, b in csv_map.items():
                fname = f"{sym}_historical.csv"
                z.writestr(fname, b)
        zip_buf.seek(0)
        st.success(f"Prepared ZIP with {len(csv_map)} CSV files")
        st.download_button("⬇️ Download ZIP (all symbols)", zip_buf.getvalue(), file_name=zip_name, mime="application/zip")

        # also individual downloads
        st.markdown("#### Individual CSV downloads")
        for sym, b in csv_map.items():
            st.download_button(f"Download {sym}.csv", b, file_name=f"{sym}_historical.csv", mime="text/csv")
    else:
        st.warning("No CSV files prepared (all failed).")

    status.info("Done.")
