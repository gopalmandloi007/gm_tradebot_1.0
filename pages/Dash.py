# final_holdings_dashboard.py
import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta, date
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import traceback
import requests

# ------------------ Configuration ------------------
st.set_page_config(layout="wide")
st.title("📊 Trading Dashboard — Definedge (Risk Managed — Improved) — FIXED")

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

debug = st.sidebar.checkbox('Show debug (raw holdings/quotes)', value=False)
use_definedge_api_key = st.sidebar.checkbox('Use Definedge API key for history fetch (if needed)', value=False)
if use_definedge_api_key:
    st.sidebar.text_input('Definedge API key (put into session_state as definedge_api_key)', key='definedge_api_key_input')

# Sidebar risk inputs
capital = st.sidebar.number_input('Total Capital (₹)', value=DEFAULT_TOTAL_CAPITAL, step=10000, key='capital_input')
initial_sl_pct = st.sidebar.number_input('Initial Stop Loss (%)', value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1, key='initial_sl_input')/100
targets_input = st.sidebar.text_input('Targets % (comma separated)', ','.join(map(str, DEFAULT_TARGETS)), key='targets_input')
try:
    target_pcts = sorted([max(0.0, float(t.strip())/100.0) for t in targets_input.split(',') if t.strip()])
    if not target_pcts:
        target_pcts = [t/100.0 for t in DEFAULT_TARGETS]
except Exception:
    st.sidebar.error('Invalid Targets input — using defaults')
    target_pcts = [t/100.0 for t in DEFAULT_TARGETS]
trailing_thresholds = target_pcts
show_actions = st.sidebar.checkbox('Show Action Buttons (Square-off / Place SL)', value=False, key='show_actions')

# ------------------ Fetch Holdings ------------------
try:
    holdings_resp = client.get_holdings()
    if debug:
        st.write("🔎 raw holdings response (first item):", holdings_resp if isinstance(holdings_resp, dict) else str(holdings_resp)[:1000])

    if not holdings_resp or holdings_resp.get('status') != 'SUCCESS':
        st.warning('⚠️ No holdings found or API returned error')
        st.stop()

    raw_holdings = holdings_resp.get('data', [])
    if not raw_holdings:
        st.info('✅ No holdings found.')
        st.stop()

    # Parse holdings: pick NSE tradingsymbol entry per item
    rows = []
    for item in raw_holdings:
        dp_qty = safe_float(item.get('dp_qty')) or 0.0
        t1_qty = safe_float(item.get('t1_qty')) or 0.0
        trade_qty = safe_float(item.get('trade_qty')) or safe_float(item.get('holding_used')) or 0.0
        sell_amt = safe_float(item.get('sell_amt') or item.get('sell_amount') or item.get('sellAmt')) or 0.0
        avg_buy_price = safe_float(item.get('avg_buy_price') or item.get('average_price')) or 0.0

        ts_field = item.get('tradingsymbol')
        nse_entry = None
        if isinstance(ts_field, list):
            for ts in ts_field:
                if isinstance(ts, dict) and ts.get('exchange') == 'NSE':
                    nse_entry = ts
                    break
        elif isinstance(ts_field, dict):
            if ts_field.get('exchange') == 'NSE':
                nse_entry = ts_field
        elif isinstance(ts_field, str):
            nse_entry = {'tradingsymbol': ts_field, 'exchange': 'NSE', 'token': item.get('token')}

        if not nse_entry:
            continue

        rows.append({
            'symbol': nse_entry.get('tradingsymbol') or '',
            'token': nse_entry.get('token') or item.get('token') or '',
            'dp_qty': dp_qty,
            't1_qty': t1_qty,
            'trade_qty': int(trade_qty),
            'sell_amt': sell_amt,
            'avg_buy_price': avg_buy_price,
            'raw': item
        })

    if not rows:
        st.warning('⚠️ No NSE holdings found after parsing.')
        st.stop()

    df = pd.DataFrame(rows)

    # Aggregate by symbol
    def _agg(g):
        buy_qty = (g['dp_qty'] + g['t1_qty']).sum()
        sold_qty = g['trade_qty'].sum()
        sell_amt = g['sell_amt'].sum()
        weighted_avg = (g['avg_buy_price'] * (g['dp_qty'] + g['t1_qty'])).sum() / max(buy_qty, 1)
        token = g['token'].iloc[0]
        return pd.Series({
            'dp_qty': g['dp_qty'].sum(),
            't1_qty': g['t1_qty'].sum(),
            'buy_qty': int(buy_qty),
            'trade_qty': int(sold_qty),
            'sell_amt': sell_amt,
            'avg_buy_price': float(weighted_avg),
            'token': token
        })

    df = df.groupby('symbol', as_index=False).apply(_agg).reset_index()
    df['open_qty'] = (df['buy_qty'] - df['trade_qty']).clip(lower=0).astype(int)
    df['sold_qty'] = df['trade_qty'].astype(int)
    df['quantity'] = df['open_qty']

    # Fetch LTP + prev_close
    st.info('Fetching live prices and previous close (robust logic).')
    ltp_list, prev_close_list, prev_source_list = [], [], []
    today_dt = datetime.now()
    today_date = today_dt.date()
    LTP_KEYS = ['ltp', 'last_price', 'lastTradedPrice', 'lastPrice', 'ltpPrice', 'last']
    POSSIBLE_PREV_KEYS = [
        'prev_close', 'previous_close', 'previousClose', 'previousClosePrice', 'prevClose',
        'prevclose', 'previousclose', 'prev_close_price', 'yesterdayClose', 'previous_close_price',
        'prev_close_val', 'previous_close_val', 'yesterday_close', 'close_prev'
    ]
    last_hist_df = None

    for idx, row in df.iterrows():
        token = row.get('token')
        prev_close_from_quote = None
        ltp_val = None
        try:
            quote_resp = client.get_quotes(exchange='NSE', token=token)
            if debug:
                st.write(f"quote_resp for {row['symbol'][:20]}:", quote_resp if isinstance(quote_resp, dict) else str(quote_resp)[:400])
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
            prev_source = 'quote'
        else:
            prev_close = None
            prev_source = 'no_data'

        ltp_list.append(safe_float(ltp_val) or 0.0)
        prev_close_list.append(prev_close)
        prev_source_list.append(prev_source or 'unknown')

