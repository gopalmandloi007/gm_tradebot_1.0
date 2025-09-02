import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import traceback

st.set_page_config(layout="wide")
st.title("📊 Trading Dashboard — Definedge (Prev Close = Historical Only)")

# ------------------ Helper: parse Definedge CSV ------------------
def parse_definedge_csv(raw_text, timeframe="day"):
    """
    Parse raw CSV returned by Definedge (they return CSV without headers).
    """
    try:
        from io import StringIO

        if not raw_text or raw_text.strip() == "":
            return None, "empty"

        df = pd.read_csv(StringIO(raw_text), header=None)

        if timeframe == "day":
            df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume", "OI"]
            df["DateTime"] = pd.to_datetime(df["DateTime"], format="%Y-%m-%d")
        else:
            return None, "unsupported_timeframe"

        return df, None
    except Exception as exc:
        return None, f"parse_error:{exc}"


# ------------------ Helper: Previous Close from Historical ------------------
def get_robust_prev_close_from_hist(hist_df: pd.DataFrame, today_date: date):
    """
    Returns strictly yesterday's close from historical dataframe.
    Ignores today's rows so that LTP is never used.
    """
    try:
        if "DateTime" not in hist_df.columns or "Close" not in hist_df.columns:
            return None, "missing_columns"

        df = hist_df.dropna(subset=["DateTime", "Close"]).copy()
        if df.empty:
            return None, "no_hist_data"

        df["date_only"] = df["DateTime"].dt.date
        df["Close_numeric"] = pd.to_numeric(df["Close"], errors="coerce")

        # strictly yesterday (last trading date before today)
        df = df[df["date_only"] < today_date]
        if df.empty:
            return None, "no_date_before_today"

        prev_trading_date = df["date_only"].max()
        prev_rows = df[df["date_only"] == prev_trading_date].sort_values("DateTime")
        prev_close = prev_rows["Close_numeric"].dropna().iloc[-1]

        return float(prev_close), f"prev_close_{prev_trading_date}"

    except Exception as exc:
        return None, f"error:{str(exc)[:120]}"


# ------------------ Main Dashboard ------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first.")
    st.stop()

try:
    today_dt = datetime.now()
    today_date = today_dt.date()

    # Example: holdings or watchlist (replace with your own symbols/tokens)
    watchlist = [
        {"symbol": "NSE|26009", "token": "26009"},  # Example Reliance
        {"symbol": "NSE|22", "token": "22"},        # Example SBI
    ]

    rows = []
    for item in watchlist:
        token = item["token"]
        symbol = item["symbol"]

        # --- Get live LTP ---
        try:
            q = client.get_quotes(["NSE"], [token])
            ltp = float(q[0]["ltp"]) if q else np.nan
        except Exception:
            ltp = np.nan

        # --- Get previous close (historical only) ---
        try:
            from_date = (today_dt - timedelta(days=30)).strftime("%d%m%Y%H%M")
            to_date = today_dt.strftime("%d%m%Y%H%M")
            hist_csv = client.historical_csv(
                segment="NSE",
                token=token,
                timeframe="day",
                frm=from_date,
                to=to_date,
            )

            hist_df, err = parse_definedge_csv(hist_csv, timeframe="day")
            if hist_df is None:
                raise Exception(f"parse_definedge_csv failed: {err}")

            prev_close_val, reason = get_robust_prev_close_from_hist(hist_df, today_date)
            if prev_close_val is not None:
                prev_close = prev_close_val
            else:
                prev_close = np.nan
        except Exception:
            prev_close = np.nan

        # --- Add to rows ---
        rows.append({
            "symbol": symbol,
            "ltp": ltp,
            "prev_close": prev_close,
            "change": (ltp - prev_close) if not np.isnan(prev_close) else np.nan,
            "change_%": ((ltp - prev_close) / prev_close * 100) if prev_close and not np.isnan(prev_close) else np.nan,
        })

    # ------------------ Display ------------------
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)

except Exception as e:
    st.error("⚠️ Error occurred")
    st.text(traceback.format_exc())
