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
    sc = s.astype(str).str.strip()
    sc = sc.str.replace(r'\.0+$', '', regex=True)
    sc = sc.str.replace(r'["\']', '', regex=True)
    sc = sc.str.replace(r'\s+', '', regex=True)
    return sc

def _looks_like_ddmmyyyy_hhmm(val: str) -> bool:
    return bool(re.fullmatch(r'\d{12}', val)) and 1 <= int(val[0:2]) <= 31

def _looks_like_ddmmyyyy(val: str) -> bool:
    return bool(re.fullmatch(r'\d{8}', val)) and 1 <= int(val[0:2]) <= 31

def _looks_like_epoch_seconds(val: str) -> bool:
    return bool(re.fullmatch(r'\d{10}', val))

def _looks_like_epoch_millis(val: str) -> bool:
    return bool(re.fullmatch(r'\d{13}', val))

def read_hist_csv_to_df(hist_csv: str) -> pd.DataFrame:
    if not hist_csv.strip(): return pd.DataFrame()
    txt = hist_csv.strip()
    lines = txt.splitlines()
    if not lines: return pd.DataFrame()

    # auto-detect header
    first_line = lines[0].lower()
    header_indicators = ("date", "datetime", "open", "high", "low", "close", "volume", "oi", "timestamp")
    use_header = any(h in first_line for h in header_indicators)

    try:
        if use_header:
            df = pd.read_csv(io.StringIO(txt))
        else:
            df = pd.read_csv(io.StringIO(txt), header=None)
    except:
        return pd.DataFrame()

    # Map columns
    cols = [str(c).lower() for c in df.columns]
    col_map = {}
    for c in df.columns:
        lc = str(c).lower()
        if "date" in lc or "time" in lc: col_map[c] = "DateTime"
        elif lc.startswith("open"): col_map[c] = "Open"
        elif lc.startswith("high"): col_map[c] = "High"
        elif lc.startswith("low"): col_map[c] = "Low"
        elif lc.startswith("close"): col_map[c] = "Close"
        elif "volume" in lc: col_map[c] = "Volume"
        elif lc == "oi": col_map[c] = "OI"
    if col_map: df = df.rename(columns=col_map)
    else:
        if df.shape[1] >= 6:
            df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]

    # Clean DateTime
    series = _clean_dt_str(df["DateTime"])
    dt = pd.to_datetime(series, dayfirst=True, errors="coerce")
    df["DateTime"] = dt
    df = df.dropna(subset=["DateTime"])
    for col in ("Open","High","Low","Close","Volume","OI"):
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Date"] = df["DateTime"].dt.normalize()
    df = df.sort_values("DateTime").drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)
    df["DateStr"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df[["DateTime","Date","DateStr","Open","High","Low","Close","Volume"]]

    # -----------------------
# Prepare OHLCV CSV
# -----------------------
def prepare_ohlcv_for_download(df: pd.DataFrame) -> pd.DataFrame:
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    cols_keep = ["Date","Open","High","Low","Close","Volume"]
    return df[cols_keep].copy()

# -------------------------
# Fetch historical wrapper
# -------------------------
def fetch_historical_5yr(client, segment, token):
    today = datetime.today()
    frm = (today - timedelta(days=5*365 + 30)).strftime("%d%m%Y%H%M")
    to = today.strftime("%d%m%Y%H%M")
    try:
        raw = client.historical_csv(segment=segment, token=token, timeframe="day", frm=frm, to=to)
    except Exception as e:
        st.warning(f"Failed fetch for {token}: {e}")
        return pd.DataFrame()
    if not raw or not raw.strip(): return pd.DataFrame()
    return read_hist_csv_to_df(raw)

# -------------------------
# Load master & UI defaults (NSE, NIFTY 500)
# -------------------------
@st.cache_data
def load_master_symbols(master_csv_path="data/master/allmaster.csv"):
    return pd.read_csv(master_csv_path)

df_master = load_master_symbols()

# default segment index for 'NSE' if exists
segments = sorted(df_master["SEGMENT"].dropna().unique())
default_seg_index = 0
for i, s in enumerate(segments):
    if str(s).strip().upper() == "NSE":
        default_seg_index = i
        break

segment = st.selectbox("Exchange/Segment", segments, index=default_seg_index)
segment_df = df_master[df_master["SEGMENT"] == segment]

# default symbol: find 'NIFTY 500' substring case-insensitive
def_symbol = None
for s in segment_df["TRADINGSYM"].astype(str).unique():
    if "NIFTY" in s.upper() and "500" in s.upper():
        def_symbol = s
        break

symbols = list(segment_df["TRADINGSYM"].astype(str).unique())
default_symbol_index = symbols.index(def_symbol) if def_symbol in symbols else 0
stock_symbol = st.selectbox("Stock Trading Symbol", symbols, index=default_symbol_index)
stock_row = segment_df[segment_df["TRADINGSYM"] == stock_symbol].iloc[0]

# index selection for RS
index_candidates = df_master[
    df_master["INSTRUMENT"].astype(str).str.contains("INDEX", case=False, na=False) |
    df_master["TRADINGSYM"].astype(str).str.contains("NIFTY|SENSEX|BANKNIFTY|IDX|500|100", case=False, na=False)
].drop_duplicates("TRADINGSYM")
if index_candidates.empty:
    index_candidates = df_master
index_symbols = list(index_candidates["TRADINGSYM"].astype(str).unique())
# pick default index logically
def_idx_symbol = None
for s in index_symbols:
    if "NIFTY" in s.upper() and "500" in s.upper():
        def_idx_symbol = s; break
    if def_idx_symbol is None and "NIFTY" in s.upper():
        def_idx_symbol = s
default_idx_index = index_symbols.index(def_idx_symbol) if def_idx_symbol in index_symbols else 0
index_symbol = st.selectbox("Index Trading Symbol (for RS)", index_symbols, index=default_idx_index)
index_row = index_candidates[index_candidates["TRADINGSYM"] == index_symbol].iloc[0]

# UI controls
st.markdown("#### EMA Periods")
ema_periods = st.text_input("Enter EMA periods (comma separated)", value="10,20,50,100,200")
ema_periods = [int(x.strip()) for x in ema_periods.split(",") if x.strip().isdigit()]

days_back = st.number_input("Number of Days (candles to fetch)", min_value=20, max_value=2000, value=250, step=1)
rs_sma_period = st.number_input("RS SMA Period", min_value=2, max_value=500, value=20, step=1)

append_today_quote = st.checkbox("Append today's live quote (use quotes API)", value=False)
show_raw_hist = st.checkbox("Show raw historical CSV (debug)", value=False)

if st.button("Show Chart"):
    try:
        client = st.session_state.get("client")
        if not client:
            st.error("Not logged in (client missing).")
            st.stop()

        df_stock = fetch_historical(client, stock_row["SEGMENT"], stock_row["TOKEN"], days_back, buffer_days=30, show_raw=show_raw_hist)
        if df_stock.empty:
            st.warning(f"No historical data for: {stock_symbol}")
            st.stop()

        df_index = fetch_historical(client, index_row["SEGMENT"], index_row["TOKEN"], days_back, buffer_days=30, show_raw=False)
        if df_index.empty:
            st.warning(f"No historical data for index: {index_symbol}")
            st.stop()

        # Optionally append today's quote (replace any existing today row)
        if append_today_quote:
            try:
                q = client.get_quotes(exchange=stock_row["SEGMENT"], token=stock_row["TOKEN"])
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
                # drop existing today row and append
                df_stock = df_stock[df_stock["Date"] < today_norm].append(today_row, ignore_index=True).reset_index(drop=True)
            except Exception as e:
                st.warning(f"Failed to append today's quote: {e}")

        # numeric safety & drop NaN closes
        for c in ["Open", "High", "Low", "Close", "Volume"]:
            if c in df_stock.columns:
                df_stock[c] = pd.to_numeric(df_stock[c], errors="coerce")
        df_stock = df_stock.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)

        # ensure DateStr available
        if "DateStr" not in df_stock.columns:
            df_stock["DateStr"] = df_stock["Date"].dt.strftime("%Y-%m-%d")

        # Debug info
        st.info(f"Stock rows: {len(df_stock)} | Date range: {df_stock['Date'].min().date()} → {df_stock['Date'].max().date()}")
        st.info(f"Index rows: {len(df_index)} | Date range: {df_index['Date'].min().date()} → {df_index['Date'].max().date()}")

        # Calculate EMAs
        def ema(series, period):
            return series.ewm(span=period, adjust=False).mean()
        for p in ema_periods:
            df_stock[f"EMA_{p}"] = ema(df_stock["Close"], p)

        # Plot using categorical x (DateStr) to remove gaps
        x = df_stock["DateStr"].tolist()
        fig1 = go.Figure()
        fig1.add_trace(go.Candlestick(
            x=x,
            open=df_stock["Open"],
            high=df_stock["High"],
            low=df_stock["Low"],
            close=df_stock["Close"],
            name="OHLC",
            increasing_line_color='green',
            decreasing_line_color='red'
        ))
        for p in ema_periods:
            col = f"EMA_{p}"
            if col in df_stock.columns:
                fig1.add_trace(go.Scatter(x=x, y=df_stock[col], mode="lines", name=col, line=dict(width=1.2)))

        fig1.update_layout(
            title=f"{stock_symbol} — Candlestick (no gaps) + EMAs",
            xaxis=dict(type="category", title="Date (trading days only)"),
            yaxis=dict(title="Price"),
            height=650, template="plotly_white", margin=dict(l=10, r=10, t=40, b=10)
        )
        st.plotly_chart(fig1, use_container_width=True)

        # Volume bar (categorical x)
        fig_vol = go.Figure()
        fig_vol.add_trace(go.Bar(x=x, y=df_stock["Volume"].fillna(0), name="Volume"))
        fig_vol.update_layout(title=f"{stock_symbol} Volume (no gaps)", xaxis=dict(type="category"), height=300, template="plotly_white")
        st.plotly_chart(fig_vol, use_container_width=True)

        # Relative Strength (merge on calendar Date)
        df_stock_rs = df_stock[["Date", "DateStr", "Close"]].rename(columns={"Close": "StockClose"})
        df_index_rs = df_index[["Date", "Close"]].rename(columns={"Close": "IndexClose"})
        df_rs = pd.merge(df_stock_rs, df_index_rs, on="Date", how="inner").sort_values("Date").reset_index(drop=True)
        if df_rs.empty:
            st.warning("No overlapping dates between stock and index data for RS chart.")
        else:
            df_rs["RS"] = (df_rs["StockClose"] / df_rs["IndexClose"]) * 100
            df_rs["RS_SMA"] = df_rs["RS"].rolling(window=rs_sma_period, min_periods=1).mean()
            x_rs = df_rs["Date"].dt.strftime("%Y-%m-%d").tolist()
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=x_rs, y=df_rs["RS"], mode="lines", name="RS"))
            fig2.add_trace(go.Scatter(x=x_rs, y=df_rs["RS_SMA"], mode="lines", name=f"RS SMA {rs_sma_period}", line=dict(dash="dash")))
            fig2.update_layout(title=f"Relative Strength: {stock_symbol} vs {index_symbol}", xaxis=dict(type="category"), height=400, template="plotly_white")
            st.plotly_chart(fig2, use_container_width=True)

            # RS download
            st.markdown("#### Download Relative Strength Data")
            rs_display_cols = ["Date", "StockClose", "IndexClose", "RS", "RS_SMA"]
            st.dataframe(df_rs[rs_display_cols], use_container_width=True)
            csv_rs = df_rs[rs_display_cols].to_csv(index=False).encode("utf-8")
            st.download_button(label="Download RS CSV", data=csv_rs, file_name=f"rs_{stock_symbol}_vs_{index_symbol}.csv", mime="text/csv")

        # Show OHLCV + EMAs table & CSV
        st.markdown("#### OHLCV + EMAs (latest rows)")
        st.dataframe(df_stock.tail(250), use_container_width=True)
        csv = df_stock.to_csv(index=False).encode("utf-8")
        st.download_button(label="Download OHLCV+EMA CSV", data=csv, file_name=f"ohlcv_ema_{stock_symbol}.csv", mime="text/csv")

        # Helpful debug: show rows where DateStr maps to 2025-07-20 or 2025-07-30 if present (user reported issue)
        problem_dates = ["2025-07-20","2025-07-30"]
        found = df_stock[df_stock["DateStr"].isin(problem_dates)]
        if not found.empty:
            st.warning("Rows found matching historic problem dates (showing for debug):")
            st.dataframe(found)

    except Exception as e:
        st.error(f"Error: {e}")
        st.text(traceback.format_exc())
