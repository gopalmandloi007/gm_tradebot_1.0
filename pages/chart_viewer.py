import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import traceback
import re

st.set_page_config(layout="wide", page_title="Candles + EMAs + RS (No Gaps)")

# -------------------------
# Utilities: robust CSV -> DataFrame
# -------------------------

def _clean_dt_str(s: pd.Series) -> pd.Series:
    sc = s.fillna("").astype(str).str.strip()
    sc = sc.str.replace(r"\.0+$", "", regex=True)
    sc = sc.str.replace(r'["\']', "", regex=True)
    sc = sc.str.replace(r"\s+", "", regex=True)
    return sc


def _looks_like_ddmmyyyy_hhmm(val: str) -> bool:
    return bool(re.fullmatch(r"\d{12}", val)) and 1 <= int(val[0:2]) <= 31


def _looks_like_ddmmyyyy(val: str) -> bool:
    return bool(re.fullmatch(r"\d{8}", val)) and 1 <= int(val[0:2]) <= 31


def _looks_like_epoch_seconds(val: str) -> bool:
    return bool(re.fullmatch(r"\d{10}", val))


def _looks_like_epoch_millis(val: str) -> bool:
    return bool(re.fullmatch(r"\d{13}", val))


def read_hist_csv_to_df(hist_csv: str) -> pd.DataFrame:
    """Robust CSV parser that tries to cope with several common formats.
    Returns: DataFrame with columns DateTime, Date, DateStr, Open, High, Low, Close, Volume
    Keeps last entry per calendar date (useful when CSV contains intraday rows).
    """
    if hist_csv is None:
        return pd.DataFrame()
    txt = hist_csv.strip()
    if not txt:
        return pd.DataFrame()

    # Try to read with pandas (let it auto-detect delimiter)
    try:
        # If there's a single column with semicolons, let pandas detect
        df = pd.read_csv(io.StringIO(txt))
    except Exception:
        try:
            df = pd.read_csv(io.StringIO(txt), header=None)
        except Exception:
            return pd.DataFrame()

    # Normalize column names
    col_map = {}
    cols = [str(c).lower() for c in df.columns]
    for orig, lc in zip(df.columns, cols):
        if "date" in lc or "time" in lc or lc in ("timestamp", "datetime"):
            col_map[orig] = "DateTime"
        elif lc.startswith("open"):
            col_map[orig] = "Open"
        elif lc.startswith("high"):
            col_map[orig] = "High"
        elif lc.startswith("low"):
            col_map[orig] = "Low"
        elif lc.startswith("close"):
            col_map[orig] = "Close"
        elif "volume" in lc or lc == "vol":
            col_map[orig] = "Volume"
        elif lc == "oi":
            col_map[orig] = "OI"
    if col_map:
        df = df.rename(columns=col_map)
    else:
        # Fallback: if no header mapping and at least 6 columns assume standard order
        if df.shape[1] >= 6:
            df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]

    if "DateTime" not in df.columns:
        # Last effort: try to find any column that looks date-like
        for c in df.columns:
            s = df[c].astype(str).str.strip().iloc[0:5].tolist()
            joined = " ".join(s)
            if re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", joined) or re.search(r"\d{8}", joined):
                df = df.rename(columns={c: "DateTime"})
                break

    if "DateTime" not in df.columns:
        return pd.DataFrame()

    # Clean DateTime
    series = _clean_dt_str(df["DateTime"])

    # try epoch detection
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=True, infer_datetime_format=True)

    # detect patterns if many NaT
    if parsed.isna().sum() > len(parsed) * 0.2:
        # try epoch seconds / millis
        def try_epoch(s):
            if s == "":
                return pd.NaT
            if _looks_like_epoch_seconds(s):
                try:
                    return pd.to_datetime(int(s), unit="s")
                except:
                    return pd.NaT
            if _looks_like_epoch_millis(s):
                try:
                    return pd.to_datetime(int(s), unit="ms")
                except:
                    return pd.NaT
            if _looks_like_ddmmyyyy_hhmm(s):
                try:
                    return pd.to_datetime(s, format="%d%m%Y%H%M")
                except:
                    return pd.NaT
            if _looks_like_ddmmyyyy(s):
                try:
                    return pd.to_datetime(s, format="%d%m%Y")
                except:
                    return pd.NaT
            return pd.NaT

        parsed2 = series.apply(try_epoch)
        # combine
        parsed = parsed.combine_first(parsed2)

    df["DateTime"] = parsed
    df = df.dropna(subset=["DateTime"])  # drop completely unparseable rows

    # Numeric conversion for OHLCV
    for col in ("Open", "High", "Low", "Close", "Volume", "OI"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Calendar date and keep last row per date (useful if feed is intraday)
    df["Date"] = df["DateTime"].dt.normalize()
    df = df.sort_values("DateTime").drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)
    df["DateStr"] = df["Date"].dt.strftime("%Y-%m-%d")

    # Ensure expected columns exist
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c not in df.columns:
            df[c] = np.nan

    return df[["DateTime", "Date", "DateStr", "Open", "High", "Low", "Close", "Volume"]]


