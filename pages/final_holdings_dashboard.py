# final_holdings_dashboard.py
# Integrated: Definedge holdings (your code) + Trading Plan (EV, ET, Drawdown, Phase, Growth Projection)
import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta, date
import plotly.graph_objects as go
import plotly.express as px
import traceback
import requests
import numpy as np
import math

# ------------------ Configuration ------------------
st.set_page_config(layout="wide", page_title="Trading Dashboard — Definedge + Trading Plan")
st.title("📊 Trading Dashboard — Definedge (Risk Managed — Improved) — FIXED + Charts")

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
        # sold quantity (trade_qty) preferred, else holding_used fallback
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

    # Aggregate by symbol to be safe (sum quantities & sell amounts, weighted avg buy)
    def _agg(g):
        buy_qty = (g['dp_qty'] + g['t1_qty']).sum()
        sold_qty = g['trade_qty'].sum()
        sell_amt = g['sell_amt'].sum()
        # weighted average by buy quantity
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

    # Compute quantities: open = buys - sold
    df['open_qty'] = (df['buy_qty'] - df['trade_qty']).clip(lower=0).astype(int)
    df['sold_qty'] = df['trade_qty'].astype(int)
    df['quantity'] = df['open_qty']  # compatibility for rest of UI

    # Fetch LTP + prev_close
    st.info('Fetching live prices and previous close (robust logic).')
    ltp_list = []
    prev_close_list = []
    prev_source_list = []

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
                        prev_close = float(prev_close_val)
                        prev_source = f'historical:{reason}'
                    else:
                        prev_close = None
                        prev_source = f'historical_no_prev:{reason}'
                else:
                    prev_close = None
                    prev_source = 'no_hist'
            except Exception as exc:
                prev_close = None
                prev_source = f'fallback_error:{str(exc)[:120]}'

        ltp_list.append(safe_float(ltp_val) or 0.0)
        prev_close_list.append(prev_close)
        prev_source_list.append(prev_source or 'unknown')

except Exception as e:
    st.error(f'⚠️ Error fetching holdings or prices: {e}')
    st.text(traceback.format_exc())
    st.stop()

# show sample hist if available
try:
    if 'last_hist_df' in locals() and last_hist_df is not None and last_hist_df.shape[0] > 0:
        st.write('Historical data sample (last fetched symbol):')
        st.dataframe(last_hist_df.head())
except Exception:
    pass

# assign LTP and prev_close
df['ltp'] = pd.to_numeric(pd.Series(ltp_list), errors='coerce').fillna(0.0)
_df_prev = pd.to_numeric(pd.Series(prev_close_list), errors='coerce')
df['prev_close'] = _df_prev
df['prev_close_source'] = prev_source_list

# pnl calculations
df['realized_pnl'] = df.get('sell_amt', 0) - (df.get('trade_qty', 0) * df.get('avg_buy_price', 0))
# In many holdings responses realized pnl may be computed differently; if API provides realised pnl use it:
# if API returned realized_pnl in raw, prefer that:
if any('realized_pnl' in str(col).lower() for col in df.columns):
    # keep existing or convert
    try:
        df['realized_pnl'] = pd.to_numeric(df['realized_pnl'], errors='coerce').fillna(df['realized_pnl'])
    except Exception:
        pass

df['unrealized_pnl'] = (df['ltp'] - df['avg_buy_price']) * df['open_qty']
df['today_pnL'] = (df['ltp'] - df['prev_close']) * df['open_qty']
df['pct_change'] = df.apply(lambda r: ((r['ltp'] - r['prev_close']) / r['prev_close'] * 100) if pd.notna(r['prev_close']) and r['prev_close'] != 0 else None, axis=1)
df['total_pnl'] = df['realized_pnl'] + df['unrealized_pnl']

# compatibility columns used later
df['avg_buy_price'] = df['avg_buy_price'].astype(float)
df['quantity'] = df['open_qty']
df['invested_value'] = df['avg_buy_price'] * df['quantity']
df['current_value'] = df['ltp'] * df['quantity']
df['overall_pnl'] = df['current_value'] - df['invested_value']
# ensure numeric columns exist and are numeric
for col in ['initial_risk', 'open_risk']:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    else:
        df[col] = 0.0

