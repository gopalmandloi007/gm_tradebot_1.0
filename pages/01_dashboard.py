import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta, date
import plotly.graph_objects as go
import traceback

# ------------------ Configuration ------------------
st.set_page_config(layout="wide")
st.title("📊 Trading Dashboard — Definedge (Risk Managed — Improved)")

# ------------------ Defaults ------------------
DEFAULT_TOTAL_CAPITAL = 1400000
DEFAULT_INITIAL_SL_PCT = 2.0
DEFAULT_TARGETS = [10, 20, 30, 40]

# ------------------ Helper: Robust Prev Close ------------------
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

# ------------------ Client check ------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

# ------------------ Sidebar (user controls) ------------------
st.sidebar.header("⚙️ Dashboard Settings & Risk")
capital = st.sidebar.number_input("Total Capital (₹)", value=DEFAULT_TOTAL_CAPITAL, step=10000, key="capital_input")
initial_sl_pct = st.sidebar.number_input("Initial Stop Loss (%)", value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1, key="initial_sl_input")/100
targets_input = st.sidebar.text_input("Targets % (comma separated)", ",".join(map(str, DEFAULT_TARGETS)), key="targets_input")

try:
    target_pcts = sorted([max(0.0, float(t.strip())/100.0) for t in targets_input.split(",") if t.strip()])
    if not target_pcts:
        target_pcts = [t/100.0 for t in DEFAULT_TARGETS]
except Exception:
    st.sidebar.error("Invalid Targets input — using defaults")
    target_pcts = [t/100.0 for t in DEFAULT_TARGETS]

trailing_thresholds = target_pcts
auto_refresh = st.sidebar.checkbox("Auto-refresh LTP on page interaction", value=False, key="auto_refresh")
show_actions = st.sidebar.checkbox("Show Action Buttons (Square-off / Place SL)", value=False, key="show_actions")
st.sidebar.markdown("---")

# ------------------ Fetch holdings ------------------
try:
    holdings_resp = client.get_holdings()
    if not holdings_resp or holdings_resp.get("status") != "SUCCESS":
        st.warning("⚠️ No holdings found or API returned error")
        st.stop()

    holdings = holdings_resp.get("data", [])
    if not holdings:
        st.info("✅ No holdings found.")
        st.stop()

    rows = []
    for item in holdings:
        try:
            avg_buy_price = float(item.get("avg_buy_price") or 0)
        except Exception:
            avg_buy_price = 0.0
        try:
            dp_qty = float(item.get("dp_qty") or 0)
        except Exception:
            dp_qty = 0.0
        try:
            t1_qty = float(item.get("t1_qty") or 0)
        except Exception:
            t1_qty = 0.0
        try:
            holding_used = float(item.get("holding_used") or 0)
        except Exception:
            holding_used = 0.0

        total_qty = int(dp_qty + t1_qty + holding_used)

        tradings = item.get("tradingsymbol") or []
        if isinstance(tradings, dict):
            tradings = [tradings]
        if isinstance(tradings, str):
            rows.append({
                "symbol": tradings,
                "token": item.get("token"),
                "avg_buy_price": avg_buy_price,
                "quantity": total_qty,
                "product_type": item.get("product_type", "")
            })
        else:
            for sym in tradings:
                sym_obj = sym if isinstance(sym, dict) else {}
                sym_exchange = sym_obj.get("exchange") if isinstance(sym_obj, dict) else None
                if sym_exchange and sym_exchange != "NSE":
                    continue
                rows.append({
                    "symbol": sym_obj.get("tradingsymbol") or sym_obj.get("symbol") or item.get("tradingsymbol"),
                    "token": sym_obj.get("token") or item.get("token"),
                    "avg_buy_price": avg_buy_price,
                    "quantity": total_qty,
                    "product_type": item.get("product_type", "")
                })

    if not rows:
        st.warning("⚠️ No NSE holdings found.")
        st.stop()

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["symbol"]).reset_index(drop=True)

    # ------------------ Fetch LTP + prev_close strictly from historical ------------------
    st.info("Fetching live prices and previous close (from historical only).")
    ltp_list = []
    prev_close_list = []
    prev_source_list = []

    today_dt = datetime.now()
    today_date = today_dt.date()

    last_hist_df = None

    for idx, row in df.iterrows():
        token = row.get("token")
        symbol = row.get("symbol")
        ltp = 0.0
        prev_close = None
        prev_source = "not_fetched"

        # Fetch LTP (for live values)
        try:
            quote_resp = client.get_quotes(exchange="NSE", token=token)
            if isinstance(quote_resp, dict):
                ltp_val = (quote_resp.get("ltp") or quote_resp.get("last_price") or
                           quote_resp.get("lastTradedPrice") or quote_resp.get("lastPrice") or quote_resp.get("ltpPrice"))
                ltp = float(ltp_val or 0.0)
        except Exception:
            ltp = 0.0

        # Fetch prev_close only from historical CSV
        try:
            from_date = (today_dt - timedelta(days=30)).strftime("%d%m%Y%H%M")
            to_date = today_dt.strftime("%d%m%Y%H%M")
            hist_csv = client.historical_csv(segment="NSE", token=token, timeframe="day", frm=from_date, to=to_date)

            hist_df, err = parse_definedge_csv(hist_csv, timeframe="day")
            if hist_df is None:
                raise Exception(f"parse_definedge_csv failed: {err}")

            last_hist_df = hist_df.copy()

            prev_close_val, reason = get_robust_prev_close_from_hist(hist_df, today_date)
            if prev_close_val is not None:
                prev_close = float(prev_close_val)
                prev_source = f"historical_csv:{reason}"
            else:
                prev_close = None
                prev_source = f"historical_missing:{reason}"
        except Exception as exc:
            prev_close = None
            prev_source = f"fallback_error:{str(exc)[:120]}"

        ltp_list.append(ltp)
        prev_close_list.append(prev_close)
        prev_source_list.append(prev_source)

    df["ltp"] = ltp_list
    df["prev_close"] = prev_close_list
    df["prev_close_source"] = prev_source_list

except Exception as e:
    st.error(f"⚠️ Error fetching holdings or prices: {e}")
    st.text(traceback.format_exc())
    st.stop()

# ------------------ Final historical sample display (optional) ------------------
try:
    if last_hist_df is not None and last_hist_df.shape[0] > 0:
        st.write("Historical data sample (last fetched symbol):")
        st.dataframe(last_hist_df.head())
except Exception:
    pass

# ------------------ Calculate P&L and other metrics ------------------
for col in ["avg_buy_price", "quantity", "ltp", "prev_close"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

df["invested_value"] = df["avg_buy_price"] * df["quantity"]
df["current_value"] = df["ltp"] * df["quantity"]
# Safe handling: if prev_close missing → today_pnl = 0
df["today_pnl"] = (df["ltp"] - df["prev_close"].fillna(df["ltp"])) * df["quantity"]
df["overall_pnl"] = df["current_value"] - df["invested_value"]
df["capital_allocation_%"] = (df["invested_value"] / capital) * 100