# -------------------------
# Fetch historical wrapper (uses `client` if provided)
# -------------------------

def _fmt_for_api(dt: datetime) -> str:
    # API expects ddmmyyyyHHMM
    return dt.strftime("%d%m%Y%H%M")


def fetch_historical(client, segment, token, days_back=250, buffer_days=30, timeframe="day", show_raw=False):
    """Fetch historical CSV via client's historical_csv method when available.
    If client is None or call fails returns empty DataFrame.
    """
    today = datetime.today()
    start = today - timedelta(days=days_back + buffer_days)
    frm = _fmt_for_api(start)
    to = _fmt_for_api(today)
    try:
        raw = client.historical_csv(segment=segment, token=token, timeframe=timeframe, frm=frm, to=to)
        if show_raw:
            st.text_area("Raw historical CSV (debug)", value=str(raw), height=200)
    except Exception as e:
        st.warning(f"Failed fetch for {token}: {e}")
        return pd.DataFrame()
    if not raw or not str(raw).strip():
        return pd.DataFrame()
    return read_hist_csv_to_df(raw)


# -------------------------
# Master symbols loader (user environment expected to have file)
# -------------------------
@st.cache_data
def load_master_symbols(master_csv_path="data/master/allmaster.csv"):
    try:
        return pd.read_csv(master_csv_path)
    except Exception:
        return pd.DataFrame()


# -------------------------
# UI
# -------------------------
st.title("📈 Candlestick, EMAs, Relative Strength & Volume — Improved")

df_master = load_master_symbols()
if df_master.empty:
    st.warning("Master symbols not found at data/master/allmaster.csv — you can upload a master CSV or use the file uploader for OHLCV directly.")

# Allow user to upload OHLCV CSV as fallback
uploaded_csv = st.file_uploader("Upload OHLCV CSV (optional). If provided, this will be used instead of fetching from client.", type=["csv","txt"]) 

# Exchange / symbol selection (if master present)
segment = None
stock_symbol = None
stock_row = None
index_symbol = None
index_row = None