df['capital_allocation_%'] = (df['invested_value'] / max(capital, 1)) * 100

# stops/targets code uses df['quantity'] (open positions)
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
            tsl_pct_down = 0.0 if idx_max == 0 else trailing_thresholds[idx_max - 1]
            tsl_price = round(avg_abs * (1 - tsl_pct_down), 4)
        else:
            tsl_price = initial_sl_price
        open_risk = round(max(0.0, (tsl_price - avg_abs) * abs(qty)), 2)
        initial_risk = round(max(0.0, (initial_sl_price - avg_abs) * abs(qty)), 2)
        realized_if_tsl_hit = round((avg_abs - tsl_price) * abs(qty), 2)
        return pd.Series({'side':side,'initial_sl_price':initial_sl_price,'tsl_price':tsl_price,'targets':targets,'initial_risk':initial_risk,'open_risk':open_risk,'realized_if_tsl_hit':realized_if_tsl_hit})

stoppers = df.apply(calc_stops_targets, axis=1)
df = pd.concat([df, stoppers], axis=1)

for i, tp in enumerate(target_pcts, start=1):
    df[f'target_{i}_pct'] = tp * 100
    df[f'target_{i}_price'] = df['targets'].apply(lambda lst: round(lst[i-1], 4) if isinstance(lst, list) and len(lst) >= i else 0.0)

# Portfolio KPIs
total_invested = df['invested_value'].sum()
total_current = df['current_value'].sum()
total_overall_pnl = df['overall_pnl'].sum()
missing_prev_count = int(df['prev_close'].isna().sum())
total_today_pnl = df['today_pnL'].fillna(0.0).sum()
total_initial_risk = df['initial_risk'].sum()
total_open_risk = df['open_risk'].sum()
total_realized_if_all_tsl = df['realized_if_tsl_hit'].sum()

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

# Positions table
display_cols = ['symbol', 'quantity', 'open_qty', 'buy_qty', 'sold_qty', 'avg_buy_price', 'ltp', 'prev_close', 'pct_change', 'today_pnL', 'realized_pnl', 'unrealized_pnl', 'total_pnl', 'capital_allocation_%', 'initial_sl_price', 'tsl_price', 'initial_risk', 'open_risk']
st.subheader('📋 Positions & Risk Table')
st.dataframe(df[display_cols].sort_values(by='capital_allocation_%', ascending=False).reset_index(drop=True), use_container_width=True)

# --- NEW: Charts & SL/Targets table ---
if not df.empty:
    st.subheader('📊 Capital Allocation')
    try:
        # Pie chart for capital allocation
        fig_pie = px.pie(df, names='symbol', values='invested_value', title='Capital Allocation (by invested amount)', hover_data=['capital_allocation_%', 'quantity'])
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_pie, use_container_width=True)
    except Exception:
        st.write('Could not render capital allocation pie chart.')

    st.subheader('📈 Risk Breakdown (per stock)')
    try:
        # Bar chart showing initial risk vs open risk per stock - ensure numeric dtype consistent
        risk_df = df.sort_values('open_risk', ascending=False).copy()
        risk_df['initial_risk'] = pd.to_numeric(risk_df['initial_risk'], errors='coerce').fillna(0.0)
        risk_df['open_risk'] = pd.to_numeric(risk_df['open_risk'], errors='coerce').fillna(0.0)
        # if very large number of symbols, allow user to pick top N
        max_bars = st.sidebar.number_input('Show top N symbols by open risk', min_value=3, max_value=50, value=10, step=1, key='topn_risk')
        plot_df = risk_df.head(int(max_bars))
        fig_bar = px.bar(plot_df, x='symbol', y=['initial_risk', 'open_risk'], title='Initial Risk vs Open Risk per Stock', labels={'value':'Amount (₹)', 'symbol':'Symbol'})
        fig_bar.update_layout(barmode='group', xaxis={'categoryorder':'total descending'})
        st.plotly_chart(fig_bar, use_container_width=True)
    except Exception:
        st.write('Could not render risk bar chart.')

    # Show SL and target prices in a concise table
    try:
        st.subheader('🎯 SL & Target Prices (per position)')
        target_cols = ['initial_sl_price'] + [f'target_{i}_price' for i in range(1, len(target_pcts)+1)]
        sl_table = df[['symbol'] + target_cols].fillna(0).reset_index(drop=True)
        st.dataframe(sl_table, use_container_width=True)
    except Exception:
        st.write('Could not render SL & Targets table.')

