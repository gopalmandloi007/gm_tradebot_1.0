import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, timedelta
import plotly.graph_objects as go
import traceback

st.set_page_config(layout="wide")
st.title("📈 Candlestick, EMAs, Relative Strength & Volume — No Gaps (Robust)")

# -------------------------
# Utilities: robust CSV -> DataFrame
# -------------------------
def try_parse_epoch(series):
    """If series looks numeric and large, try epoch seconds/ms parse."""
    try:
        s = pd.to_numeric(series, errors="coerce")
        if s.isna().all():
            return pd.Series([pd.NaT] * len(s))
        # Heuristics: if values > 1e12 -> ms, >1e9 -> sec
        if (s > 1e12).any():
            return pd.to_datetime(s, unit="ms", errors="coerce")
        if (s > 1e9).any():
            return pd.to_datetime(s, unit="s", errors="coerce")
    except Exception:
        pass
    return pd.Series([pd.NaT] * len(series))

def read_hist_csv_to_df(hist_csv: str) -> pd.DataFrame:
    """Robustly read broker historical CSV and return daily rows deduped by calendar Date.
    The returned DataFrame contains DateTime (datetime), Date (normalized midnight),
    Open/High/Low/Close/Volume (numeric).
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

    # Attempt CSV read with/without header
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

    # Normalize column names
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
        # If no header, assume common positions
        if df.shape[1] >= 6:
            if df.shape[1] == 7:
                df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume", "OI"]
            else:
                df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]
        else:
            return pd.DataFrame()

    # Ensure DateTime column exists
    if "DateTime" not in df.columns:
        return pd.DataFrame()

    series = df["DateTime"].astype(str)

    # 1) Try pandas infer (dayfirst)
    dt = pd.to_datetime(series, dayfirst=True, infer_datetime_format=True, errors="coerce")

    # 2) If many NaT: try explicit formats
    if dt.isna().sum() > 0:
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

    # 3) If still many NaT, try epoch heuristics
    if dt.isna().sum() > 0:
        parsed_epoch = try_parse_epoch(series)
        dt = dt.fillna(parsed_epoch)

    # 4) Final fallback without dayfirst
    if dt.isna().sum() > 0:
        parsed = pd.to_datetime(series, infer_datetime_format=True, errors="coerce")
        dt = dt.fillna(parsed)

    df["DateTime"] = dt
    df = df.dropna(subset=["DateTime"]).copy()

    # Numeric conversion for OHLCV
    for col in ("Open", "High", "Low", "Close", "Volume", "OI"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if df.empty:
        return pd.DataFrame()

    # Normalize to calendar Date (midnight) and dedupe by Date keeping last intraday row
    df["Date"] = df["DateTime"].dt.normalize()
    df = df.sort_values("DateTime").drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)

    # Keep only essential columns
    keep_cols = ["DateTime", "Date", "Open", "High", "Low", "Close", "Volume"]
    existing = [c for c in keep_cols if c in df.columns]
    df = df[existing].copy()

    return df

# -------------------------
# Fetch historical wrapper
# -------------------------
def fetch_historical(client, segment, token, days, buffer_days=30, show_raw=False):
    """
    Fetch historical CSV and parse robustly. We request extra 'buffer_days' to avoid truncated ranges.
    Returns DataFrame with DateTime & Date normalized.
    """
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
        st.text_area("Raw historical CSV (first 2000 chars)", raw_text[:2000], height=200)

    df = read_hist_csv_to_df(raw_text)
    if df.empty:
        return df

    df = df.sort_values("Date").tail(days).reset_index(drop=True)
    # Add a DateStr column used for categorical x-axis (YYYY-MM-DD)
    df["DateStr"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df

# -------------------------
# Load master & UI defaults
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

# DEFAULT symbol selection: find 'NIFTY 500' (case-insensitive substring) if present
def_symbol = None
candidates = segment_df["TRADINGSYM"].astype(str)
for s in candidates.unique():
    if "NIFTY" in s.upper() and "500" in s.upper():
        def_symbol = s
        break

# Build symbol list and determine default index
symbols = list(segment_df["TRADINGSYM"].astype(str).unique())
if def_symbol and def_symbol in symbols:
    default_symbol_index = symbols.index(def_symbol)
else:
    default_symbol_index = 0

stock_symbol = st.selectbox("Stock Trading Symbol", symbols, index=default_symbol_index)
stock_row = segment_df[segment_df["TRADINGSYM"] == stock_symbol].iloc[0]

# Index selection (for RS) - try to pick a sensible index symbol (e.g. NIFTY or NIFTY 500)
index_candidates = df_master[
    df_master["INSTRUMENT"].astype(str).str.contains("INDEX", case=False, na=False) |
    df_master["TRADINGSYM"].astype(str).str.contains("NIFTY|SENSEX|BANKNIFTY|IDX|500|100", case=False, na=False)
].drop_duplicates("TRADINGSYM")

if index_candidates.empty:
    index_candidates = df_master

index_symbols = list(index_candidates["TRADINGSYM"].astype(str).unique())
# default index: try 'NIFTY 500' then 'NIFTY 50' then first
def_idx_symbol = None
for s in index_symbols:
    su = s.upper()
    if "NIFTY" in su and "500" in su:
        def_idx_symbol = s
        break
    if def_idx_symbol is None and "NIFTY" in su:
        def_idx_symbol = s

default_idx_index = index_symbols.index(def_idx_symbol) if def_idx_symbol in index_symbols else 0
index_symbol = st.selectbox("Index Trading Symbol (for RS)", index_symbols, index=default_idx_index)
index_row = index_candidates[index_candidates["TRADINGSYM"] == index_symbol].iloc[0]

# EMA periods & days (UI)
st.markdown("#### EMA Periods")
ema_periods = st.text_input("Enter EMA periods (comma separated)", value="10,20,50,100,200")
ema_periods = [int(x.strip()) for x in ema_periods.split(",") if x.strip().isdigit()]

days_back = st.number_input("Number of Days (candles to fetch)", min_value=20, max_value=2000, value=250, step=1)
rs_sma_period = st.number_input("RS SMA Period", min_value=2, max_value=500, value=20, step=1)

# Options
append_today_quote = st.checkbox("Append today's live quote (use quotes API)", value=False)
show_raw_hist = st.checkbox("Show raw historical CSV (for debugging)", value=False)

if st.button("Show Chart"):
    try:
        # Fetch historical data
        df_stock = fetch_historical(st.session_state.get("client"), stock_row["SEGMENT"], stock_row["TOKEN"], days_back, buffer_days=30, show_raw=show_raw_hist)
        if df_stock.empty:
            st.warning(f"No historical data for: {stock_symbol}")
            st.stop()

        df_index = fetch_historical(st.session_state.get("client"), index_row["SEGMENT"], index_row["TOKEN"], days_back, buffer_days=30, show_raw=False)
        if df_index.empty:
            st.warning(f"No historical data for index: {index_symbol}")
            st.stop()

        # Optionally append today's quote (replace same-day row if present)
        if append_today_quote:
            try:
                quotes = st.session_state.get("client").get_quotes(exchange=stock_row["SEGMENT"], token=stock_row["TOKEN"])
                # Map common fields: day_open, day_high, day_low, ltp/day_close, volume
                q_open = float(quotes.get("day_open") or quotes.get("open") or 0)
                q_high = float(quotes.get("day_high") or quotes.get("high") or 0)
                q_low  = float(quotes.get("day_low") or quotes.get("low") or 0)
                q_close = float(quotes.get("ltp") or quotes.get("last_price") or 0)
                q_vol = float(quotes.get("volume") or quotes.get("vol") or 0)

                today_norm = pd.to_datetime(datetime.today().date())
                today_str = today_norm.strftime("%Y-%m-%d")
                # Build today's row dataframe
                today_row = pd.DataFrame([{
                    "DateTime": pd.to_datetime(datetime.now()),
                    "Date": today_norm,
                    "Open": q_open,
                    "High": q_high,
                    "Low": q_low,
                    "Close": q_close,
                    "Volume": q_vol,
                    "DateStr": today_str
                }])
                # Remove existing today's row if exists and append
                df_stock = df_stock[df_stock["Date"] < today_norm].append(today_row, ignore_index=True).reset_index(drop=True)
            except Exception as e:
                st.warning(f"Failed to append today's quote: {e}")

        # Safety: ensure numeric columns and drop NaN close rows
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in df_stock.columns:
                df_stock[col] = pd.to_numeric(df_stock[col], errors="coerce")
        df_stock = df_stock.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)

        # Derive DateStr if missing
        if "DateStr" not in df_stock.columns:
            df_stock["DateStr"] = df_stock["Date"].dt.strftime("%Y-%m-%d")

        # Info for quick verification
        st.info(f"Stock rows: {len(df_stock)} | Date range: {df_stock['Date'].min().date()} → {df_stock['Date'].max().date()}")
        st.info(f"Index rows: {len(df_index)} | Date range: {df_index['Date'].min().date()} → {df_index['Date'].max().date()}")

        # Calculate EMAs on Close
        def ema(series, period):
            return series.ewm(span=period, adjust=False).mean()
        for p in ema_periods:
            df_stock[f"EMA_{p}"] = ema(df_stock["Close"], p)

        # --- Plot Candlestick with categorical x (no gaps) ---
        x = df_stock["DateStr"].tolist()  # categorical labels in chronological order
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
            if f"EMA_{p}" in df_stock.columns:
                fig1.add_trace(go.Scatter(x=x, y=df_stock[f"EMA_{p}"], mode="lines", name=f"EMA {p}", line=dict(width=1.2)))

        fig1.update_layout(
            title=f"{stock_symbol} — Candlestick (no gaps) + EMAs",
            xaxis=dict(type="category", title="Date (trading days only)"),
            yaxis=dict(title="Price"),
            height=650,
            template="plotly_white",
            margin=dict(l=10, r=10, t=40, b=10)
        )
        st.plotly_chart(fig1, use_container_width=True)

        # Volume (categorical x)
        fig_vol = go.Figure()
        fig_vol.add_trace(go.Bar(x=x, y=df_stock["Volume"].fillna(0), name="Volume"))
        fig_vol.update_layout(title=f"{stock_symbol} Volume (no gaps)", xaxis=dict(type="category"), height=300, template="plotly_white")
        st.plotly_chart(fig_vol, use_container_width=True)

        # ---- Relative Strength: merge on Date (calendar) and show with categorical axis ----
        df_stock_rs = df_stock[["Date", "DateStr", "Close"]].rename(columns={"Close": "StockClose"})
        df_index_rs = df_index[["Date", "Close"]].rename(columns={"Close": "IndexClose"})
        df_rs = pd.merge(df_stock_rs, df_index_rs, on="Date", how="inner").sort_values("Date")
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

            # Download RS data
            st.markdown("#### Download Relative Strength Data")
            rs_display_cols = ["Date", "StockClose", "IndexClose", "RS", "RS_SMA"]
            st.dataframe(df_rs[rs_display_cols], use_container_width=True)
            csv_rs = df_rs[rs_display_cols].to_csv(index=False).encode("utf-8")
            st.download_button(label="Download RS CSV", data=csv_rs, file_name=f"rs_{stock_symbol}_vs_{index_symbol}.csv", mime="text/csv")

        # Show OHLCV+EMA table and CSV download
        st.markdown("#### OHLCV + EMAs (latest rows)")
        st.dataframe(df_stock.tail(250), use_container_width=True)
        csv = df_stock.to_csv(index=False).encode("utf-8")
        st.download_button(label="Download OHLCV+EMA CSV", data=csv, file_name=f"ohlcv_ema_{stock_symbol}.csv", mime="text/csv")

    except Exception as e:
        st.error(f"Error: {e}")
        st.text(traceback.format_exc())
