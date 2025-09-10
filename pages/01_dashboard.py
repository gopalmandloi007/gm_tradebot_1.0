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

# copy your parse_definedge_csv_text & fetch_hist_for_date_range & get_robust_prev_close_from_hist here
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

# Sidebar risk inputs (unchanged)
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

# Fetch holdings
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
        trade_qty = safe_float(item.get('trade_qty'))
        if trade_qty is None:
            trade_qty = safe_float(item.get('holding_used')) or 0.0
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

    # Compute quantities
    df['open_qty'] = (df['buy_qty'] - df['trade_qty']).clip(lower=0).astype(int)
    df['sold_qty'] = df['trade_qty'].astype(int)
    df['quantity'] = df['open_qty']

    # Fetch LTP + prev_close
    st.info('Fetching live prices and previous close (robust logic).')
    ltp_list, prev_close_list, prev_source_list = [], [], []
    today_dt, today_date = datetime.now(), datetime.now().date()

    LTP_KEYS = ['ltp', 'last_price', 'lastTradedPrice', 'lastPrice', 'ltpPrice', 'last']
    POSSIBLE_PREV_KEYS = [
        'prev_close', 'previous_close', 'previousClose', 'previousClosePrice', 'prevClose',
        'prevclose', 'previousclose', 'prev_close_price', 'yesterdayClose', 'previous_close_price',
        'prev_close_val', 'previous_close_val', 'yesterday_close', 'close_prev'
    ]

    last_hist_df = None

    for idx, row in df.iterrows():
        token, prev_close_from_quote, ltp_val = row.get('token'), None, None
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
            prev_close_from_quote, ltp_val = None, None

        prev_close, prev_source = None, None
        if prev_close_from_quote is not None:
            prev_close, prev_source = float(prev_close_from_quote), 'quote'
        else:
            try:
                hist_df = pd.DataFrame()
                if hasattr(client, 'historical_csv'):
                    try:
                        from_date = (today_dt - timedelta(days=30)).strftime('%d%m%Y%H%M')
                        to_date = today_dt.strftime('%d%m%Y%H%M')
                        hist_csv = client.historical_csv(segment='NSE', token=token, timeframe='day', frm=from_date, to=to_date)
                        hist_df = parse_definedge_csv_text(hist_csv)
                    except Exception:
                        hist_df = pd.DataFrame()
                if (hist_df is None or hist_df.empty) and use_definedge_api_key:
                    api_key = st.session_state.get('definedge_api_key') or st.session_state.get('definedge_api_key_input')
                    if api_key:
                        hist_df = fetch_hist_for_date_range(api_key, 'NSE', token, today_dt - timedelta(days=30), today_dt)

                if hist_df is not None and not hist_df.empty:
                    last_hist_df = hist_df.copy()
                    prev_close_val, reason = get_robust_prev_close_from_hist(hist_df, today_date)
                    if prev_close_val is not None:
                        prev_close, prev_source = float(prev_close_val), f'historical:{reason}'
                    else:
                        prev_close, prev_source = None, f'historical_no_prev:{reason}'
                else:
                    prev_close, prev_source = None, 'no_hist'
            except Exception as exc:
                prev_close, prev_source = None, f'fallback_error:{str(exc)[:120]}'

        ltp_list.append(safe_float(ltp_val) or 0.0)
        prev_close_list.append(prev_close)
        prev_source_list.append(prev_source or 'unknown')

except Exception as e:
    st.error(f'⚠️ Error fetching holdings or prices: {e}')
    st.text(traceback.format_exc())
    st.stop()

# assign LTP and prev_close
df['ltp'] = pd.to_numeric(pd.Series(ltp_list), errors='coerce').fillna(0.0)
_df_prev = pd.to_numeric(pd.Series(prev_close_list), errors='coerce')
df['prev_close'] = _df_prev
df['prev_close_source'] = prev_source_list

# pnl calculations
df['realized_pnl'] = df['sell_amt'] - (df['trade_qty'] * df['avg_buy_price'])
df['unrealized_pnl'] = (df['ltp'] - df['avg_buy_price']) * df['open_qty']
df['today_pnL'] = (df['ltp'] - df['prev_close']) * df['open_qty']
df['pct_change'] = df.apply(lambda r: ((r['ltp'] - r['prev_close']) / r['prev_close'] * 100) if pd.notna(r['prev_close']) and r['prev_close'] != 0 else None, axis=1)
df['total_pnl'] = df['realized_pnl'] + df['unrealized_pnl']

# compatibility columns
df['avg_buy_price'] = df['avg_buy_price'].astype(float)
df['quantity'] = df['open_qty']
df['invested_value'] = df['avg_buy_price'] * df['quantity']
df['current_value'] = df['ltp'] * df['quantity']
df['overall_pnl'] = df['current_value'] - df['invested_value']
df['capital_allocation_%'] = (df['invested_value'] / capital) * 100