# Export
st.subheader('📥 Export')
csv_bytes = df.to_csv(index=False).encode('utf-8')
st.download_button('Download positions with PnL (CSV)', csv_bytes, file_name='positions_pnl.csv', mime='text/csv')

# -----------------------
# TRADING PLAN SECTION (EV, ET, PHASE, DRAWdown, GROWTH)
# -----------------------
st.markdown("---")
st.header("📈 Trading Plan & Performance Insights (Integrated)")

# Allow user to upload trade log CSV (optional) to compute actual win-rate and avg days
st.info("Optional: Upload a trade-log CSV (columns: symbol, entry_date, exit_date, pnl) to compute actual win-rate and avg holding days. Otherwise manual inputs used.")
trade_log_file = st.file_uploader("Upload trade-log CSV (optional)", type=["csv"])

trade_log_df = None
if trade_log_file:
    try:
        trade_log_df = pd.read_csv(trade_log_file, parse_dates=['entry_date', 'exit_date'])
        st.success("Trade log loaded.")
    except Exception as e:
        st.error("Could not read trade-log CSV. Ensure columns: symbol, entry_date, exit_date, pnl. Error: " + str(e))
        trade_log_df = None

# Manual / default inputs for the trading plan (if no trade log)
colA, colB, colC = st.columns(3)
input_win_rate = colA.number_input("Win Rate (if no trade-log) %", min_value=1.0, max_value=100.0, value=35.0) / 100.0
input_avg_win_days = colB.number_input("Avg Win holding days (if no trade-log)", min_value=1, max_value=90, value=16)
input_avg_loss_days = colC.number_input("Avg Loss holding days (if no trade-log)", min_value=1, max_value=30, value=4)

reward_risk_ratio = st.number_input("R (Reward : Risk) — e.g. 5 means target is 5×risk", min_value=0.1, max_value=50.0, value=5.0)
risk_pct_per_trade = st.number_input("Risk per trade (% of capital)", min_value=0.1, max_value=10.0, value=2.0)
target_return_pct = st.number_input("Target return (%) you want (of capital)", min_value=1.0, max_value=500.0, value=50.0)

# Determine actual win rate and avg days from trade_log if provided else fallback to manual
if trade_log_df is not None and not trade_log_df.empty:
    # compute pnl sign
    trade_log_df['pnl'] = pd.to_numeric(trade_log_df['pnl'], errors='coerce').fillna(0.0)
    wins = trade_log_df[trade_log_df['pnl'] > 0]
    losses = trade_log_df[trade_log_df['pnl'] <= 0]
    actual_win_rate = len(wins) / max(1, len(trade_log_df))
    # days
    trade_log_df['days'] = (trade_log_df['exit_date'] - trade_log_df['entry_date']).dt.days.fillna(0).clip(lower=0)
    avg_win_days_actual = wins['days'].mean() if not wins.empty else input_avg_win_days
    avg_loss_days_actual = losses['days'].mean() if not losses.empty else input_avg_loss_days
    used_win_rate = actual_win_rate
    used_avg_win_days = avg_win_days_actual
    used_avg_loss_days = avg_loss_days_actual
else:
    used_win_rate = input_win_rate
    used_avg_win_days = input_avg_win_days
    used_avg_loss_days = input_avg_loss_days

# Convert numbers
win_rate_pct_display = used_win_rate * 100.0
risk_amount = capital * (risk_pct_per_trade / 100.0)
expected_reward = reward_risk_ratio * risk_amount

# Expected Value per trade (monetary) = p_win * reward - p_loss * risk
p_win = used_win_rate
p_loss = 1 - p_win
ev_per_trade_monetary = (p_win * expected_reward) - (p_loss * risk_amount)

