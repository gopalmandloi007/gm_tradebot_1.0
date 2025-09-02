import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta
import traceback
import re

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Data Downloader — Clean Dates & CSV")

# ------------------------- Utilities -------------------------
def _clean_dt_str(s: pd.Series) -> pd.Series:
    sc = s.astype(str).str.strip()
    sc = sc.str.replace(r'\.0+$', '', regex=True)
    sc = sc.str.replace(r'["\']', '', regex=True)
    sc = sc.str.replace(r'\s+', '', regex=True)
    return sc

def _looks_like_ddmmyyyy_hhmm(val: str) -> bool:
    return bool(re.fullmatch(r'\d{12}', val))

def _looks_like_ddmmyyyy(val: str) -> bool:
    return bool(re.fullmatch(r'\d{8}', val))

def read_hist_csv_to_df(hist_csv: str) -> pd.DataFrame:
    if not hist_csv.strip():
        return pd.DataFrame()
    txt = hist_csv.strip()
    lines = txt.splitlines()
    if not lines:
        return pd.DataFrame()
    # header detection
    first_line = lines[0].lower()
    header_indicators = ("date","datetime","open","high","low","close","volume","oi","timestamp")
    use_header = any(h in first_line for h in header_indicators)
    try:
        df = pd.read_csv(io.StringIO(txt)) if use_header else pd.read_csv(io.StringIO(txt), header=None)
    except Exception:
        df = pd.read_csv(io.StringIO(txt), header=None, delim_whitespace=True)
    # map columns
    if df.shape[1] == 7:
        df.columns = ["DateTime","Open","High","Low","Close","Volume","OI"]
    elif df.shape[1] == 6:
        df.columns = ["DateTime","Open","High","Low","Close","Volume"]
    else:
        return pd.DataFrame()
    # clean DateTime
    series_raw = df["DateTime"]
    series = _clean_dt_str(series_raw)
    dt = pd.Series([pd.NaT]*len(series), index=series.index)
    n = len(series.dropna())
    if n == 0:
        return pd.DataFrame()
    n_ddmmhh = series.apply(lambda v: _looks_like_ddmmyyyy_hhmm(v)).sum()
    n_ddmm = series.apply(lambda v: _looks_like_ddmmyyyy(v)).sum()
    if n_ddmmhh >= max(1,int(0.35*n)):
        dt = pd.to_datetime(series, format="%d%m%Y%H%M", errors="coerce")
    if n_ddmm >= max(1,int(0.35*n)):
        dt = dt.fillna(pd.to_datetime(series, format="%d%m%Y", errors="coerce"))
    dt = dt.fillna(pd.to_datetime(series, dayfirst=True, infer_datetime_format=True, errors="coerce"))
    df["DateTime"] = dt
    df = df.dropna(subset=["DateTime"])
    # numeric conversion
    for col in ("Open","High","Low","Close","Volume","OI"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("DateTime").reset_index(drop=True)
    return df

# ------------------------- Fetch historical wrapper -------------------------
def fetch_historical(client, segment, token, days=365, buffer_days=30):
    today = datetime.today()
    frm = (today - timedelta(days=days+buffer_days)).strftime("%d%m%Y%H%M")
    to = today.strftime("%d%m%Y%H%M")
    try:
        raw = client.historical_csv(segment=segment, token=token, timeframe="day", frm=frm, to=to)
    except Exception as e:
        st.error(f"Historical API failed: {e}")
        return pd.DataFrame()
    df = read_hist_csv_to_df(str(raw))
    return df.sort_values("DateTime").tail(days).reset_index(drop=True)

# ------------------------- UI -------------------------
@st.cache_data
def load_master(path="data/master/allmaster.csv"):
    return pd.read_csv(path)

df_master = load_master()

segments = sorted(df_master["SEGMENT"].dropna().unique())
segment = st.selectbox("Exchange/Segment", segments, index=0)
segment_df = df_master[df_master["SEGMENT"] == segment]

symbols = list(segment_df["TRADINGSYM"].astype(str).unique())
stock_symbol = st.selectbox("Stock Trading Symbol", symbols, index=0)
stock_row = segment_df[segment_df["TRADINGSYM"] == stock_symbol].iloc[0]

days_back = st.number_input("Number of Days to fetch", min_value=20, max_value=2000, value=365, step=1)

if st.button("Fetch & Download Historical Data"):
    client = st.session_state.get("client")
    if not client:
        st.error("Client not logged in!")
        st.stop()
    try:
        df_hist = fetch_historical(client, stock_row["SEGMENT"], stock_row["TOKEN"], days=days_back)
        if df_hist.empty:
            st.warning("No data fetched.")
        else:
            st.dataframe(df_hist.tail(250), use_container_width=True)
            csv_bytes = df_hist.to_csv(index=False).encode("utf-8")
            st.download_button(label=f"Download OHLCV CSV ({stock_symbol})", data=csv_bytes,
                               file_name=f"ohlcv_{stock_symbol}.csv", mime="text/csv")
    except Exception as e:
        st.error(f"Error: {e}")
        st.text(traceback.format_exc())
