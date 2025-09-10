# final_holdings_dashboard.py
import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta, date
import plotly.graph_objects as go
import traceback
import requests

# ------------------ Configuration ------------------
st.set_page_config(layout="wide")
st.title("📊 Trading Dashboard — Definedge (Risk Managed — Improved)")

# ------------------ Defaults ------------------
DEFAULT_TOTAL_CAPITAL = 1400000
DEFAULT_INITIAL_SL_PCT = 2.0
DEFAULT_TARGETS = [10, 20, 30, 40]

# ------------------ Helpers ------------------
def safe_float(x):
    if x is None:
        return None
    try:
        s = str(x).replace(",", "").strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None

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

# ------------------ MAIN ------------------
client = st.session_state.get('client')
if not client:
    st.error('⚠️ Not logged in. Please login first from the Login page.')
    st.stop()

# Sidebar inputs
capital = st.sidebar.number_input('Total Capital (₹)', value=DEFAULT_TOTAL_CAPITAL, step=10000)
initial_sl_pct = st.sidebar.number_input('Initial Stop Loss (%)', value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1)/100
targets_input = st.sidebar.text_input('Targets % (comma separated)', ','.join(map(str, DEFAULT_TARGETS)))
try:
    target_pcts = sorted([max(0.0, float(t.strip())/100.0) for t in targets_input.split(',') if t.strip()])
    if not target_pcts:
        target_pcts = [t/100.0 for t in DEFAULT_TARGETS]
except Exception:
    st.sidebar.error('Invalid Targets input — using defaults')
    target_pcts = [t/100.0 for t in DEFAULT_TARGETS]

# ------------------ Holdings Fetch ------------------
try:
    holdings_resp = client.get_holdings()
    raw_holdings = holdings_resp.get('data', []) if holdings_resp else []
    rows = []
    for item in raw_holdings:
        dp_qty = safe_float(item.get('dp_qty')) or 0.0
        t1_qty = safe_float(item.get('t1_qty')) or 0.0
        trade_qty = safe_float(item.get('trade_qty')) or safe_float(item.get('holding_used')) or 0.0
        sell_amt = safe_float(item.get('sell_amt') or item.get('sell_amount') or item.get('sellAmt')) or 0.0
        avg_buy_price = safe_float(item.get('avg_buy_price') or item.get('average_price')) or 0.0
        ts_field = item.get('tradingsymbol')
        symbol = ts_field if isinstance(ts_field, str) else item.get('token')
        token = item.get('token')
        rows.append({
            'symbol': symbol,
            'token': token,
            'dp_qty': dp_qty,
            't1_qty': t1_qty,
            'trade_qty': int(trade_qty),
            'sell_amt': sell_amt,
            'avg_buy_price': avg_buy_price
        })
    df = pd.DataFrame(rows)
    if df.empty:
        st.warning('⚠️ No holdings found.')
        st.stop()

    # Aggregation
    df['buy_qty'] = df['dp_qty'] + df['t1_qty']
    df['open_qty'] = (df['buy_qty'] - df['trade_qty']).clip(lower=0).astype(int)
    df['quantity'] = df['open_qty']

    # Live LTP + prev close
    LTP_KEYS = ['ltp', 'last_price', 'lastTradedPrice']
    PREV_KEYS = ['prev_close','previous_close','previousClose']
    ltps, prevs = [], []
    for _, row in df.iterrows():
        ltp, prev = None, None
        try:
            q = client.get_quotes(exchange='NSE', token=row['token'])
            ltp = safe_float(find_in_nested(q, LTP_KEYS))
            prev = safe_float(find_in_nested(q, PREV_KEYS))
        except Exception:
            pass
        ltps.append(ltp or 0.0)
        prevs.append(prev)
    df['ltp'] = ltps
    df['prev_close'] = prevs

    # PnL calculations
    df['realized_pnl'] = df['sell_amt'] - (df['trade_qty'] * df['avg_buy_price'])
    df['unrealized_pnl'] = (df['ltp'] - df['avg_buy_price']) * df['open_qty']
    df['today_pnL'] = (df['ltp'] - df['prev_close']) * df['open_qty']
    df['pct_change'] = df.apply(lambda r: ((r['ltp'] - r['prev_close'])/r['prev_close']*100) if pd.notna(r['prev_close']) and r['prev_close'] != 0 else None, axis=1)
    df['total_pnl'] = df['realized_pnl'] + df['unrealized_pnl']

    # Portfolio KPIs
    total_today_pnl = df['today_pnL'].fillna(0).sum()
    st.subheader('💰 Summary')
    c1, c2 = st.columns(2)
    c1.metric('Today PnL', f"₹{total_today_pnl:,.2f}")
    if not df['pct_change'].isna().all():
        avg_pct = df['pct_change'].mean(skipna=True)
        c2.metric('% Change (avg)', f"{avg_pct:.2f}%")

    # Positions table
    st.subheader('📋 Positions')
    display_cols = ['symbol','quantity','avg_buy_price','ltp','prev_close','pct_change','today_pnL','realized_pnl','unrealized_pnl','total_pnl']
    st.dataframe(df[display_cols].sort_values(by='today_pnL', ascending=False), use_container_width=True)

except Exception as e:
    st.error(f"⚠️ Error: {e}")
    st.text(traceback.format_exc())