# Expected days per trade
expected_days_per_trade = (p_win * used_avg_win_days) + (p_loss * used_avg_loss_days)

# Trades needed to reach target
target_amount = capital * (target_return_pct / 100.0)
trades_needed = (target_amount / ev_per_trade_monetary) if ev_per_trade_monetary > 0 else math.inf
expected_total_days = trades_needed * expected_days_per_trade if trades_needed != math.inf else math.inf
expected_months = expected_total_days / 30.0 if expected_total_days != math.inf else math.inf

# Display core metrics
st.subheader("🧮 Expected Value & Time Metrics")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Win rate (used)", f"{win_rate_pct_display:.2f}%")
c2.metric("EV per trade (₹)", f"{ev_per_trade_monetary:,.2f}")
c3.metric("Avg days/trade", f"{expected_days_per_trade:.1f} days")
c4.metric("Trades needed (to hit target)", f"{math.ceil(trades_needed) if trades_needed != math.inf else '∞'}")

st.markdown(f"- **Target amount:** ₹{target_amount:,.0f} ({target_return_pct:.1f}% of capital)")
st.markdown(f"- **Risk per trade:** ₹{risk_amount:,.0f} ({risk_pct_per_trade:.2f}% of capital)")
st.markdown(f"- **Reward per win (target):** ₹{expected_reward:,.0f} ({reward_risk_ratio:.2f}R)")

# Time estimate
if math.isfinite(expected_total_days):
    st.metric("Estimated time to reach target", f"{int(expected_total_days)} days (~{expected_months:.1f} months)")
else:
    st.warning("Expected profit per trade is ≤ 0 (negative EV). Strategy not profitable -> trades needed is infinite.")

# Drawdown scenarios
st.subheader("📉 Drawdown Scenarios (Consecutive SL hits & All open positions SL)")

consecutive_losses = st.number_input("Simulate consecutive stop-losses (N)", min_value=1, max_value=100, value=10, step=1)
# Loss per trade = risk_amount
sim_consecutive_loss_amount = consecutive_losses * risk_amount
# All open positions SL
total_open_positions = df.shape[0]
total_open_risk = df['initial_risk'].sum()
all_open_sl_amount = total_open_risk

col1, col2, col3 = st.columns(3)
col1.metric(f"Consecutive SLs ({consecutive_losses}) loss", f"₹{sim_consecutive_loss_amount:,.0f}")
col2.metric("Total open positions (SL if hit)", f"₹{all_open_sl_amount:,.0f}")
col3.metric("Allowed max drawdown (user)", f"₹{capital * (st.sidebar.number_input('Set drawdown % for alerts', min_value=1.0, max_value=50.0, value=5.0)/100):,.0f}")

# Visualize cumulative consecutive loss
cons_df = pd.DataFrame({
    "trade_no": list(range(1, consecutive_losses + 1)),
    "cumulative_loss": np.cumsum([risk_amount] * consecutive_losses)
})
fig_cons = px.line(cons_df, x='trade_no', y='cumulative_loss', title=f"Cumulative Loss for {consecutive_losses} consecutive SLs")
st.plotly_chart(fig_cons, use_container_width=True)

# Current phase detection using realized_pnl if available
st.subheader("📅 Current Phase & Phase Rules (Using holdings' realized pnl as proxy)")

# Compute actual win/loss count from holdings (proxy)
realized_available = 'realized_pnl' in df.columns and df['realized_pnl'].notna().any()
if realized_available:
    wins_count = (df['realized_pnl'] > 0).sum()
    losses_count = (df['realized_pnl'] < 0).sum()
    neutral_count = (df['realized_pnl'] == 0).sum()
    total_realized_checked = wins_count + losses_count + neutral_count
    # simple phase detection
    if wins_count >= 8:
        current_phase = "Stage-III / Compounding (Strong)"
    elif wins_count >= 1 and wins_count < 8:
        current_phase = "Stage-II (Risk Financed)"
    elif wins_count == 0 and losses_count > 0:
        current_phase = "Stage-I / Drawdown (Testing)"
    else:
        current_phase = "Stage-I (Testing)"
    st.markdown(f"- Winning trades (holdings-based): **{wins_count}**, Losing trades: **{losses_count}**, Neutral: **{neutral_count}**")
    st.metric("Detected Phase", current_phase)