# stops/targets
def calc_stops_targets(row):
    avg = float(row.get('avg_buy_price') or 0.0)
    qty = int(row.get('quantity') or 0)
    ltp = float(row.get('ltp') or 0.0)
    if qty == 0 or avg == 0:
        return pd.Series({'side':'FLAT','initial_sl_price':0.0,'tsl_price':0.0,'targets':[0.0]*len(target_pcts),'initial_risk':0.0,'open_risk':0.0,'realized_if_tsl_hit':0.0})
    side = 'LONG' if qty > 0 else 'SHORT'
    if side == 'LONG':
        initial_sl_price = round(avg * (1 - initial_sl_pct), 4)
        targets = [round(avg * (1 + t), 4) for t in target_pcts]
        perc = (ltp / avg - 1) if avg > 0 else 0.0
        crossed_indices = [i for i, th in enumerate(trailing_thresholds) if perc >= th]
        if crossed_indices:
            idx_max = max(crossed_indices)
            tsl_pct = 0.0 if idx_max == 0 else trailing_thresholds[idx_max - 1]
            tsl_price = round(avg * (1 + tsl_pct), 4)
        else:
            tsl_price = initial_sl_price
        tsl_price = max(tsl_price, initial_sl_price)
        open_risk = round(max(0.0, (avg - tsl_price) * qty), 2)
        initial_risk = round(max(0.0, (avg - initial_sl_price) * qty), 2)
        realized_if_tsl_hit = round((tsl_price - avg) * qty, 2)
        return pd.Series({'side':side,'initial_sl_price':initial_sl_price,'tsl_price':tsl_price,'targets':targets,'initial_risk':initial_risk,'open_risk':open_risk,'realized_if_tsl_hit':realized_if_tsl_hit})
    else:
        avg_abs = abs(avg)
        initial_sl_price = round(avg_abs * (1 + initial_sl_pct), 4)
        targets = [round(avg_abs * (1 - t), 4) for t in target_pcts]
        perc = ((avg_abs - ltp) / avg_abs) if avg_abs > 0 else 0.0
        crossed_indices = [i for i, th in enumerate(trailing_thresholds) if perc >= th]
        if crossed_indices:
            idx_max = max(crossed_indices)
            tsl_pct = 0.0 if idx_max == 0 else trailing_thresholds[idx_max - 1]
            tsl_price = round(avg_abs * (1 - tsl_pct), 4)
        else:
            tsl_price = initial_sl_price
        tsl_price = min(tsl_price, initial_sl_price)
        open_risk = round(max(0.0, (tsl_price - avg_abs) * abs(qty)), 2)
        initial_risk = round(max(0.0, (initial_sl_price - avg_abs) * abs(qty)), 2)
        realized_if_tsl_hit = round((avg_abs - tsl_price) * abs(qty), 2)
        return pd.Series({'side':side,'initial_sl_price':initial_sl_price,'tsl_price':tsl_price,'targets':targets,'initial_risk':initial_risk,'open_risk':open_risk,'realized_if_tsl_hit':realized_if_tsl_hit})

df = pd.concat([df, df.apply(calc_stops_targets, axis=1)], axis=1)

# display
st.subheader("📊 Portfolio Holdings")
st.dataframe(df[['symbol','quantity','avg_buy_price','ltp','prev_close','pct_change','invested_value','current_value','overall_pnl','today_pnL','side','initial_sl_price','tsl_price','targets','initial_risk','open_risk','realized_if_tsl_hit']], use_container_width=True)

# ---------- Summary Metrics ----------
# compute totals before using
total_invested = df['invested_value'].sum()
total_current = df['current_value'].sum()
total_pnl = total_current - total_invested
cash_in_hand = capital - total_invested
total_today_pnl = df['today_pnL'].sum()

st.subheader("📌 Portfolio Summary")

# arrange vertically (column wise instead of row)
st.metric("💰 Total Invested", f"₹{total_invested:,.2f}")
st.metric("📈 Current Value", f"₹{total_current:,.2f}")
st.metric("📊 Total PnL", f"₹{total_pnl:,.2f}")
st.metric("📅 Today's PnL", f"₹{total_today_pnl:,.2f}")
st.metric("💵 Cash in Hand", f"₹{cash_in_hand:,.2f}")

# Portfolio Max Loss if all SL/TSL hit
portfolio_max_loss = df['open_risk'].sum()
st.error(f"⚠️ Max Loss if all SL/TSL Hit: ₹{portfolio_max_loss:,.2f}")

# ---------- Charts ----------
col1, col2 = st.columns(2)

# Pie charts
with col1:
    fig1 = go.Figure(data=[go.Pie(
        labels=df['symbol'],
        values=df['invested_value'],
        textinfo='label+percent',
        hole=0.3
    )])
    fig1.update_layout(title="Portfolio Allocation — Invested Value per Stock")
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    fig2 = go.Figure(data=[go.Pie(
        labels=['Invested','Cash in Hand'],
        values=[total_invested, cash_in_hand],
        textinfo='label+percent',
        hole=0.3
    )])
    fig2.update_traces(marker=dict(colors=['blue','green']))
    fig2.update_layout(title="Portfolio vs Cash Distribution")
    st.plotly_chart(fig2, use_container_width=True)

# Risk bar chart
st.subheader("📉 Risk Profile per Stock")

fig3 = go.Figure()
fig3.add_trace(go.Bar(
    x=df['symbol'], y=df['open_risk'],
    name='Open Risk', marker_color='red',
    text=[f"₹{v:,.0f}" for v in df['open_risk']], textposition="outside"
))
fig3.add_trace(go.Bar(
    x=df['symbol'], y=df['realized_if_tsl_hit'],
    name='Realized if TSL Hit', marker_color='green',
    text=[f"₹{v:,.0f}" for v in df['realized_if_tsl_hit']], textposition="outside"
))
fig3.update_layout(
    barmode='group',
    title="Open Risk vs Realized if TSL Hit (per Stock)",
    yaxis_title="₹ Value"
)
st.plotly_chart(fig3, use_container_width=True)
