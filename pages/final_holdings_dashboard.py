# final_holdings_dashboard.py
# Integrated & fixed version for GM TradeBot holdings + trading plan
# Paste this file in your Streamlit pages folder (replace existing)

import streamlit as st
import pandas as pd
import numpy as np
import io
import math
from datetime import datetime, timedelta, date
import plotly.express as px
import plotly.graph_objects as go
import traceback
import requests

# ------------------ Page config ------------------
st.set_page_config(layout="wide", page_title="GM TradeBot — Holdings & Trading Plan")
st.title("📊 GM TradeBot — Final Holdings Dashboard + Trading Plan")

# ------------------ Defaults ------------------
DEFAULT_TOTAL_CAPITAL = 1_112_000  # example default (user provided earlier)
DEFAULT_INITIAL_SL_PCT = 2.0
DEFAULT_RISK_PCT = 2.0
DEFAULT_TARGET_RETURN_PCT = 50.0
DEFAULT_WIN_RATE = 0.35
DEFAULT_POSITION_SIZE_PCT = 10.0  # percentage of capital per position example

# ------------------ Helpers ------------------
def safe_float(x, default=None):
    if x is None:
        return default
    try:
        s = str(x).replace(",", "").strip()
        if s == "":
            return default
        return float(s)
    except Exception:
        return default

def safe_num(x):
    v = safe_float(x)
    return float(v) if v is not None else 0.0