if not df_master.empty:
    segments = sorted(df_master["SEGMENT"].dropna().unique())
    default_seg_index = 0
    for i, s in enumerate(segments):
        if str(s).strip().upper() == "NSE":
            default_seg_index = i
            break
    segment = st.selectbox("Exchange/Segment", segments, index=default_seg_index)
    segment_df = df_master[df_master["SEGMENT"] == segment]

    # default symbol: prefer NIFTY 500 if present
    def_symbol = None
    for s in segment_df["TRADINGSYM"].astype(str).unique():
        if "NIFTY" in s.upper() and "500" in s.upper():
            def_symbol = s
            break
    symbols = list(segment_df["TRADINGSYM"].astype(str).unique())
    default_symbol_index = symbols.index(def_symbol) if def_symbol in symbols else 0
    stock_symbol = st.selectbox("Stock Trading Symbol", symbols, index=default_symbol_index)
    stock_row = segment_df[segment_df["TRADINGSYM"] == stock_symbol].iloc[0]

    # index candidates
    index_candidates = df_master[
        df_master["INSTRUMENT"].astype(str).str.contains("INDEX", case=False, na=False) |
        df_master["TRADINGSYM"].astype(str).str.contains("NIFTY|SENSEX|BANKNIFTY|IDX|500|100", case=False, na=False)
    ].drop_duplicates("TRADINGSYM")
    if index_candidates.empty:
        index_candidates = df_master
    index_symbols = list(index_candidates["TRADINGSYM"].astype(str).unique())
    def_idx_symbol = None
    for s in index_symbols:
        if "NIFTY" in s.upper() and "500" in s.upper():
            def_idx_symbol = s; break
        if def_idx_symbol is None and "NIFTY" in s.upper():
            def_idx_symbol = s
    default_idx_index = index_symbols.index(def_idx_symbol) if def_idx_symbol in index_symbols else 0
    index_symbol = st.selectbox("Index Trading Symbol (for RS)", index_symbols, index=default_idx_index)
    index_row = index_candidates[index_candidates["TRADINGSYM"] == index_symbol].iloc[0]

# EMA controls
default_emas = "10,20,50,100,200"
ema_periods_raw = st.text_input("Enter EMA periods (comma separated)", value=default_emas)
try:
    ema_periods = [int(x.strip()) for x in ema_periods_raw.split(",") if x.strip().isdigit()]
except Exception:
    ema_periods = [10,20,50]

show_volume = st.checkbox("Show volume", value=True)
show_rs = st.checkbox("Show Relative Strength (vs selected index)", value=True)
rs_sma_period = st.number_input("RS SMA Period", min_value=2, max_value=500, value=20, step=1)
use_rangeslider = st.checkbox("Enable range slider (interactive) — works best with larger datasets", value=True)
append_today_quote = st.checkbox("Append today's live quote (use quotes API if client available)", value=False)
show_raw_hist = st.checkbox("Show raw historical CSV (debug)", value=False)

# number of days
days_back = st.number_input("Number of Days (candles to fetch)", min_value=20, max_value=5000, value=250, step=1)

# Plot options
plot_mode = st.radio("Chart style", options=["Compact (single chart)", "Detailed (candles + volume + RS subplots)"], index=1)

