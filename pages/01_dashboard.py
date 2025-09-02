import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import traceback

# ------------------ Configuration ------------------
st.set_page_config(layout="wide")
st.title("📊 Trading Dashboard — Definedge")

DEFAULT_TOTAL_CAPITAL = 1400000
DEFAULT_INITIAL_SL = 0.02

# ------------------ Helper: parse Definedge CSV (headerless) ------------------
def parse_definedge_csv(raw_text, timeframe="day"):
    """
    Parse raw CSV returned by Definedge (they return CSV without headers).
    """
    try:
        from io import StringIO

        if not raw_text:
            return None, "Empty CSV"

        if timeframe == "day":
            cols = ["DateTime", "Open", "High", "Low", "Close", "Volume", "OI"]
        else:
            cols = ["DateTime", "Open", "High", "Low", "Close", "Volume"]

        df = pd.read_csv(StringIO(raw_text), names=cols)
        df["DateTime"] = pd.to_datetime(df["DateTime"], errors="coerce")
        return df, None
    except Exception as e:
        return None, str(e)

# ------------------ Main ------------------
try:
    client = st.session_state.get("client")
    df = st.session_state.get("df")

    if not client or df is None:
        st.error("⚠️ Not logged in or no dataframe found.")
        st.stop()

    st.info("Fetching live prices and previous close (from historical CSV only).")

    ltp_list = []
    prev_close_list = []
    prev_source_list = []

    today_dt = datetime.now()
    today_date = today_dt.date()

    for idx, row in df.iterrows():
        token = row.get("token")
        symbol = row.get("symbol")
        qty = row.get("qty", 1)  # अगर qty column नहीं है तो default 1

        # --- 1) Fetch LTP from quotes ---
        try:
            quote_resp = client.get_quotes(exchange="NSE", token=token)
            if isinstance(quote_resp, dict):
                ltp_val = (quote_resp.get("ltp") or quote_resp.get("last_price") or
                           quote_resp.get("lastTradedPrice") or quote_resp.get("lastPrice") or
                           quote_resp.get("ltpPrice"))
                try:
                    ltp = float(ltp_val or 0.0)
                except Exception:
                    ltp = 0.0
            else:
                ltp = 0.0
        except Exception:
            ltp = 0.0

        # --- 2) Fetch prev_close from historical CSV ---
        try:
            from_date = (today_dt - timedelta(days=30)).strftime("%d%m%Y%H%M")
            to_date = today_dt.strftime("%d%m%Y%H%M")
            hist_csv = client.historical_csv(
                segment="NSE", token=token, timeframe="day", frm=from_date, to=to_date
            )

            hist_df, err = parse_definedge_csv(hist_csv, timeframe="day")
            if hist_df is None:
                raise Exception(f"parse_definedge_csv failed: {err}")

            hist_df = hist_df.dropna(subset=["DateTime", "Close"]).sort_values("DateTime")
            hist_df["date_only"] = hist_df["DateTime"].dt.date

            prev_dates = [d for d in sorted(hist_df["date_only"].unique()) if d < today_date]
            if prev_dates:
                prev_trading_date = prev_dates[-1]
                prev_rows = hist_df[hist_df["date_only"] == prev_trading_date]
                prev_close_val = prev_rows.iloc[-1]["Close"]
                prev_close = float(prev_close_val)
                prev_source = f"historical_csv:{prev_trading_date}"
            else:
                prev_close = ltp
                prev_source = "fallback:ltp(no_prev_trading_day)"
        except Exception as exc:
            prev_close = ltp
            prev_source = f"historical_error:{str(exc)[:80]}"

        # --- Append results ---
        ltp_list.append(ltp)
        prev_close_list.append(prev_close)
        prev_source_list.append(prev_source)

    df["ltp"] = ltp_list
    df["prev_close"] = prev_close_list
    df["prev_close_source"] = prev_source_list

    # ------------------ PnL Calculation ------------------
    df["pnl"] = (df["ltp"] - df["prev_close"]) * df.get("qty", 1)
    df["pnl_pct"] = np.where(
        df["prev_close"] > 0,
        (df["ltp"] - df["prev_close"]) / df["prev_close"] * 100,
        0
    )

    st.success("✅ Data fetched successfully!")

    st.dataframe(df[["symbol", "ltp", "prev_close", "pnl", "pnl_pct", "prev_close_source"]])

except Exception as e:
    st.error(f"❌ Error: {str(e)}")
    st.code(traceback.format_exc())
