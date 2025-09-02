# pages/historical_fetcher.py
import streamlit as st
import pandas as pd
import numpy as np
import io
import os
import zipfile
import time
import traceback
import re
from datetime import datetime, timedelta

st.set_page_config(layout="wide")
st.title("📥 Historical Data Fetcher — NSE (multi-symbol, 5 years)")

# -------------------------
# Robust CSV -> DataFrame reader (same safe parser used earlier)
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
    """Robust parser for historical CSV text -> DataFrame with Date normalized per-day."""
    if not isinstance(hist_csv, str) or not hist_csv.strip():
        return pd.DataFrame()

    txt = hist_csv.strip()
    lines = txt.splitlines()
    if not lines:
        return pd.DataFrame()

    first_line = lines[0].lower()
    header_indicators = ("date", "datetime", "open", "high", "low", "close", "volume", "oi", "timestamp")
    use_header = any(h in first_line for h in header_indicators)

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
        if df.shape[1] >= 6:
            if df.shape[1] == 7:
                df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume", "OI"]
            else:
                df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]
        else:
            return pd.DataFrame()

    if "DateTime" not in df.columns:
        return pd.DataFrame()

    series_raw = df["DateTime"]
    series = _clean_dt_str(series_raw)
    dt = pd.Series([pd.NaT] * len(series), index=series.index, dtype="datetime64[ns]")

    sample = series.dropna()
    n = len(sample)
    if n == 0:
        return pd.DataFrame()

    n_ddmmhh = sample.apply(lambda v: _looks_like_ddmmyyyy_hhmm(v)).sum()
    n_ddmm = sample.apply(lambda v: _looks_like_ddmmyyyy(v)).sum()

    if n_ddmmhh >= max(1, int(0.35 * n)):
        parsed = pd.to_datetime(series, format="%d%m%Y%H%M", errors="coerce")
        dt = dt.fillna(parsed)

    if n_ddmm >= max(1, int(0.35 * n)):
        parsed = pd.to_datetime(series, format="%d%m%Y", errors="coerce")
        dt = dt.fillna(parsed)

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

    if dt.isna().any():
        parsed = pd.to_datetime(series, dayfirst=True, infer_datetime_format=True, errors="coerce")
        dt = dt.fillna(parsed)

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

    if dt.isna().any():
        parsed = pd.to_datetime(series, infer_datetime_format=True, errors="coerce")
        dt = dt.fillna(parsed)

    df["DateTime"] = dt
    df = df.dropna(subset=["DateTime"]).copy()
    if df.empty:
        return pd.DataFrame()

    for col in ("Open", "High", "Low", "Close", "Volume", "OI"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Date"] = df["DateTime"].dt.normalize()
    df = df.sort_values("DateTime").drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)
    df["DateStr"] = df["Date"].dt.strftime("%Y-%m-%d")
    cols_keep = [c for c in ["DateTime", "Date", "DateStr", "Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    return df[cols_keep].copy()

# -------------------------
# Load master symbols (NSE-only)
# -------------------------
@st.cache_data(show_spinner=False)
def load_master(master_csv_path="data/master/allmaster.csv"):
    # Attempt to read path, else return empty df
    if os.path.exists(master_csv_path):
        mdf = pd.read_csv(master_csv_path, dtype=str)
    else:
        return pd.DataFrame()
    # Normalize column names to uppercase keys
    mdf.columns = [c.strip() for c in mdf.columns]
    colmap = {c: c for c in mdf.columns}
    # common names
    names_upper = {c.upper(): c for c in mdf.columns}
    # expected columns might be TRADINGSYM, SEGMENT, TOKEN
    # create canonical columns
    def get_col(*candidates):
        for cand in candidates:
            if cand in names_upper:
                return names_upper[cand]
        return None
    trad_col = get_col("TRADINGSYM", "TRADINGSYMBOL", "TRADSYM", "SYMBOL", "tradingsym")
    seg_col = get_col("SEGMENT", "segment")
    token_col = get_col("TOKEN", "token")
    # fallback: try lowercase equivalents
    if trad_col is None:
        candidates = [c for c in mdf.columns if "trad" in c.lower() or "symbol" in c.lower()]
        trad_col = candidates[0] if candidates else mdf.columns[0]
    if seg_col is None:
        candidates = [c for c in mdf.columns if "seg" in c.lower()]
        seg_col = candidates[0] if candidates else None
    if token_col is None:
        candidates = [c for c in mdf.columns if "token" in c.lower()]
        token_col = candidates[0] if candidates else None

    mdf = mdf.rename(columns={trad_col: "TRADINGSYM"})
    if seg_col:
        mdf = mdf.rename(columns={seg_col: "SEGMENT"})
    else:
        mdf["SEGMENT"] = "NSE"  # default if missing
    if token_col:
        mdf = mdf.rename(columns={token_col: "TOKEN"})
    else:
        mdf["TOKEN"] = ""

    mdf["TRADINGSYM"] = mdf["TRADINGSYM"].astype(str)
    mdf["SEGMENT"] = mdf["SEGMENT"].astype(str)
    mdf["TOKEN"] = mdf["TOKEN"].astype(str)
    return mdf[["TRADINGSYM", "SEGMENT", "TOKEN"]]

# -------------------------
# Helper: get token by trading symbol
# -------------------------
def token_for_symbol(master_df, symbol):
    row = master_df[master_df["TRADINGSYM"] == symbol]
    if not row.empty:
        return row.iloc[0]["TOKEN"]
    return ""

# -------------------------
# Historical fetch wrapper using Definedge client
# -------------------------
def fetch_symbol_history(client, segment, token, days, timeframe="day", buffer_days=30, show_raw=False):
    """
    Calls client's historical_csv and returns parsed DataFrame (or empty DF).
    - client: Definedge client (must have historical_csv(segment, token, timeframe, frm, to))
    - days: how many most recent trading days to return
    """
    today = datetime.today()
    frm = (today - timedelta(days=days + buffer_days)).strftime("%d%m%Y%H%M")
    to = today.strftime("%d%m%Y%H%M")
    try:
        raw = client.historical_csv(segment=segment, token=token, timeframe=timeframe, frm=frm, to=to)
    except Exception as e:
        raise RuntimeError(f"historical_csv API error: {e}")

    raw_text = str(raw) if raw is not None else ""
    if show_raw:
        st.text_area("Raw historical CSV (first 4000 chars)", raw_text[:4000], height=220)
    df = read_hist_csv_to_df(raw_text)
    if df.empty:
        return pd.DataFrame()
    # return last `days` calendar rows (most recent)
    df = df.sort_values("Date").tail(days).reset_index(drop=True)
    return df

# -------------------------
# UI inputs
# -------------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in — go to the Login page and complete login first.")
    st.stop()

master_df = load_master()
if master_df.empty:
    st.warning("Master file not found at `data/master/allmaster.csv`. Upload a master CSV (format: TRADINGSYM, SEGMENT, TOKEN).")
    uploaded = st.file_uploader("Upload master CSV (optional)", type=["csv"])
    if uploaded:
        try:
            mdf = pd.read_csv(uploaded, dtype=str)
            # save temporarily to cache by writing to local path (not committed to git)
            os.makedirs("data/master", exist_ok=True)
            uploaded_path = "data/master/allmaster.csv"
            mdf.to_csv(uploaded_path, index=False)
            st.success("Master CSV uploaded and saved to data/master/allmaster.csv")
            master_df = load_master()  # reload cached function
        except Exception as e:
            st.error(f"Failed to read uploaded CSV: {e}")
            st.stop()
    else:
        st.stop()

# Filter NSE only
nse_df = master_df[master_df["SEGMENT"].str.upper() == "NSE"].copy()
if nse_df.empty:
    st.error("No NSE symbols found in master file.")
    st.stop()

# symbol selector
st.sidebar.header("Symbol selection (NSE only)")
search = st.sidebar.text_input("Search symbol (substring)", value="")
candidates = sorted(nse_df["TRADINGSYM"].unique())
if search:
    candidates = [s for s in candidates if search.lower() in s.lower()]

# default select: NIFTY 500 if present, else top 10
default_selection = []
for s in candidates:
    if "NIFTY" in s.upper() and "500" in s.upper():
        default_selection = [s]
        break
if not default_selection:
    default_selection = candidates[:10]

selected_symbols = st.sidebar.multiselect("Select symbols (multi)", options=candidates, default=default_selection)

years = st.sidebar.number_input("Years back (history)", min_value=1, max_value=20, value=5, step=1)
days_back = int(years * 365)  # approximate days
timeframe = st.sidebar.selectbox("Timeframe", ["day"], index=0, help="Daily candles for long-term backtesting")
append_today = st.sidebar.checkbox("Append today's live quote (optional)", value=True)
rate_sleep = st.sidebar.number_input("Seconds between API calls (rate-limit)", min_value=0.0, max_value=5.0, value=0.5, step=0.1)
show_raw = st.sidebar.checkbox("Show raw historical CSV (debug)", value=False)

if not selected_symbols:
    st.info("Select one or more symbols from the sidebar to fetch historical data.")
    st.stop()

# Main action button
if st.button("Fetch historical data & build ZIP"):
    results = []
    csv_buffers = {}
    errors = {}
    total = len(selected_symbols)
    progress = st.progress(0)
    status_text = st.empty()
    start_time = datetime.now()

    for idx, sym in enumerate(selected_symbols, start=1):
        status_text.info(f"Processing ({idx}/{total}): {sym}")
        try:
            token = token_for_symbol(nse_df, sym)
            if not token or str(token).strip() == "":
                raise RuntimeError("Token missing for symbol in master file")

            # fetch
            df_hist = fetch_symbol_history(client, "NSE", token, days_back, timeframe=timeframe, buffer_days=40, show_raw=show_raw)
            if df_hist.empty:
                raise RuntimeError("No historical rows returned / parse failed")

            # Optionally append today's quote (safe: only when LTP available)
            if append_today:
                try:
                    q = client.get_quotes(exchange="NSE", token=token)
                    if isinstance(q, dict):
                        # many brokers return ltp as string in root
                        q_open = float(q.get("day_open") or q.get("open") or 0)
                        q_high = float(q.get("day_high") or q.get("high") or 0)
                        q_low  = float(q.get("day_low") or q.get("low") or 0)
                        q_close = float(q.get("ltp") or q.get("last_price") or 0)
                        q_vol = float(q.get("volume") or q.get("vol") or 0)
                        today_norm = pd.to_datetime(datetime.today().date())
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
                        # merge: drop existing today then concat
                        df_hist = pd.concat([df_hist[df_hist["Date"] < today_norm], today_row], ignore_index=True)
                except Exception:
                    # do not fail overall for quote append
                    pass

            # final clean: ensure Close numeric and sorted
            for c in ["Open","High","Low","Close","Volume"]:
                if c in df_hist.columns:
                    df_hist[c] = pd.to_numeric(df_hist[c], errors="coerce")
            df_hist = df_hist.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)

            # Keep only last (years*~252 trading days) but user asked for calendar days approximation; we keep what's returned
            # Save CSV bytes in-memory
            csv_buf = df_hist.to_csv(index=False).encode("utf-8")
            csv_buffers[sym] = csv_buf

            results.append({
                "symbol": sym,
                "rows": len(df_hist),
                "start_date": df_hist["Date"].min().strftime("%Y-%m-%d") if not df_hist.empty else None,
                "end_date": df_hist["Date"].max().strftime("%Y-%m-%d") if not df_hist.empty else None,
                "status": "OK"
            })

        except Exception as e:
            errors[sym] = str(e)
            results.append({
                "symbol": sym,
                "rows": 0,
                "start_date": None,
                "end_date": None,
                "status": f"ERROR: {e}"
            })

        # progress sleep & update
        progress.progress(int(idx/total * 100))
        time.sleep(rate_sleep)

    end_time = datetime.now()
    status_text.success(f"Completed fetch — {len(results)} symbols in {round((end_time-start_time).total_seconds(),1)}s")

    # Show summary table
    summary_df = pd.DataFrame(results)
    st.subheader("Fetch Summary")
    st.dataframe(summary_df, use_container_width=True)

    # Show errors if any
    if errors:
        st.error(f"{len(errors)} symbol(s) failed. See details below.")
        for sym, msg in errors.items():
            st.write(f"- {sym}: {msg}")

    # Preview first successful symbol (if exists)
    successful = [s for s in results if s.get("status") == "OK"]
    if successful:
        preview_sym = successful[0]["symbol"]
        st.subheader(f"Preview: {preview_sym}")
        st.dataframe(pd.read_csv(io.BytesIO(csv_buffers[preview_sym])), use_container_width=True)

    # Build ZIP in-memory
    if csv_buffers:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
            for sym, b in csv_buffers.items():
                # file name safe: replace spaces/slashes
                fname = f"{sym}_historical.csv"
                z.writestr(fname, b)
        zip_buf.seek(0)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"historical_nse_{years}yrs_{stamp}.zip"

        st.markdown("---")
        st.success(f"Prepared ZIP with {len(csv_buffers)} CSV(s). Download below.")
        st.download_button("⬇️ Download ZIP (all symbols)", zip_buf.getvalue(), file_name=zip_filename, mime="application/zip")

        # Also provide individual CSV downloads
        st.markdown("#### Individual CSV downloads")
        for sym, b in csv_buffers.items():
            st.download_button(f"Download {sym}.csv", b, file_name=f"{sym}_historical.csv", mime="text/csv")
    else:
        st.warning("No CSVs prepared for download (all failed).")