except Exception as e:
    st.error(f'⚠️ Error fetching holdings or prices: {e}')
    st.text(traceback.format_exc())
    st.stop()

# Assign LTP / prev_close
df['ltp'] = pd.to_numeric(pd.Series(ltp_list), errors='coerce').fillna(0.0)
_df_prev = pd.to_numeric(pd.Series(prev_close_list), errors='coerce')
df['prev_close'] = _df_prev
df['prev_close_source'] = prev_source_list

# ------------------ PnL calculations ------------------
df['realized_pnl'] = df['sell_amt'] - (df['trade_qty'] * df['avg_buy_price'])
df['unrealized_pnl'] = (df['ltp'] - df['avg_buy_price']) * df['open_qty']
df['today_pnL'] = (df['ltp'] - df['prev_close']) * df['open_qty']
df['pct_change'] = df.apply(lambda r: ((r['ltp'] - r['prev_close']) / r['prev_close'] * 100) if pd.notna(r['prev_close']) and r['prev_close'] != 0 else None, axis=1)
df['total_pnl'] = df['realized_pnl'] + df['unrealized_pnl']
df['avg_buy_price'] = df['avg_buy_price'].astype(float)
df['quantity'] = df['open_qty']
df['invested_value'] = df['avg_buy_price'] * df['quantity']
df['current_value'] = df['ltp'] * df['quantity']
df['overall_pnl'] = df['current_value'] - df['invested_value']
df['capital_allocation_%'] = (df['invested_value'] / capital) * 100

# ------------------ Portfolio KPIs ------------------
total_invested = df['invested_value'].sum()
total_current = df['current_value'].sum()
total_overall_pnl = df['overall_pnl'].sum()
missing_prev_count = int(df['prev_close'].isna().sum())
total_today_pnl = df['today_pnL'].fillna(0.0).sum()
total_initial_risk = df['initial_risk'].sum() if 'initial_risk' in df.columns else 0.0
total_open_risk = df['open_risk'].sum() if 'open_risk' in df.columns else 0.0
total_realized_if_all_tsl = df['realized_if_tsl_hit'].sum() if 'realized_if_tsl_hit' in df.columns else 0.0

st.subheader('💰 Overall Summary')
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric('Total Invested', f'₹{total_invested:,.2f}')
k2.metric('Total Current', f'₹{total_current:,.2f}')
k3.metric('Unrealized PnL', f'₹{total_overall_pnl:,.2f}')
if total_today_pnl >= 0:
    k4.metric('Today PnL', f'₹{total_today_pnl:,.2f}', delta=f'₹{total_today_pnl:,.2f}')
else:
    k4.metric('Today PnL', f'₹{total_today_pnl:,.2f}', delta=f'₹{total_today_pnl:,.2f}', delta_color='inverse')
if missing_prev_count > 0:
    k4.caption(f"Note: {missing_prev_count} positions missing previous-close — their Today PnL not included.")
k5.metric('Open Risk (TSL)', f'₹{total_open_risk:,.2f}')

# ------------------ Portfolio Charts ------------------
st.subheader('📊 Portfolio Visuals')
fig = make_subplots(
    rows=1, cols=2,
    specs=[[{"type":"domain"}, {"type":"xy"}]],
    subplot_titles=("Capital Allocation %", "Open Risk per Position")
)

# Pie chart: Capital Allocation
fig.add_trace(
    go.Pie(
        labels=df['symbol'],
        values=df['invested_value'],
        textinfo='label+percent',
        hovertemplate='%{label}: ₹%{value:,.2f} (%{percent})<extra></extra>'
    ),
    row=1, col=1
)

# Bar chart: Open Risk
fig.add_trace(
    go.Bar(
        x=df['symbol'],
        y=df['open_risk'] if 'open_risk' in df.columns else [0]*len(df),
        text=[f'₹{v:,.0f}' for v in (df['open_risk'] if 'open_risk' in df.columns else [0]*len(df))],
        textposition='auto',
        marker_color='crimson',
        name='Open Risk'
    ),
    row=1, col=2
)

fig.update_layout(
    height=500,
    showlegend=True,
    title_text="Portfolio Capital Allocation & Open Risk Overview",
    title_x=0.5
)

st.plotly_chart(fig, use_container_width=True)

# ------------------ Positions Table ------------------
display_cols = ['symbol', 'quantity', 'open_qty', 'buy_qty', 'sold_qty', 'avg_buy_price', 'ltp', 'prev_close', 'pct_change', 'today_pnL', 'realized_pnl', 'unrealized_pnl', 'total_pnl', 'capital_allocation_%', 'initial_sl_price', 'tsl_price', 'initial_risk', 'open_risk']
st.subheader('📋 Positions & Risk Table')
st.dataframe(df[display_cols].sort_values(by='capital_allocation_%', ascending=False).reset_index(drop=True), use_container_width=True)

# ------------------ Export ------------------
st.subheader('📥 Export')
csv_bytes = df.to_csv(index=False).encode('utf-8')
st.download_button('Download positions with PnL (CSV)', csv_bytes, file_name='positions_pnl.csv', mime='text/csv')