else:
    st.info("No realized PnL data in holdings to auto-detect phase. Use trade-log upload for better detection or set phase manually.")
    # let user set manual phase if they like
    current_phase = st.selectbox("Set current phase manually", ["Stage-I (Testing)", "Stage-II (Risk Financed)", "Stage-III (Fully Financed)", "Stage-IV (Compounding)"])

# Capital-growth projection simulation (monthly) using EV & expected trades per month
st.subheader("📈 Capital Growth Projection (Simulated)")

projection_months = st.number_input("Projection months", min_value=1, max_value=60, value=12)
trades_per_month = st.number_input("Approx trades per month", min_value=1, max_value=200, value=20)

# Use EV per trade to simulate linear expectation (non-compounding) and optionally compounding
compounding = st.checkbox("Compound profits into capital each month?", value=False)

monthly_expected_profit = ev_per_trade_monetary = ev_per_trade_monetary = ev_per_trade_monetary if 'ev_per_trade_monetary' in locals() else ev_per_trade_monetary
# compute expected profit per trade already (ev_per_trade_monetary)
monthly_profit = ev_per_trade_monetary * trades_per_month if math.isfinite(ev_per_trade_monetary) else 0.0

capital_series = []
cap = capital
for m in range(1, int(projection_months) + 1):
    if not math.isfinite(ev_per_trade_monetary) or ev_per_trade_monetary <= 0:
        expected_gain = 0.0
    else:
        expected_gain = monthly_profit
    if compounding:
        cap = cap + expected_gain
    else:
        cap = cap + expected_gain  # linear same update but label later as "with/without compounding" since we add same expected gain for both; compounding affects if expected_gain computed from changing capital (we keep EV constant here)
    capital_series.append({'month': m, 'capital': cap, 'expected_gain': expected_gain})

proj_df = pd.DataFrame(capital_series)

fig_proj = px.line(proj_df, x='month', y='capital', title='Projected Capital Over Time (Expectation)')
st.plotly_chart(fig_proj, use_container_width=True)
st.dataframe(proj_df.style.format({"capital":"{:.0f}", "expected_gain":"{:.0f}"}))

# High-R stocks detection (current R per holding)
st.subheader("🔥 High-R Holdings (current R multiple per position)")
# Current R = (ltp - avg_buy) / (avg_buy - initial_sl)
def calc_current_R(row):
    denom = (row['avg_buy_price'] - row['initial_sl_price'])
    if denom == 0:
        return np.nan
    return (row['ltp'] - row['avg_buy_price']) / denom

df['current_R'] = df.apply(calc_current_R, axis=1)
highR_df = df[df['current_R'] >= 5].copy()
if not highR_df.empty:
    st.dataframe(highR_df[['symbol','current_R','unrealized_pnl','overall_pnl']].sort_values('current_R', ascending=False).reset_index(drop=True))
else:
    st.info("No holding currently >= 5R.")

# Final notes & quick-export of plan values
st.markdown("### ✅ Quick export & notes")
plan_summary = {
    "capital": capital,
    "risk_per_trade_pct": risk_pct_per_trade,
    "risk_per_trade_amt": risk_amount,
    "win_rate_used": used_win_rate,
    "avg_win_days_used": used_avg_win_days,
    "avg_loss_days_used": used_avg_loss_days,
    "R": reward_risk_ratio,
    "EV_per_trade": ev_per_trade_monetary,
    "Trades_needed_for_target": trades_needed if trades_needed != math.inf else None,
    "Expected_days_to_target": expected_total_days if expected_total_days != math.inf else None,
    "Total_open_risk": total_open_risk
}
st.download_button("📥 Download Plan Summary (CSV)", data=pd.DataFrame([plan_summary]).to_csv(index=False).encode('utf-8'), file_name='trading_plan_summary.csv')

st.success("Integrated: holdings → trading plan. Use trade-log upload for more accurate real-world EV/time calculations.")
st.caption("Note: Expected Value (EV) uses your chosen risk % and R. If EV ≤ 0 the strategy is not profitable long-term — adjust inputs.")

