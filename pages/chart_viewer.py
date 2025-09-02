# paste this entire file in place of your current Streamlit page

import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, timedelta
import plotly.graph_objects as go
import traceback
import re

st.set_page_config(layout="wide")
st.title("📈 Candlestick, EMAs, Relative Strength & Volume — No Gaps (Fixed Dates)")

# -------------------------
# Utilities: robust CSV -> DataFrame (FIXED parser)
# -------------------------
def _clean_dt_str(s: pd.Series) -> pd.Series:
    """Clean common artifacts: trailing .0 from numeric CSV exports, quotes, whitespace."""
    sc = s.astype(str).str.strip()
    sc = sc.str.replace(r'\.0+$', '', regex=True)      # "020720250000.0" -> "020720250000"
    sc = sc.str.replace(r'["\']', '', regex=True)      # remove quotes
    sc = sc.str.replace(r'\s+', '', regex=True)        # remove stray spaces
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
    Robustly parse broker historical CSVs with many formats.
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

    # read CSV (flexible)
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

    # Map columns to canonical names
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
        # assume standard positions when header absent
        if df.shape[1] >= 6:
            if df.shape[1] == 7:
                df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume", "OI"]
            else:
                df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]
        else:
            return pd.DataFrame()

    if "DateTime" not in df.columns:
        return pd.DataFrame()

    # Clean DateTime strings
    series_raw = df["DateTime"]
    series = _clean_dt_str(series_raw)

    # Pre-allocate result dt Series
    dt = pd.Series([pd.NaT] * len(series), index=series.index, dtype="datetime64[ns]")

    # 1) Try ddmmyyyyHHMM or ddmmyyyy formats
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

    # try other formats, infer, epoch fallback...
    if dt.isna().any():
        parsed = pd.to_datetime(series, dayfirst=True, infer_datetime_format=True, errors="coerce")
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
# Fetch historical wrapper
# -------------------------
def fetch_historical(client, segment, token, days, buffer_days=30, show_raw=False):
    today = datetime.today()
    frm = (today - timedelta(days=days + buffer_days)).strftime("%d%m%Y%H%M")
    to = today.strftime("%d%m%Y%H%M")
    try:
        raw = client.historical_csv(segment=segment, token=token, timeframe="day", frm=frm, to=to)
    except Exception as e:
        st.error(f"Historical API failed: {e}")
        return pd.DataFrame()
    raw_text = str(raw) if raw is not None else ""
    if show_raw:
        st.text_area("Raw historical CSV (first 4000 chars)", raw_text[:4000], height=220)
    df = read_hist_csv_to_df(raw_text)
    if df.empty:
        return df
    df = df.sort_values("Date").tail(days).reset_index(drop=True)
    return df

# -------------------------
# Main UI code (shortened to show the fix area)
# -------------------------
if st.button("Show Chart"):
    try:
        client = st.session_state.get("client")
        if not client:
            st.error("Not logged in (client missing).")
            st.stop()

        df_stock = fetch_historical(client, "NSE", "26000", 250)
        if df_stock.empty:
            st.warning("No historical data")
            st.stop()

        # ✅ FIX: replace .append() with pd.concat()
        append_today_quote = True
        if append_today_quote:
            try:
                q = client.get_quotes("NSE", "26000")
                today_norm = pd.to_datetime(datetime.today().date())
                today_str = today_norm.strftime("%Y-%m-%d")
                today_row = pd.DataFrame([{
                    "DateTime": pd.to_datetime(datetime.now()),
                    "Date": today_norm,
                    "DateStr": today_str,
                    "Open": float(q.get("day_open") or 0),
                    "High": float(q.get("day_high") or 0),
                    "Low": float(q.get("day_low") or 0),
                    "Close": float(q.get("ltp") or 0),
                    "Volume": float(q.get("volume") or 0)
                }])

                df_stock = df_stock[df_stock["Date"] < today_norm]
                df_stock = pd.concat([df_stock, today_row], ignore_index=True).reset_index(drop=True)

            except Exception as e:
                st.warning(f"Failed to append today's quote: {e}")

        st.dataframe(df_stock.tail())

    except Exception as e:
        st.error(f"Error: {e}")
        st.text(traceback.format_exc())
