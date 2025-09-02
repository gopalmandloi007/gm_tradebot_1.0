import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, timedelta
import plotly.graph_objects as go
import traceback

# ------------------------------
# Helpers: robust CSV -> DataFrame
# ------------------------------
def read_hist_csv_to_df(hist_csv: str) -> pd.DataFrame:
    """
    Robustly read a broker historical CSV (may or may not have header).
    Returns a DataFrame with parsed DateTime and OHLCV columns when possible.
    """
    if not isinstance(hist_csv, str) or not hist_csv.strip():
        return pd.DataFrame()

    txt = hist_csv.strip()
    first_line = txt.splitlines()[0].lower()

    # If first line looks like a header (contains common column names), let pandas infer header
    header_indicators = ("date", "datetime", "open", "high", "low", "close", "volume", "oi", "timestamp")
    use_header = any(h in first_line for h in header_indicators)

    try:
        if use_header:
            df = pd.read_csv(io.StringIO(txt))
        else:
            df = pd.read_csv(io.StringIO(txt), header=None)
    except Exception:
        # fallback: try reading as whitespace-separated
        try:
            df = pd.read_csv(io.StringIO(txt), header=None, delim_whitespace=True)
        except Exception:
            return pd.DataFrame()

    # Normalize columns: try to find which column is DateTime and which are OHLCV
    # If header present and columns named, use them
    cols = [c.lower() for c in df.columns.astype(str)]
    if any("date" in c or "time" in c for c in cols):
        # rename common names to canonical
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
        # assume typical positions: DateTime, Open, High, Low, Close, Volume, [OI]
        if df.shape[1] >= 6:
            if df.shape[1] == 7:
                df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume", "OI"]
            else:
                df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]
        else:
            # Not enough columns -> return empty
            return pd.DataFrame()

    # --- Robust DateTime parsing ---
    # Try general to_datetime first (infer format, dayfirst)
    series = df["DateTime"].astype(str)
    dt = pd.to_datetime(series, dayfirst=True, infer_datetime_format=True, errors="coerce")

    # If many NaT, attempt several explicit formats to correct common shapes
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

    # Final fallback: try parsing with pandas without dayfirst
    if dt.isna().sum() > 0:
        parsed = pd.to_datetime(series, infer_datetime_format=True, errors="coerce")
        dt = dt.fillna(parsed)

    df["DateTime"] = dt
    # Drop rows where DateTime couldn't be parsed
    df = df.dropna(subset=["DateTime"]).copy()

    # Convert OHLCV to numeric safely
    for col in ("Open", "High", "Low", "Close", "Volume", "OI"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Normalize to daily: remove any time-of-day noise by using date only
    # Keep a 'Date' column (datetime.date) for merging or deduping
    df["Date"] = df["DateTime"].dt.normalize()  # midnight time, still datetime dtype
    # Sort and deduplicate by Date (keep last record for that calendar date)
    df = df.sort_values("DateTime").drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)

    return df

# ------------------------------
# Fetch wrapper that calls broker's historical_csv and uses the robust reader
# ------------------------------
def fetch_historical(client, segment, token, days):
    """
    Fetch historical CSV from broker and return robustly parsed DataFrame.
    We request a little extra days to be safe (holidays).
    """
    today = datetime.today()
    # request days + buffer to avoid truncation
    buffer_days = max(15, int(days * 0.2))  # at least 15 days extra
    frm = (today - timedelta(days=days + buffer_days)).strftime("%d%m%Y%H%M")
    to = today.strftime("%d%m%Y%H%M")
    hist_csv = client.historical_csv(segment=segment, token=token, timeframe="day", frm=frm, to=to)
    df = read_hist_csv_to_df(hist_csv)
    # keep only the last `days` rows (most recent)
    if not df.empty:
        df = df.sort_values("Date").tail(days).reset_index(drop=True)
    return df

# ------------------------------
# EMA helper
# ------------------------------
def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

# ------------------------------
# Streamlit UI (main)
# ------------------------------
st.title("📈 Candlestick, EMAs, Relative Strength & Volume Chart (robust dates)")

client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

# master symbols loader (simple)
@st.cache_data
def load_master_symbols(master_csv_path="data/master/allmaster.csv"):
    return pd.read_csv(master_csv_path)

df_master = load_master_symbols()
segment = st.selectbox("Exchange/Segment", sorted(df_master["SEGMENT"].unique()), index=0)
segment_df = df_master[df_master["SEGMENT"] == segment]

def select_symbol(df, label="Trading Symbol"):
    symbol = st.selectbox(label, df["TRADINGSYM"].unique())
    return df[df["TRADINGSYM"] == symbol].iloc[0]

def select_index_symbol(df, label="Index Symbol"):
    index_candidates = df[
        df["INSTRUMENT"].str.contains("INDEX", case=False, na=False) |
        df["TRADINGSYM"].str.contains("NIFTY|IDX|SENSEX|BANKNIFTY|MIDSMALL|500|100", case=False, na=False)
    ].drop_duplicates("TRADINGSYM")
    if index_candidates.empty:
        index_candidates = df
    index_symbol = st.selectbox(label, index_candidates["TRADINGSYM"].unique())
    return index_candidates[index_candidates["TRADINGSYM"] == index_symbol].iloc[0]

stock_row = select_symbol(segment_df, label="Stock Trading Symbol")
index_row = select_index_symbol(df_master, label="Index Trading Symbol")

# EMA periods & days
st.markdown("#### EMA Periods")
ema_periods = st.text_input("Enter EMA periods (comma separated)", value="10,20,50,100,200")
ema_periods = [int(x.strip()) for x in ema_periods.split(",") if x.strip().isdigit()]