# Button
if st.button("Show Chart"):
    try:
        # Determine data source
        if uploaded_csv is not None:
            raw = uploaded_csv.read().decode("utf-8")
            df_stock = read_hist_csv_to_df(raw)
            if df_stock.empty:
                st.error("Uploaded CSV could not be parsed into OHLCV.")
                st.stop()
        else:
            client = st.session_state.get("client")
            if client is None:
                st.warning("Client not found in session state. If you wish to fetch from master symbols please set `st.session_state['client']` first. You can also upload a CSV.")
                st.stop()
            if stock_row is None:
                st.error("Stock selection unavailable (master file issue).")
                st.stop()
            df_stock = fetch_historical(client, stock_row["SEGMENT"], stock_row["TOKEN"], days_back=days_back, buffer_days=30, show_raw=show_raw_hist)
            if df_stock.empty:
                st.warning(f"No historical data for: {stock_symbol}")
                st.stop()

        # Optionally append today's quote
        if append_today_quote and uploaded_csv is None:
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
                df_stock = pd.concat([df_stock[df_stock["Date"] < today_norm], today_row], ignore_index=True)
            except Exception as e:
                st.warning(f"Failed to append today's quote: {e}")

        # numeric safety & drop NaN closes
        for c in ["Open", "High", "Low", "Close", "Volume"]:
            if c in df_stock.columns:
                df_stock[c] = pd.to_numeric(df_stock[c], errors="coerce")
        df_stock = df_stock.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)

        # Trim to requested days_back
        if len(df_stock) > days_back:
            df_stock = df_stock.tail(days_back).reset_index(drop=True)

        # DateStr available
        if "DateStr" not in df_stock.columns:
            df_stock["DateStr"] = df_stock["Date"].dt.strftime("%Y-%m-%d")

        st.info(f"Stock rows: {len(df_stock)} | Date range: {df_stock['Date'].min().date()} → {df_stock['Date'].max().date()}")

        # Calculate EMAs
        def ema(series, period):
            return series.ewm(span=period, adjust=False).mean()

        for p in ema_periods:
            df_stock[f"EMA_{p}"] = ema(df_stock["Close"], p)

        # create integer x-axis to avoid gaps but keep range slider functionality
        df_stock = df_stock.reset_index().rename(columns={"index": "_idx"})
        x_idx = df_stock["_idx"].tolist()

        # RS calculation if requested
        df_rs = pd.DataFrame()
        if show_rs:
            if uploaded_csv is not None:
                st.info("RS chart skipped: index data not available when using uploaded stock CSV (unless you upload index CSV separately).")
                show_rs = False
            else:
                df_index = fetch_historical(client, index_row["SEGMENT"], index_row["TOKEN"], days_back=days_back, buffer_days=30, show_raw=False)
                if df_index.empty:
                    st.warning(f"No historical data for index: {index_symbol}")
                    show_rs = False
                else:
                    # merge on calendar date and map to stock index
                    df_index = df_index[["Date","Close"]].rename(columns={"Close":"IndexClose"})
                    df_rs = pd.merge(df_stock[["Date","_idx","Close"]].rename(columns={"Close":"StockClose"}), df_index, on="Date", how="inner")
                    if df_rs.empty:
                        st.warning("No overlapping dates between stock and index data for RS chart.")
                        show_rs = False
                    else:
                        df_rs["RS"] = (df_rs["StockClose"] / df_rs["IndexClose"]) * 100
                        df_rs["RS_SMA"] = df_rs["RS"].rolling(window=rs_sma_period, min_periods=1).mean()

        # Plotting
        # Decide subplot rows
        rows = 1 + (1 if show_volume else 0) + (1 if show_rs else 0)
        row_heights = []
        if rows == 3:
            row_heights = [0.6, 0.2, 0.2]
        elif rows == 2:
            # prefer main + volume
            row_heights = [0.7, 0.3] if show_volume else [0.7, 0.3]
        else:
            row_heights = [1.0]

        specs = [[{"secondary_y": False}]] * rows
        fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=row_heights)

        # Row mapping helpers
        r = 1
        # Candles + EMAs
        fig.add_trace(go.Candlestick(
            x=x_idx,
            open=df_stock["Open"],
            high=df_stock["High"],
            low=df_stock["Low"],
            close=df_stock["Close"],
            name="OHLC",
            increasing_line_color='green',
            decreasing_line_color='red',
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Open: %{open:.2f}<br>High: %{high:.2f}<br>Low: %{low:.2f}<br>Close: %{close:.2f}<br>Volume: %{customdata[1]:,.0f}<extra></extra>"
            ),
            customdata=np.stack((df_stock["DateStr"].astype(str), df_stock["Volume"].fillna(0).astype(int)), axis=-1)
        ), row=r, col=1)

        # EMA traces (click legend to toggle)
        palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]
        for i, p in enumerate(ema_periods):
            col = f"EMA_{p}"
            if col in df_stock.columns:
                fig.add_trace(go.Scatter(
                    x=x_idx,
                    y=df_stock[col],
                    mode="lines",
                    name=col,
                    line=dict(width=1.6, color=palette[i % len(palette)]),
                    hovertemplate=f"EMA {p}: %{{y:.2f}}<br><b>%{{customdata}}</b><extra></extra>",
                    customdata=df_stock["DateStr"].astype(str)
                ), row=r, col=1)

        r += 1

        # Volume
        if show_volume:
            vol_colors = np.where(df_stock["Close"].diff().fillna(0) >= 0, "green", "red")
            fig.add_trace(go.Bar(x=x_idx, y=df_stock["Volume"].fillna(0), name="Volume", marker_color=vol_colors, hovertemplate="Date: %{customdata}<br>Volume: %{y:,.0f}<extra></extra>", customdata=df_stock["DateStr"].astype(str)), row=r, col=1)
            r += 1

        # RS
        if show_rs and not df_rs.empty:
            fig.add_trace(go.Scatter(x=df_rs["_idx"], y=df_rs["RS"], mode="lines", name="RS", line=dict(width=1.6)), row=r, col=1)
            fig.add_trace(go.Scatter(x=df_rs["_idx"], y=df_rs["RS_SMA"], mode="lines", name=f"RS SMA {rs_sma_period}", line=dict(dash="dash", width=1.4)), row=r, col=1)

        # Layout tweaks
        # build tick labels at reasonable interval
        n = len(df_stock)
        if n <= 12:
            tick_step = 1
        else:
            tick_step = max(1, n // 10)
        tickvals = list(range(0, n, tick_step))
        ticktext = df_stock.loc[tickvals, "DateStr"].tolist()

        fig.update_layout(
            title_text=f"{stock_symbol} — Candlestick (no gaps) + EMAs",
            template="plotly_white",
            height=700,
            showlegend=True,
            margin=dict(l=10, r=10, t=60, b=30)
        )

        # X axis: numeric index but show date ticks; rangeslider if chosen
        fig.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)
        if use_rangeslider:
            fig.update_layout(xaxis=dict(rangeslider=dict(visible=True), type="linear"))

        fig.update_yaxes(title_text="Price", row=1, col=1)
        if show_volume:
            fig.update_yaxes(title_text="Volume", row=2 if rows>1 else 1, col=1)
        if show_rs:
            fig.update_yaxes(title_text="RS", row=rows, col=1)

        # Render
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "scrollZoom": True})

        # RS table & download
        if show_rs and not df_rs.empty:
            st.markdown("#### Relative Strength (table)")
            display_cols = ["Date", "StockClose", "IndexClose", "RS", "RS_SMA"]
            df_rs_disp = df_rs.rename(columns={"Close": "StockClose"}) if "Close" in df_rs.columns else df_rs
            st.dataframe(df_rs[["Date", "StockClose", "IndexClose", "RS", "RS_SMA"]].assign(Date=lambda d: d["Date"].dt.strftime("%Y-%m-%d")), use_container_width=True)
            csv_rs = df_rs[["Date", "StockClose", "IndexClose", "RS", "RS_SMA"]].assign(Date=lambda d: d["Date"].dt.strftime("%Y-%m-%d")).to_csv(index=False).encode("utf-8")
            st.download_button(label="Download RS CSV", data=csv_rs, file_name=f"rs_{stock_symbol}_vs_{index_symbol}.csv", mime="text/csv")

        # Show OHLCV + EMAs table & CSV
        st.markdown("#### OHLCV + EMAs (latest rows)")
        display_df = df_stock.copy()
        display_df["Date"] = display_df["Date"].dt.strftime("%Y-%m-%d")
        st.dataframe(display_df.tail(250), use_container_width=True)
        csv = display_df.to_csv(index=False).encode("utf-8")
        st.download_button(label="Download OHLCV+EMA CSV", data=csv, file_name=f"ohlcv_ema_{stock_symbol or 'uploaded'}.csv", mime="text/csv")

    except Exception as e:
        st.error(f"Error: {e}")
        st.text(traceback.format_exc())