def ensure_numeric_df(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
    return df

def dedupe_columns(df):
    # Remove duplicate column names, keep first occurrence
    return df.loc[:, ~df.columns.duplicated()].copy()

def find_in_nested(obj, keys):
    if obj is None:
        return None
    if isinstance(obj, dict):
        klower = {kk.lower() for kk in keys}
        for k, v in obj.items():
            if k is None:
                continue
            if str(k).lower() in klower:
                return v
            res = find_in_nested(v, keys)
            if res is not None:
                return res
    elif isinstance(obj, (list, tuple)):
        for it in obj:
            res = find_in_nested(it, keys)
            if res is not None:
                return res
    return None

def parse_definedge_csv_text(csv_text: str) -> pd.DataFrame:
    # robust parse for Definedge historical CSV
    if not csv_text or not isinstance(csv_text, str):
        return pd.DataFrame(columns=["DateTime", "Close"])
    try:
        df_raw = pd.read_csv(io.StringIO(csv_text), header=None, dtype=str)
    except Exception:
        return pd.DataFrame(columns=["DateTime", "Close"])
    if df_raw.shape[1] < 6:
        return pd.DataFrame(columns=["DateTime", "Close"])
    df = df_raw.rename(columns={0: "DateTime", 1: "Open", 2: "High", 3: "Low", 4: "Close", 5: "Volume"})
    df = df[["DateTime", "Open", "High", "Low", "Close", "Volume"]].copy()
    df['DateTime_parsed'] = pd.to_datetime(df['DateTime'], format="%d%m%Y%H%M", errors='coerce')
    if df['DateTime_parsed'].isna().all():
        df['DateTime_parsed'] = pd.to_datetime(df['DateTime'], format="%d%m%Y", errors='coerce')
    df['DateTime_parsed'] = pd.to_datetime(df['DateTime_parsed'], errors='coerce')
    df['Close'] = pd.to_numeric(df['Close'].str.replace(',', '').astype(str), errors='coerce')
    res = df[['DateTime_parsed', 'Close']].dropna(subset=['DateTime_parsed']).rename(columns={'DateTime_parsed': 'DateTime'})
    res = res.sort_values('DateTime').reset_index(drop=True)
    return res

def fetch_hist_for_date_range(api_key: str, segment: str, token: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    from_str = start_date.strftime("%d%m%Y") + "0000"
    to_str = end_date.strftime("%d%m%Y") + "1530"
    url = f"https://data.definedgesecurities.com/sds/history/{segment}/{token}/day/{from_str}/{to_str}"
    headers = {"Authorization": api_key}
    try:
        resp = requests.get(url, headers=headers, timeout=25)
        if resp.status_code == 200 and resp.text.strip():
            return parse_definedge_csv_text(resp.text)
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()

def get_robust_prev_close_from_hist(hist_df: pd.DataFrame, today_date: date):
    try:
        if hist_df is None or hist_df.empty:
            return None, "no_data"
        if 'DateTime' not in hist_df.columns or 'Close' not in hist_df.columns:
            return None, 'missing_cols'
        df = hist_df.dropna(subset=['DateTime', 'Close']).copy()
        if df.empty:
            return None, 'no_valid_rows'
        df['date_only'] = df['DateTime'].dt.date
        prev_dates = sorted([d for d in df['date_only'].unique() if d < today_date])
        if prev_dates:
            prev_trading_date = prev_dates[-1]
            prev_rows = df[df['date_only'] == prev_trading_date].sort_values('DateTime')
            val = prev_rows['Close'].dropna().iloc[-1]
            return float(val), f'prev_trading_date:{prev_trading_date.isoformat()}'
        closes = df['Close'].dropna().tolist()
        if len(closes) == 0:
            return None, 'no_closes'
        dedup = []
        last = None
        for v in closes:
            if last is None or v != last:
                dedup.append(v)
            last = v
        if len(dedup) >= 2:
            return float(dedup[-2]), 'dedup_second_last'
        else:
            return float(closes[-1]), 'last_available'
    except Exception as e:
        return None, f'error:{str(e)[:120]}'


# ------------------ UI Inputs ------------------
st.sidebar.header("⚙️ Dashboard Settings")
debug = st.sidebar.checkbox("Show debug (raw holdings/quotes)", value=False)
use_definedge_api_key = st.sidebar.checkbox("Use Definedge API key for history fetch (if needed)", value=False)
if use_definedge_api_key:
    st.sidebar.text_input("Definedge API key (will be read into session_state)", key="definedge_api_key_input")

capital = st.sidebar.number_input("Total Capital (₹)", value=DEFAULT_TOTAL_CAPITAL, step=10000, key="capital_input")
initial_sl_pct = st.sidebar.number_input("Initial Stop Loss (%)", value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1, key="initial_sl_input")/100.0
risk_pct_per_trade = st.sidebar.number_input("Risk per trade (%)", value=DEFAULT_RISK_PCT, min_value=0.1, max_value=10.0, step=0.1)/100.0
reward_risk_ratio = st.sidebar.number_input("R — Reward:Risk (e.g., 5)", value=5.0, min_value=0.1, step=0.1)

targets_default = st.sidebar.text_input("Targets % (comma separated)", value="10,20,30,40", key="targets_input")
try:
    target_pcts = sorted([max(0.0, float(t.strip())/100.0) for t in targets_default.split(",") if t.strip()])
    if not target_pcts:
        target_pcts = [0.1, 0.2, 0.3, 0.4]
except Exception:
    target_pcts = [0.1, 0.2, 0.3, 0.4]

# Average holding time inputs (user-specific)
st.sidebar.markdown("### 🕒 Holding time assumptions (days)")
avg_win_days = st.sidebar.number_input("Avg win holding days (12-20 suggested)", min_value=1, max_value=90, value=16)
avg_loss_days = st.sidebar.number_input("Avg loss holding days (3-5 suggested)", min_value=1, max_value=30, value=4)

# ------------------ Fetch holdings from client ------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first (set st.session_state['client']).")
    st.stop()

# Attempt to get holdings (wrap in try to show friendly error)
try:
    holdings_resp = client.get_holdings()
    if debug:
        st.write("🔎 Raw holdings response:", holdings_resp if isinstance(holdings_resp, dict) else str(holdings_resp)[:1000])
    if not holdings_resp:
        st.warning("⚠️ No holdings response from client.")
        st.stop()
    # Some APIs return {'status': 'SUCCESS', 'data': [...]}
    if isinstance(holdings_resp, dict) and holdings_resp.get("status"):
        if holdings_resp.get("status") != "SUCCESS":
            # maybe still contains data
            raw_holdings = holdings_resp.get("data", [])
        else:
            raw_holdings = holdings_resp.get("data", [])
    elif isinstance(holdings_resp, list):
        raw_holdings = holdings_resp
    else:
        # try to extract data
        raw_holdings = holdings_resp.get("data") if isinstance(holdings_resp, dict) else []
except Exception as exc:
    st.error("⚠️ Error fetching holdings from client: " + str(exc))
    st.text(traceback.format_exc())
    st.stop()

if not raw_holdings:
    st.info("No holdings found in account.")
    st.stop()

# ------------------ Parse holdings to DataFrame ------------------
rows = []
for item in raw_holdings:
    # robustly extract numeric/strings
    dp_qty = safe_num(item.get("dp_qty") if isinstance(item, dict) else None)
    t1_qty = safe_num(item.get("t1_qty") if isinstance(item, dict) else None)
    trade_qty = item.get("trade_qty") if isinstance(item, dict) else None
    trade_qty = safe_num(trade_qty) if trade_qty is not None else 0.0
    sell_amt = safe_num(item.get("sell_amt") or item.get("sell_amount") or item.get("sellAmt"))
    avg_buy_price = safe_num(item.get("avg_buy_price") or item.get("average_price"))
    ts_field = item.get("tradingsymbol") if isinstance(item, dict) else None
    token = None
    nse_symbol = ""
    if isinstance(ts_field, list):
        for ts in ts_field:
            if isinstance(ts, dict) and ts.get("exchange") == "NSE":
                nse_symbol = ts.get("tradingsymbol", "")
                token = ts.get("token") or token
                break
    elif isinstance(ts_field, dict):
        nse_symbol = ts_field.get("tradingsymbol", "")
        token = ts_field.get("token") or token
    elif isinstance(ts_field, str):
        nse_symbol = ts_field
        token = item.get("token") or token
    else:
        nse_symbol = item.get("symbol") or item.get("tradingsymbol") or ""

    rows.append({
        "symbol": nse_symbol,
        "token": token or item.get("token") or "",
        "dp_qty": dp_qty,
        "t1_qty": t1_qty,
        "trade_qty": int(trade_qty),
        "sell_amt": sell_amt,
        "avg_buy_price": avg_buy_price,
        "raw": item
    })

df = pd.DataFrame(rows)

# Aggregate by symbol (if duplicates)
def _agg(g):
    buy_qty = int((g["dp_qty"] + g["t1_qty"]).sum())
    sold_qty = int(g["trade_qty"].sum())
    sell_amt = safe_num(g["sell_amt"].sum())
    weighted_avg = 0.0
    try:
        weighted_avg = (g["avg_buy_price"] * (g["dp_qty"] + g["t1_qty"])).sum() / max((g["dp_qty"] + g["t1_qty"]).sum(), 1)
    except Exception:
        weighted_avg = safe_num(g["avg_buy_price"].mean())
    token = g["token"].iloc[0] if "token" in g else ""
    return pd.Series({
        "dp_qty": g["dp_qty"].sum(),
        "t1_qty": g["t1_qty"].sum(),
        "buy_qty": buy_qty,
        "trade_qty": sold_qty,
        "sell_amt": sell_amt,
        "avg_buy_price": float(weighted_avg),
        "token": token
    })

try:
    df = df.groupby("symbol", as_index=False).apply(_agg).reset_index()
except Exception:
    # fallback: keep as-is
    df = df.reset_index(drop=True)

# Compute quantities
df["open_qty"] = ((df.get("buy_qty", 0) - df.get("trade_qty", 0))).clip(lower=0).astype(int)
df["sold_qty"] = df.get("trade_qty", 0).astype(int)
df["quantity"] = df["open_qty"]

# Fetch LTP / prev_close for each token via client.get_quotes
st.info("Fetching live LTPs & previous close (robust)...")
ltp_list = []
prev_close_list = []
prev_source_list = []
today_dt = datetime.now()
today_date = today_dt.date()

LTP_KEYS = ["ltp", "last_price", "lastTradedPrice", "lastPrice", "ltpPrice", "last"]
POSSIBLE_PREV_KEYS = [
    "prev_close", "previous_close", "previousClose", "previousClosePrice", "prevClose",
    "prevclose", "previousclose", "prev_close_price", "yesterdayClose", "previous_close_price",
    "prev_close_val", "previous_close_val", "yesterday_close", "close_prev"
]
last_hist_df = None

for idx, row in df.iterrows():
    token = row.get("token")
    prev_close_from_quote = None
    ltp_val = None
    # get quotes
    try:
        quote_resp = client.get_quotes(exchange="NSE", token=token) if token else {}
        if debug:
            st.write(f"Quote for {row.get('symbol')}: {quote_resp}")
        if isinstance(quote_resp, dict) and quote_resp:
            found_ltp = find_in_nested(quote_resp, LTP_KEYS)
            if found_ltp is not None:
                ltp_val = safe_float(found_ltp)
            found_prev = find_in_nested(quote_resp, POSSIBLE_PREV_KEYS)
            if found_prev is not None:
                prev_close_from_quote = safe_float(found_prev)
    except Exception:
        prev_close_from_quote = None
        ltp_val = None

    prev_close = None
    prev_source = None

    if prev_close_from_quote is not None:
        prev_close = float(prev_close_from_quote)
        prev_source = "quote"
    else:
        # fallback: try client.historical_csv or Definedge API if enabled
        try:
            hist_df = pd.DataFrame()
            if hasattr(client, "historical_csv"):
                try:
                    from_date = (today_dt - timedelta(days=30)).strftime("%d%m%Y%H%M")
                    to_date = today_dt.strftime("%d%m%Y%H%M")
                    hist_csv = client.historical_csv(segment="NSE", token=token, timeframe="day", frm=from_date, to=to_date)
                    hist_df = parse_definedge_csv_text(hist_csv)
                except Exception:
                    hist_df = pd.DataFrame()
            if (hist_df is None or hist_df.empty) and use_definedge_api_key:
                api_key = st.session_state.get("definedge_api_key") or st.session_state.get("definedge_api_key_input")
                if api_key:
                    hist_df = fetch_hist_for_date_range(api_key, "NSE", token, today_dt - timedelta(days=30), today_dt)
            if hist_df is not None and not hist_df.empty:
                last_hist_df = hist_df.copy()
                prev_close_val, reason = get_robust_prev_close_from_hist(hist_df, today_date)
                if prev_close_val is not None:
                    prev_close = float(prev_close_val)
                    prev_source = f"historical:{reason}"
                else:
                    prev_close = None
                    prev_source = f"historical_no_prev:{reason}"
            else:
                prev_close = None
                prev_source = "no_hist"
        except Exception as exc:
            prev_close = None
            prev_source = f"fallback_error:{str(exc)[:120]}"

    ltp_list.append(safe_float(ltp_val, 0.0) or 0.0)
    prev_close_list.append(prev_close)
    prev_source_list.append(prev_source or "unknown")

# show some histif available
try:
    if "last_hist_df" in locals() and last_hist_df is not None and last_hist_df.shape[0] > 0 and debug:
        st.write("Last historical sample:")
        st.dataframe(last_hist_df.head())
except Exception:
    pass

# Assign LTP/prev_close to df
df["ltp"] = pd.to_numeric(pd.Series(ltp_list), errors="coerce").fillna(0.0)
_df_prev = pd.to_numeric(pd.Series(prev_close_list), errors="coerce")
df["prev_close"] = _df_prev
df["prev_close_source"] = prev_source_list

# Calculations: pnl, unrealized, pct_change
df["realized_pnl"] = df.get("sell_amt", 0.0) - (df.get("trade_qty", 0.0) * df.get("avg_buy_price", 0.0))
df["realized_pnl"] = pd.to_numeric(df["realized_pnl"], errors="coerce").fillna(0.0)
df["unrealized_pnl"] = (df["ltp"] - df["avg_buy_price"]) * df["open_qty"]
df["today_pnL"] = (df["ltp"] - df["prev_close"]) * df["open_qty"]
df["pct_change"] = df.apply(lambda r: ((r["ltp"] - r["prev_close"]) / r["prev_close"] * 100) if pd.notna(r["prev_close"]) and r["prev_close"] != 0 else None, axis=1)
df["total_pnl"] = df["realized_pnl"] + df["unrealized_pnl"]

# compatibility
df["avg_buy_price"] = pd.to_numeric(df["avg_buy_price"], errors="coerce").fillna(0.0)
df["quantity"] = df["open_qty"]
df["invested_value"] = df["avg_buy_price"] * df["quantity"]
df["current_value"] = df["ltp"] * df["quantity"]
df["overall_pnl"] = df["current_value"] - df["invested_value"]

# compute initial_risk / open_risk per position based on initial_sl_pct and TSL logic
def calc_stops_targets(row):
    avg = float(safe_num(row.get("avg_buy_price")))
    qty = int(row.get("quantity") or 0)
    ltp = float(safe_num(row.get("ltp")))
    if qty == 0 or avg == 0:
        return pd.Series({
            "side": "FLAT",
            "initial_sl_price": 0.0,
            "tsl_price": 0.0,
            "targets": [0.0] * len(target_pcts),
            "initial_risk": 0.0,
            "open_risk": 0.0,
            "realized_if_tsl_hit": 0.0
        })
    side = "LONG" if qty > 0 else "SHORT"
    if side == "LONG":
        initial_sl_price = round(avg * (1 - initial_sl_pct), 4)
        targets = [round(avg * (1 + t), 4) for t in target_pcts]
        perc = (ltp / avg - 1) if avg > 0 else 0.0
        crossed_indices = [i for i, th in enumerate(target_pcts) if perc >= th]
        if crossed_indices:
            idx_max = max(crossed_indices)
            tsl_pct = 0.0 if idx_max == 0 else target_pcts[idx_max - 1]
            tsl_price = round(avg * (1 + tsl_pct), 4)
        else:
            tsl_price = initial_sl_price
        tsl_price = max(tsl_price, initial_sl_price)
        open_risk = round(max(0.0, (avg - tsl_price) * qty), 2)
        initial_risk = round(max(0.0, (avg - initial_sl_price) * qty), 2)
        realized_if_tsl_hit = round((tsl_price - avg) * qty, 2)
        return pd.Series({
            "side": side,
            "initial_sl_price": initial_sl_price,
            "tsl_price": tsl_price,
            "targets": targets,
            "initial_risk": initial_risk,
            "open_risk": open_risk,
            "realized_if_tsl_hit": realized_if_tsl_hit
        })
    else:
        avg_abs = abs(avg)
        initial_sl_price = round(avg_abs * (1 + initial_sl_pct), 4)
        targets = [round(avg_abs * (1 - t), 4) for t in target_pcts]
        perc = ((avg_abs - ltp) / avg_abs) if avg_abs > 0 else 0.0
        crossed_indices = [i for i, th in enumerate(target_pcts) if perc >= th]
        if crossed_indices:
            idx_max = max(crossed_indices)
            tsl_pct_down = 0.0 if idx_max == 0 else target_pcts[idx_max - 1]
            tsl_price = round(avg_abs * (1 - tsl_pct_down), 4)
        else:
            tsl_price = initial_sl_price
        open_risk = round(max(0.0, (tsl_price - avg_abs) * abs(qty)), 2)
        initial_risk = round(max(0.0, (initial_sl_price - avg_abs) * abs(qty)), 2)
        realized_if_tsl_hit = round((avg_abs - tsl_price) * abs(qty), 2)
        return pd.Series({
            "side": side,
            "initial_sl_price": initial_sl_price,
            "tsl_price": tsl_price,
            "targets": targets,
            "initial_risk": initial_risk,
            "open_risk": open_risk,
            "realized_if_tsl_hit": realized_if_tsl_hit
        })

stoppers = df.apply(calc_stops_targets, axis=1)
df = pd.concat([df, stoppers], axis=1)

# add target price columns
for i, tp in enumerate(target_pcts, start=1):
    df[f"target_{i}_pct"] = tp * 100
    df[f"target_{i}_price"] = df["targets"].apply(lambda lst, i=i: round(lst[i-1], 4) if isinstance(lst, list) and len(lst) >= i else 0.0)

# ensure numeric columns
numeric_cols = ["invested_value", "current_value", "overall_pnl", "initial_risk", "open_risk", "realized_if_tsl_hit", "ltp", "avg_buy_price"]
df = ensure_numeric_df(df, numeric_cols)

# dedupe duplicate column names before display/plotting
df = dedupe_columns(df)

# Portfolio KPIs
total_invested = safe_num(df["invested_value"].sum())
total_current = safe_num(df["current_value"].sum())
total_overall_pnl = safe_num(df["overall_pnl"].sum())
missing_prev_count = int(df["prev_close"].isna().sum())
total_today_pnl = safe_num(df["today_pnL"].fillna(0.0).sum())
total_initial_risk = safe_num(df["initial_risk"].sum())
total_open_risk = safe_num(df["open_risk"].sum())
total_realized_if_all_tsl = safe_num(df["realized_if_tsl_hit"].sum())

# Display KPIs
st.subheader("💰 Overall Summary")
k1, k2, k3, k4, k5 = st.columns(5)

def safe_metric(col, label, value):
    try:
        col.metric(label, f"₹{value:,.2f}")
    except Exception:
        col.metric(label, f"₹{value}")

safe_metric(k1, "Total Invested", total_invested)
safe_metric(k2, "Total Current", total_current)
safe_metric(k3, "Unrealized PnL", total_overall_pnl)

# Today PnL with delta
try:
    if total_today_pnl >= 0:
        k4.metric("Today PnL", f"₹{total_today_pnl:,.2f}", delta=f"₹{total_today_pnl:,.2f}")
    else:
        k4.metric("Today PnL", f"₹{total_today_pnl:,.2f}", delta=f"₹{total_today_pnl:,.2f}", delta_color="inverse")
except Exception:
    k4.metric("Today PnL", f"₹{total_today_pnl}")

safe_metric(k5, "Open Risk (TSL)", total_open_risk)
if missing_prev_count > 0:
    k4.caption(f"Note: {missing_prev_count} positions missing previous-close — Today PnL may be incomplete.")

# Positions table display with dedupe protection
st.subheader("📋 Positions & Risk Table")
display_cols = [
    "symbol", "quantity", "open_qty", "buy_qty", "sold_qty",
    "avg_buy_price", "ltp", "prev_close", "pct_change",
    "today_pnL", "realized_pnl", "unrealized_pnl", "total_pnl",
    "capital_allocation_%", "initial_sl_price", "tsl_price", "initial_risk", "open_risk"
]
# compute capital_allocation_% if missing
if "capital_allocation_%" not in df.columns:
    try:
        df["capital_allocation_%"] = (df["invested_value"] / max(float(capital), 1.0)) * 100.0
    except Exception:
        df["capital_allocation_%"] = 0.0

# ensure unique columns again
df = dedupe_columns(df)

try:
    show_df = df[[c for c in display_cols if c in df.columns]].sort_values(by="capital_allocation_%", ascending=False).reset_index(drop=True)
    # convert any object columns that are dict/list to string to avoid pyarrow errors
    for col in show_df.columns:
        if show_df[col].apply(lambda x: isinstance(x, (dict, list))).any():
            show_df[col] = show_df[col].apply(lambda x: str(x))
    st.dataframe(show_df, use_container_width=True)
except Exception as e:
    st.write("Could not render positions table due to:", str(e))
    st.write("Showing raw dataframe:")
    st.dataframe(df.head(50), use_container_width=True)

# Charts and visualizations
if not df.empty:
    st.subheader("📊 Capital Allocation")
    try:
        fig_pie = px.pie(df, names="symbol", values="invested_value", title="Capital Allocation (by invested amount)", hover_data=["capital_allocation_%", "quantity"])
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig_pie, use_container_width=True)
    except Exception as e:
        st.write("Could not render capital allocation pie:", str(e))

    st.subheader("📈 Risk Breakdown (per stock)")
    try:
        risk_df = df.sort_values("open_risk", ascending=False).copy()
        risk_df["initial_risk"] = pd.to_numeric(risk_df["initial_risk"], errors="coerce").fillna(0.0)
        risk_df["open_risk"] = pd.to_numeric(risk_df["open_risk"], errors="coerce").fillna(0.0)
        max_bars = st.sidebar.number_input("Show top N symbols by open risk", min_value=3, max_value=200, value=10, step=1, key="topn_risk")
        plot_df = risk_df.head(int(max_bars))
        # ensure no mixed-types
        plot_df = plot_df.copy()
        plot_df["initial_risk"] = plot_df["initial_risk"].astype(float)
        plot_df["open_risk"] = plot_df["open_risk"].astype(float)
        fig_bar = px.bar(plot_df, x="symbol", y=["initial_risk", "open_risk"], title="Initial Risk vs Open Risk per Stock", labels={"value": "Amount (₹)", "symbol": "Symbol"})
        fig_bar.update_layout(barmode="group", xaxis={"categoryorder": "total descending"})
        st.plotly_chart(fig_bar, use_container_width=True)
    except Exception as e:
        st.write("Could not render risk bar chart —", str(e))

    # SL & target prices table
    try:
        st.subheader("🎯 SL & Target Prices (per position)")
        target_cols = ["initial_sl_price"] + [f"target_{i}_price" for i in range(1, len(target_pcts) + 1)]
        available_cols = [c for c in (["symbol"] + target_cols) if c in df.columns]
        sl_table = df[available_cols].fillna(0).reset_index(drop=True)
        st.dataframe(sl_table, use_container_width=True)
    except Exception as e:
        st.write("Could not render SL & Targets table —", str(e))

# ------------------ Trading Plan Calculations (EV, ET, Trades needed) ------------------

st.set_page_config(page_title="Trading Plan Dashboard", layout="wide")

st.title("📈 Trading Plan Dashboard — Auto Calculator (by Gopal Mandloi)")

# ---------------------- USER INPUTS ----------------------
st.header("🔧 Input Parameters")

capital = st.number_input("💰 Total Capital (₹)", value=1112000.0, step=10000.0)
position_size_pct = st.number_input("📦 Position Size (% of Capital per trade)", value=10.0, step=1.0) / 100.0
risk_pct_per_trade = st.number_input("⚠️ Risk per Trade (%)", value=2.0, step=0.5) / 100.0
total_risk_cap_pct = st.number_input("🔻 Risk of Total Capital (%)", value=0.5, step=0.1) / 100.0
reward_risk_ratio = st.number_input("💹 Reward : Risk Ratio", value=5.0, step=0.5)
win_rate = st.number_input("✅ Win Rate (Accuracy %)", value=35.0, step=1.0) / 100.0
target_profit_pct = st.number_input("🎯 Target Profit (Yearly %)", value=50.0, step=5.0) / 100.0
target_days = st.number_input("📅 Target Time (Days)", value=365, step=10)
max_drawdown_pct = st.number_input("📉 Max Drawdown (%)", value=5.0, step=0.5) / 100.0
avg_day_win = st.number_input("🕒 Avg Holding Days (Winning Trade)", value=12, step=1)
avg_day_loss = st.number_input("🕓 Avg Holding Days (Losing Trade)", value=4, step=1)

# ---------------------- CALCULATIONS ----------------------
position_size = capital * position_size_pct
risk_per_trade = position_size * risk_pct_per_trade
total_risk_cap = capital * total_risk_cap_pct
reward_per_win = risk_per_trade * reward_risk_ratio
target_profit = capital * target_profit_pct
max_drawdown = capital * max_drawdown_pct

# Expected Value (EV) per trade
expected_value_per_trade = (win_rate * reward_risk_ratio) - (1 - win_rate)
expected_value_pct = expected_value_per_trade * risk_pct_per_trade * 100
expected_value_absolute = capital * (expected_value_per_trade * risk_pct_per_trade)

# Expected holding days per trade (weighted avg)
expected_days_per_trade = (win_rate * avg_day_win) + ((1 - win_rate) * avg_day_loss)

# How many trades to achieve target
target_multiplier = target_profit_pct
if expected_value_per_trade > 0:
    required_trades = math.log(1 + target_multiplier) / math.log(1 + (expected_value_per_trade * risk_pct_per_trade))
    required_trades = math.ceil(required_trades)
else:
    required_trades = float("inf")

# Expected total time (in days)
if math.isfinite(required_trades):
    total_days_required = required_trades * expected_days_per_trade
else:
    total_days_required = float("inf")

# Losing trades caution
losing_trades_caution = max(1, int(total_risk_cap / risk_per_trade))

# ---------------------- TABLE DATA ----------------------
data = [
    ["Total Capital", f"{capital:,.0f}", "Trading capital"],
    ["Position Size", f"{position_size:,.0f}", "Per trade exposure"],
    ["Risk per Trade (2%)", f"{risk_per_trade:,.0f}", "Loss per trade"],
    ["Risk of Total Capital (0.5%)", f"{total_risk_cap:,.0f}", "Max loss per trade"],
    ["Reward per Win", f"{reward_per_win:,.0f}", "Target profit per trade"],
    ["Win Rate (Accuracy)", f"{win_rate*100:.2f}", "Based on system performance"],
    ["Target Profit (50% Yearly)", f"{target_profit:,.0f}", "Expected return goal"],
    ["Target Time (One Year)", f"{target_days}", "Expected return goal time"],
    ["Max Drawdown (5%)", f"{max_drawdown:,.0f}", "Max drawdown allowed 5% of total capital"],
    ["Expected Value per Trade", f"{expected_value_absolute:,.2f}", f"EV = ({win_rate:.2f}×{reward_risk_ratio}) - ({1-win_rate:.2f})"],
    ["Expected Value per Trade (%)", f"{expected_value_pct:.3f}%", "Average return % per trade"],
    ["Trades Needed for Target", f"{required_trades}", "Required trades to gain 50% of capital"],
    ["Avg Day Holding (Win)", f"{avg_day_win}", "Average holding days for winning trade"],
    ["Avg Day Holding (Loss)", f"{avg_day_loss}", "Average holding days for losing trade"],
    ["Expected Time per Trade", f"{expected_days_per_trade:.2f}", "Weighted avg days per trade"],
    ["Time Needed for Target (Days)", f"{total_days_required:,.0f}", "Approx time to reach target"],
    ["Losing Trades Caution (A/F N Trades)", f"{losing_trades_caution}", "Stop trading after these many consecutive losses"],
    ["Stage-I (Initial Trade Capital)", f"{position_size:,.0f}", "Use 10–20% capital for testing"],
    ["Stage-II (Confidence Build)", "1", "After 1 profitable trade, increase exposure to 30–50%"],
    ["Stage-III (Fully Financed)", "8–10", "After 8–10 winning trades, use 100% capital"],
    ["Stage-IV (Compounding Phase)", "10+", "Increase position size gradually after consistent wins"],
    ["Slow Down", "-", "Back-to-back 5 stop losses"],
    ["Stop Trading for a Week", "-", "Back-to-back 10 stop losses"],
    ["Stop Trading for a Month", "-", "Back-to-back 15 stop losses"],
    ["Break Taken", "-", "After 25 consecutive stop losses"],
    ["Increase Position Size", "-", "Back-to-back 5 targets hit"],
]

df = pd.DataFrame(data, columns=["Parameter", "Value", "Notes"])

# ---------------------- DISPLAY ----------------------
st.subheader("📊 Trading Plan Summary Table")
st.dataframe(df, use_container_width=True, hide_index=True)

# Download option
csv = df.to_csv(index=False).encode("utf-8")
st.download_button("📥 Download this Table as CSV", csv, "trading_plan_summary.csv", "text/csv")

# ---------------------- INTERPRETATION ----------------------
st.markdown(f"""
---

### 🧠 Interpretation & Key Insights

- **Expected Value (EV)** = {expected_value_pct:.3f}% per trade → your average return (after wins & losses).  
- **Trades Required:** ≈ **{required_trades} trades** to reach a **{target_profit_pct*100:.0f}%** return target.  
- **Total Time Needed:** ≈ **{total_days_required:,.0f} days** assuming consistent performance and same holding period.  
- **Expected Holding Time:** ~{expected_days_per_trade:.2f} days per trade (weighted average).  

#### ⚠️ Discipline Alerts
- ❌ Stop trading after **{losing_trades_caution} consecutive stop-losses**.  
- 🧘 Take a **1-week break after 10** consecutive losses.  
- 💪 Increase position size only after **5 consecutive targets hit**.  

---

This model helps visualize realistic expectations for compounding-based trading growth.  
Keep updating your **Win Rate**, **Risk %,** and **Reward Ratio** based on real data every quarter.  
""")

# ------------------ Current R per holding & top >5R detection ------------------
st.subheader("🔥 Current R per Holding & High-R stocks")
def calc_current_R(row):
    denom = (row.get("avg_buy_price") - row.get("initial_sl_price"))
    try:
        if denom == 0 or pd.isna(denom):
            return np.nan
        return (row.get("ltp") - row.get("avg_buy_price")) / denom
    except Exception:
        return np.nan

df["current_R"] = df.apply(calc_current_R, axis=1)
highR_df = df[df["current_R"].notna() & (df["current_R"] >= 5)].copy()
if not highR_df.empty:
    st.write("Holdings with current R ≥ 5")
    st.dataframe(highR_df[["symbol", "current_R", "unrealized_pnl", "overall_pnl"]].sort_values("current_R", ascending=False).reset_index(drop=True))
else:
    st.info("No holdings currently ≥ 5R")

# ------------------ Export and downloads ------------------
st.markdown("---")
st.header("📥 Export / Download")

# download positions csv
try:
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download positions with PnL (CSV)", csv_bytes, file_name="positions_pnl.csv", mime="text/csv")
except Exception as e:
    st.write("Could not prepare CSV export:", str(e))

# download plan summary CSV
plan_summary = {
    "capital": capital,
    "risk_pct_per_trade": risk_pct_per_trade,
    "risk_per_trade_amt": risk_amount,
    "win_rate_used": used_win_rate,
    "avg_win_days_used": used_avg_win_days,
    "avg_loss_days_used": used_avg_loss_days,
    "R": reward_risk_ratio,
    "EV_per_trade": ev_per_trade,
    "Trades_needed_for_target": (math.ceil(trades_needed) if math.isfinite(trades_needed) else None),
    "Expected_days_to_target": (int(expected_total_days) if math.isfinite(expected_total_days) else None),
    "Total_open_risk": total_open_risk
}
try:
    st.download_button("Download Plan Summary (CSV)", data=pd.DataFrame([plan_summary]).to_csv(index=False).encode("utf-8"), file_name="trading_plan_summary.csv", mime="text/csv")
except Exception:
    pass

st.success("✅ Dashboard computed. Review charts and exports above.")

# ------------------ End ------------------
