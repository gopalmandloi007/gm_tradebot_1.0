import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta
import plotly.graph_objects as go
import traceback

# ------------------ All Helper Functions ------------------

def parse_definedge_csv_text(csv_text: str, timeframe: str = "day") -> tuple:
    """
    Parses the CSV text into a DataFrame.
    For simplicity, assumes standard CSV format.
    """
    try:
        df = pd.read_csv(io.StringIO(csv_text), header=None)
        if df.shape[1] < 6:
            return None, "Insufficient columns"
        df = df.rename(columns={0: "DateTime", 1: "Open", 2: "High", 3: "Low", 4: "Close", 5: "Volume"})
        df = df[["DateTime","Open","High","Low","Close","Volume"]].copy()

        # Parse date
        if timeframe == "day":
            df["Date"] = pd.to_datetime(df["DateTime"], format="%d%m%Y%H%M").dt.date
        else:
            df["Date"] = pd.to_datetime(df["DateTime"], format="%d%m%Y%H%M")
        return df, None
    except Exception as e:
        return None, str(e)

def get_robust_prev_close_from_hist(hist_df, today_date):
    """
    Computes the robust previous close from historical data.
    """
    try:
        # Filter data before today
        hist_df['Date'] = pd.to_datetime(hist_df['Date'])
        prev_days = hist_df[hist_df['Date'].dt.date < today_date]
        if prev_days.empty:
            return None, "No prior data"
        # Use the last available close
        last_row = prev_days.iloc[-1]
        return last_row["Close"], "last_close"
    except Exception as e:
        return None, str(e)

def get_prev_close_for_symbol(client, token, today_dt, symbol):
    """
    Fetches the previous close for a given symbol with robust fallback.
    """
    POSSIBLE_PREV_KEYS = [
        "prev_close", "previous_close", "previousClose", "previousClosePrice", "prevClose",
        "prevclose", "previousclose", "prev_close_price", "Close", "previous_close_price",
        "prev_close_val", "previous_close_val", "yesterday_close"
    ]

    prev_close_value = None
    prev_source = ""

    # 1. Try to get from quote API
    try:
        quote_resp = client.get_quotes(exchange="NSE", token=token)
        if isinstance(quote_resp, dict):
            for key in POSSIBLE_PREV_KEYS:
                if key in quote_resp and quote_resp[key] not in (None, "", []):
                    try:
                        prev_close_value = float(str(quote_resp[key]).replace(",", ""))
                        prev_source = "quote"
                        break
                    except Exception:
                        continue
        if prev_close_value is not None:
            return prev_close_value, prev_source
    except Exception:
        pass

    # 2. Fallback to historical CSV
    try:
        from_date = (today_dt - timedelta(days=30)).strftime("%d%m%Y%H%M")
        to_date = today_dt.strftime("%d%m%Y%H%M")
        hist_csv = client.historical_csv(segment="NSE", token=token, timeframe="day", frm=from_date, to=to_date)

        hist_df, err = parse_definedge_csv_text(hist_csv, timeframe="day")
        if hist_df is not None:
            prev_close_hist, reason = get_robust_prev_close_from_hist(hist_df, today_dt.date())
            if prev_close_hist is not None:
                return float(prev_close_hist), f"historical:{reason}"
    except Exception:
        pass

    # 3. Final fallback: use LTP
    try:
        quote_resp = client.get_quotes(exchange="NSE", token=token)
        if isinstance(quote_resp, dict):
            ltp = (quote_resp.get("ltp") or quote_resp.get("last_price") or
                   quote_resp.get("lastTradedPrice") or quote_resp.get("lastPrice"))
            try:
                ltp_val = float(ltp or 0.0)
            except Exception:
                ltp_val = 0.0
            return ltp_val, "ltp_fallback"
    except Exception:
        pass

    # If all fails, default to 0
    return 0.0, "default"

# ------------------ Streamlit app starts here ------------------

st.set_page_config(layout="wide")
st.title("📊 Trading Dashboard — Definedge (Risk Managed — Improved)")

# Defaults
DEFAULT_TOTAL_CAPITAL = 1400000
DEFAULT_INITIAL_SL_PCT = 2.0
DEFAULT_TARGETS = [10, 20, 30, 40]

# Helper: parse CSV
def parse_definedge_csv_text(csv_text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(csv_text), header=None, dtype=str)
    if df.shape[1] < 6:
        return pd.DataFrame()
    df = df.rename(columns={0: "DateTime", 1: "Open", 2: "High", 3: "Low", 4: "Close", 5: "Volume"})
    df = df[["DateTime","Open","High","Low","Close","Volume"]].copy()
    try:
        df["Date"] = pd.to_datetime(df["DateTime"], format="%d%m%Y%H%M").dt.strftime("%d/%m/%Y")
        df = df[["Date","Open","High","Low","Close","Volume"]]
    except Exception:
        pass
    return df

# Client login check
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

# Sidebar controls
st.sidebar.header("⚙️ Dashboard Settings & Risk")
capital = st.sidebar.number_input("Total Capital (₹)", value=DEFAULT_TOTAL_CAPITAL, step=10000, key="capital_input")
initial_sl_pct = st.sidebar.number_input("Initial Stop Loss (%)", value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1, key="initial_sl_input")/100
targets_input = st.sidebar.text_input("Targets % (comma separated)", ",".join(map(str, DEFAULT_TARGETS)), key="targets_input")

# Parse targets
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

# Fetch holdings
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
        # Defensive parsing
        try:
            avg_buy_price = float(item.get("avg_buy_price") or 0)
        except:
            avg_buy_price = 0.0
        try:
            dp_qty = float(item.get("dp_qty") or 0)
        except:
            dp_qty = 0.0
        try:
            t1_qty = float(item.get("t1_qty") or 0)
        except:
            t1_qty = 0.0
        try:
            holding_used = float(item.get("holding_used") or 0)
        except:
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
                # keep only NSE entries
                if sym_exchange and sym_exchange != "NSE":
                    continue
                symbol_name = sym_obj.get("tradingsymbol") or sym_obj.get("symbol") or item.get("tradingsymbol")
                token_id = sym_obj.get("token") or item.get("token")
                rows.append({
                    "symbol": symbol_name,
                    "token": token_id,
                    "avg_buy_price": avg_buy_price,
                    "quantity": total_qty,
                    "product_type": item.get("product_type", "")
                })

    if not rows:
        st.warning("⚠️ No NSE holdings found.")
        st.stop()

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["symbol"]).reset_index(drop=True)

    # Fetch live prices and prev_close
    st.info("Fetching live prices and previous close (robust logic).")
    prev_close_list = []
    prev_source_list = []

    today_dt = datetime.now()

    for idx, row in df.iterrows():
        token = row.get("token")
        symbol = row.get("symbol")
        prev_close, source = get_prev_close_for_symbol(client, token, today_dt, symbol)
        prev_close_list.append(prev_close)
        prev_source_list.append(source)

    # Assign to dataframe
    df["prev_close"] = prev_close_list
    df["prev_close_source"] = prev_source_list

    # Debug output
    st.write("Sample 'prev_close' values after fetch:", df[["symbol", "prev_close", "prev_close_source"]].head())

    # Convert to numeric
    df["prev_close"] = pd.to_numeric(df["prev_close"], errors="coerce").fillna(0)

except Exception as e:
    st.error(f"⚠️ Error fetching holdings or prices: {e}")
    st.text(traceback.format_exc())
    st.stop()

# Continue with your calculation and display logic...
# (Include your existing code from here onward, such as calculating PnL, stops, targets, etc.)
# For brevity, only the main changes are shown here.