days_back = st.number_input("Number of Days (candles to fetch)", min_value=20, max_value=1000, value=250, step=1)
rs_sma_period = st.number_input("RS SMA Period", min_value=2, max_value=200, value=20, step=1)

if st.button("Show Chart"):
    try:
        df_stock = fetch_historical(client, stock_row["SEGMENT"], stock_row["TOKEN"], days_back)
        if df_stock.empty:
            st.warning(f"No data for: {stock_row['TRADINGSYM']} ({stock_row['TOKEN']}, {stock_row['SEGMENT']})")
            st.stop()

        df_index = fetch_historical(client, index_row["SEGMENT"], index_row["TOKEN"], days_back)
        if df_index.empty:
            st.warning(f"No data for index: {index_row['TRADINGSYM']} ({index_row['TOKEN']}, {index_row['SEGMENT']})")
            st.stop()

        # Quick debug: show date range and row counts so you can verify correctness
        st.info(f"Stock data: {len(df_stock)} rows — {df_stock['Date'].min().date()} to {df_stock['Date'].max().date()}")
        st.info(f"Index data: {len(df_index)} rows — {df_index['Date'].min().date()} to {df_index['Date'].max().date()}")

        # Ensure Close is numeric
        df_stock["Close"] = pd.to_numeric(df_stock["Close"], errors="coerce")
        df_stock = df_stock.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)

        # Calculate EMAs (on Close)
        for period in ema_periods:
            df_stock[f"EMA_{period}"] = ema(df_stock["Close"], period)

        # Plot: use Date (datetime) as x and xaxis_type='date' for correct ordering
        fig1 = go.Figure()
        fig1.add_trace(go.Candlestick(
            x=df_stock["Date"],
            open=df_stock["Open"],
            high=df_stock["High"],
            low=df_stock["Low"],
            close=df_stock["Close"],
            name="OHLC",
            increasing_line_color='green',
            decreasing_line_color='red'
        ))
        for period in ema_periods:
            fig1.add_trace(go.Scatter(
                x=df_stock["Date"],
                y=df_stock[f"EMA_{period}"],
                mode="lines", name=f"EMA {period}",
                line=dict(width=1.2)
            ))
        fig1.update_layout(
            title=f"{stock_row['TRADINGSYM']} Candlestick Chart with EMAs",
            xaxis=dict(title="Date", type="date", rangeslider=dict(visible=False)),
            yaxis=dict(title="Price"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=650,
            template="plotly_white",
            margin=dict(l=10, r=10, t=40, b=10)
        )
        st.plotly_chart(fig1, use_container_width=True)

        # Volume chart (aligned)
        fig_vol = go.Figure()
        fig_vol.add_trace(go.Bar(
            x=df_stock["Date"],
            y=df_stock["Volume"].fillna(0),
            name="Volume",
            opacity=0.7,
        ))
        fig_vol.update_layout(title=f"{stock_row['TRADINGSYM']} Volume", xaxis=dict(type="date"), height=300, template="plotly_white")
        st.plotly_chart(fig_vol, use_container_width=True)

        # --- Relative Strength: merge on calendar date to avoid time-of-day mismatches ---
        df_stock_rs = df_stock[["Date", "Close"]].rename(columns={"Close": "StockClose"})
        df_index_rs = df_index[["Date", "Close"]].rename(columns={"Close": "IndexClose"})

        # Merge by Date (normalized)
        df_rs = pd.merge(df_stock_rs, df_index_rs, on="Date", how="inner")
        df_rs = df_rs.sort_values("Date").reset_index(drop=True)
        if df_rs.empty:
            st.warning("No overlapping dates between stock and index data for RS chart.")
        else:
            df_rs["RS"] = (df_rs["StockClose"] / df_rs["IndexClose"]) * 100
            df_rs["RS_SMA"] = df_rs["RS"].rolling(window=rs_sma_period, min_periods=1).mean()

            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=df_rs["Date"], y=df_rs["RS"], mode="lines", name="Relative Strength"))
            fig2.add_trace(go.Scatter(x=df_rs["Date"], y=df_rs["RS_SMA"], mode="lines", name=f"RS SMA {rs_sma_period}", line=dict(dash='dash')))
            fig2.update_layout(title=f"Relative Strength: {stock_row['TRADINGSYM']} vs {index_row['TRADINGSYM']}",
                               xaxis=dict(type="date"), yaxis_title="Relative Strength", height=400, template="plotly_white")
            st.plotly_chart(fig2, use_container_width=True)

            st.markdown("#### Download Relative Strength Data")
            rs_display_cols = ["Date", "StockClose", "IndexClose", "RS", "RS_SMA"]
            st.dataframe(df_rs[rs_display_cols], use_container_width=True)
            csv_rs = df_rs[rs_display_cols].to_csv(index=False).encode('utf-8')
            st.download_button(label="Download RS data as CSV", data=csv_rs,
                               file_name=f'relative_strength_{stock_row["TRADINGSYM"]}_vs_{index_row["TRADINGSYM"]}.csv',
                               mime='text/csv')

        # Download OHLCV+EMA data
        st.markdown("#### Download OHLCV+EMAs Data")
        st.dataframe(df_stock, use_container_width=True)
        csv = df_stock.to_csv(index=False).encode('utf-8')
        st.download_button(label="Download OHLCV+EMA data as CSV", data=csv,
                           file_name=f'candlestick_ema_{stock_row["TRADINGSYM"]}.csv', mime='text/csv')

    except Exception as e:
        st.error(f"Error fetching/calculating chart: {e}")
        st.text(traceback.format_exc())
