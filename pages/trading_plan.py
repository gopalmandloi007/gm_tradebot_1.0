# final_holdings_dashboard.py
# Complete Streamlit page: holdings + trading plan (EV, ET, R-multiple, >5R, max drawdown) + charts + export
import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta, date
import plotly.express as px
import traceback
import requests

# ------------------ Page config ------------------
st.set_page_config(layout="wide", page_title="Trading Dashboard — Risk Managed", page_icon="📊")
st.title("📊 Trading Dashboard — Risk Managed (Holdings + Trading Plan)")

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

# reuse your parsing helpers (kept robust)
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

# ------------------ Input controls ------------------
st.sidebar.header("Trading Plan Inputs")
capital = st.sidebar.number_input("Total Capital (₹)", value=DEFAULT_TOTAL_CAPITAL, step=10000, key='capital_input')
initial_sl_pct = st.sidebar.number_input("Initial Stop Loss (%)", value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1, key='initial_sl_input')/100
# R:R or reward per win will be derived from position / stop loss; but allow override of Reward per win per trade
rr_input = st.sidebar.number_input("Reward : Risk (R:R) (e.g. 5 means 1:5)", value=5, min_value=1, step=1)
win_rate_perc = st.sidebar.slider("Win Rate (%)", value=35, min_value=1, max_value=99)
win_rate = win_rate_perc / 100.0
target_percent = st.sidebar.number_input("Target Profit (% of capital)", value=50, min_value=1, max_value=500, step=1)
target_profit = capital * (target_percent/100.0)

st.sidebar.markdown("---")
st.sidebar.header("Time assumptions")
avg_days_win = st.sidebar.number_input("Avg days per WIN trade", value=12, min_value=1)
avg_days_loss = st.sidebar.number_input("Avg days per LOSS trade", value=3, min_value=1)
avg_trades_per_month = st.sidebar.number_input("Avg trades per month (overlap allowed)", value=20, min_value=1)

st.sidebar.markdown("---")
st.sidebar.header("Display / debug")
debug = st.sidebar.checkbox("Show debug", value=False)
use_definedge_api_key = st.sidebar.checkbox('Use Definedge API key for history fetch (if needed)', value=False)
if use_definedge_api_key:
    st.sidebar.text_input('Definedge API key (put into session_state as definedge_api_key)', key='definedge_api_key_input')

targets_input = st.sidebar.text_input('Targets % (comma separated)', ','.join(map(str, DEFAULT_TARGETS)), key='targets_input')
try:
    target_pcts = sorted([max(0.0, float(t.strip())/100.0) for t in targets_input.split(',') if t.strip()])
    if not target_pcts:
        target_pcts = [t/100.0 for t in DEFAULT_TARGETS]
except Exception:
    target_pcts = [t/100.0 for t in DEFAULT_TARGETS]
trailing_thresholds = target_pcts

# ------------------ Fetch holdings from client ------------------
client = st.session_state.get('client')
if not client:
    st.error("⚠️ Not logged in. Please login first on the Login page.")
    st.stop()

try:
    holdings_resp = client.get_holdings()
    if debug:
        st.write("Raw holdings response (preview):", holdings_resp if isinstance(holdings_resp, dict) else str(holdings_resp)[:800])
    if not holdings_resp or holdings_resp.get('status') != 'SUCCESS':
        st.warning("No holdings found or API returned error.")
        st.stop()
    raw_holdings = holdings_resp.get('data', [])
    if not raw_holdings:
        st.info("No holdings present.")
        st.stop()

    # Parse holdings into rows
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
        st.warning("No NSE holdings found after parsing.")
        st.stop()

    df = pd.DataFrame(rows)

    # Aggregate by symbol (sum quantities, weighted avg)
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

    # Compute open quantity and compatibility columns
    df['open_qty'] = (df['buy_qty'] - df['trade_qty']).clip(lower=0).astype(int)
    df['sold_qty'] = df['trade_qty'].astype(int)
    df['quantity'] = df['open_qty']

    # Fetch LTP and prev_close robustly
    st.info("Fetching quotes and (robust) prev close...")
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
        ltp_val = None
        prev_close_from_quote = None
        try:
            quote_resp = client.get_quotes(exchange='NSE', token=token)
            if debug:
                st.write(f"Quote for {row['symbol']}: ", quote_resp if isinstance(quote_resp, dict) else str(quote_resp)[:600])
            if isinstance(quote_resp, dict) and quote_resp:
                found_ltp = find_in_nested(quote_resp, LTP_KEYS)
                if found_ltp is not None:
                    ltp_val = safe_float(found_ltp)
                found_prev = find_in_nested(quote_resp, POSSIBLE_PREV_KEYS)
                if found_prev is not None:
                    prev_close_from_quote = safe_float(found_prev)
        except Exception:
            ltp_val = None
            prev_close_from_quote = None

        prev_close = None
        prev_source = None

        if prev_close_from_quote is not None:
            prev_close = float(prev_close_from_quote)
            prev_source = 'quote'
        else:
            # try historical CSV from client
            hist_df = pd.DataFrame()
            try:
                if hasattr(client, 'historical_csv'):
                    try:
                        from_date = (today_dt - timedelta(days=60)).strftime('%d%m%Y%H%M')
                        to_date = today_dt.strftime('%d%m%Y%H%M')
                        hist_csv = client.historical_csv(segment='NSE', token=token, timeframe='day', frm=from_date, to=to_date)
                        hist_df = parse_definedge_csv_text(hist_csv)
                    except Exception:
                        hist_df = pd.DataFrame()
                # fallback to definedge api if user provided key
                if (hist_df is None or hist_df.empty) and use_definedge_api_key:
                    api_key = st.session_state.get('definedge_api_key') or st.session_state.get('definedge_api_key_input')
                    if api_key:
                        hist_df = fetch_hist_for_date_range(api_key, 'NSE', token, today_dt - timedelta(days=60), today_dt)
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
    st.error(f"⚠️ Error fetching holdings/prices: {e}")
    st.text(traceback.format_exc())
    st.stop()

# show sample hist if available (optional)
try:
    if 'last_hist_df' in locals() and last_hist_df is not None and last_hist_df.shape[0] > 0 and debug:
        st.write('Historical sample for last token fetched:')
        st.dataframe(last_hist_df.head())
except Exception:
    pass

# ------------------ numeric assignments & pnl calcs ------------------
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

# compatibility columns used later
df['avg_buy_price'] = df['avg_buy_price'].astype(float)
df['quantity'] = df['open_qty'].astype(int)
df['invested_value'] = df['avg_buy_price'] * df['quantity']
df['current_value'] = df['ltp'] * df['quantity']
df['overall_pnl'] = df['current_value'] - df['invested_value']
# avoid division by zero
df['capital_allocation_%'] = df['invested_value'] / capital * 100

# stops/targets (reused robust function)
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

# derive explicit target columns
for i, tp in enumerate(target_pcts, start=1):
    df[f'target_{i}_pct'] = tp * 100
    df[f'target_{i}_price'] = df['targets'].apply(lambda lst: round(lst[i-1], 4) if isinstance(lst, list) and len(lst) >= i else 0.0)

# ------------------ Portfolio KPIs & Trading Plan math ------------------
# clean numeric columns
for col in ['initial_risk', 'open_risk', 'unrealized_pnl', 'overall_pnl', 'invested_value', 'current_value']:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

total_invested = df['invested_value'].sum()
total_current = df['current_value'].sum()
total_overall_pnl = df['overall_pnl'].sum()
missing_prev_count = int(df['prev_close'].isna().sum())
total_today_pnl = df['today_pnL'].fillna(0.0).sum()
total_initial_risk = df['initial_risk'].sum()
total_open_risk = df['open_risk'].sum()
total_realized_if_all_tsl = df['realized_if_tsl_hit'].sum()

# Expected Value (EV) per trade using R:R with initial stop of initial_sl_pct
# Determine a base position size: use average invested per position or allow user override
avg_position_size = df['invested_value'].mean() if len(df) > 0 else capital * 0.1
# We'll set risk_per_trade to be avg_position_size * initial_sl_pct (approx)
risk_per_trade = avg_position_size * initial_sl_pct
reward_per_trade = risk_per_trade * rr_input
EV_per_trade = (win_rate * reward_per_trade) - ((1 - win_rate) * risk_per_trade)

# Expected Time (ET) per trade
ET_days = (win_rate * avg_days_win) + ((1 - win_rate) * avg_days_loss)

# Trades needed to reach target
trades_needed = int(round(target_profit / EV_per_trade)) if EV_per_trade > 0 else None

# Serial days if trades are done one after another
if trades_needed:
    total_days_serial = trades_needed * ET_days
    months_by_freq = trades_needed / max(1, avg_trades_per_month)
else:
    total_days_serial = None
    months_by_freq = None

# R-multiple for each position:
# Using formula for long positions: R = (LTP - AvgBuy) / (AvgBuy - InitialSL)
def compute_r_multiple(row):
    try:
        avg = float(row['avg_buy_price'])
        ltp = float(row['ltp'])
        initial_sl_price = float(row['initial_sl_price'])
        denom = (avg - initial_sl_price)
        if denom == 0:
            return 0.0
        # if long position
        r = (ltp - avg) / denom
        return round(r, 2)
    except Exception:
        return 0.0

df['current_R'] = df.apply(compute_r_multiple, axis=1)
df['R_status'] = df['current_R'].apply(lambda x: "🏆 +5R+" if x >= 5 else ("✅ Positive" if x > 0 else "🔻 Negative"))

# Portfolio-level R metrics
# Weighted average R by invested value
weighted_R = (df['current_R'] * df['invested_value']).sum() / total_invested if total_invested > 0 else 0.0
sum_R = df['current_R'].sum()

# Max drawdown if all SL hit = sum of initial_risk (negative number or positive amount lost)
max_drawdown_if_all_sl = -total_initial_risk  # negative to represent loss (we'll display positive)

# ------------------ UI: Summary KPIs ------------------
st.subheader('💰 Overall Summary')
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric('Total Invested', f'₹{total_invested:,.2f}')
k2.metric('Total Current', f'₹{total_current:,.2f}')
k3.metric('Unrealized PnL', f'₹{total_overall_pnl:,.2f}')
k4.metric('Today PnL', f'₹{total_today_pnl:,.2f}')
k5.metric('Open Risk (TSL)', f'₹{total_open_risk:,.2f}')

st.markdown(f"- **Avg position size (est)**: ₹{avg_position_size:,.2f}  •  **Risk per trade (est)**: ₹{risk_per_trade:,.2f}  •  **Reward/trade (est)**: ₹{reward_per_trade:,.2f}")
st.markdown(f"- **EV per trade (est)**: ₹{EV_per_trade:,.2f}  •  **ET per trade (days)**: {ET_days:.2f} days")

if trades_needed:
    st.markdown(f"- **Trades needed for target ₹{target_profit:,.0f}**: {trades_needed} trades  •  Serial time ≈ {int(total_days_serial)} days (~{total_days_serial/30:.1f} months).")
    st.markdown(f"- **Approx months at {int(avg_trades_per_month)} trades/month**: {months_by_freq:.1f} months")
else:
    st.markdown("⚠️ EV per trade is non-positive — adjust R:R or Win Rate to a positive-expectancy system.")

# ------------------ UI: Positions Table ------------------
display_cols = ['symbol', 'quantity', 'avg_buy_price', 'ltp', 'prev_close', 'pct_change', 'today_pnL', 'realized_pnl', 'unrealized_pnl', 'overall_pnl', 'capital_allocation_%', 'initial_sl_price', 'initial_risk', 'open_risk', 'tsl_price', 'current_R', 'R_status']
st.subheader('📋 Positions & Risk Table')
st.dataframe(df[display_cols].sort_values(by='capital_allocation_%', ascending=False).reset_index(drop=True), use_container_width=True)

# ------------------ Charts & SL/Targets ------------------
if not df.empty:
    st.subheader('📊 Capital Allocation')
    try:
        fig_pie = px.pie(df, names='symbol', values='invested_value', title='Capital Allocation (by invested amount)', hover_data=['capital_allocation_%', 'quantity'])
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_pie, use_container_width=True)
    except Exception:
        st.write('Could not render capital allocation pie chart.')

    st.subheader('📈 Risk Breakdown (per stock)')
    try:
        risk_df = df.sort_values('open_risk', ascending=False).copy()
        # data cleaning for plotting
        for col in ['initial_risk', 'open_risk', 'unrealized_pnl']:
            if col in risk_df.columns:
                risk_df[col] = pd.to_numeric(risk_df[col], errors='coerce').fillna(0.0)
        max_bars = st.sidebar.number_input('Show top N symbols by open risk', min_value=3, max_value=50, value=10, step=1, key='topn_risk')
        plot_df = risk_df.head(int(max_bars))
        fig_bar = px.bar(plot_df, x='symbol', y=['initial_risk', 'open_risk'], title='Initial Risk vs Open Risk per Stock', labels={'value':'Amount (₹)', 'symbol':'Symbol'})
        fig_bar.update_layout(barmode='group', xaxis={'categoryorder':'total descending'})
        st.plotly_chart(fig_bar, use_container_width=True)
    except Exception:
        st.write('Could not render risk bar chart.')

    # SL & Targets table
    try:
        st.subheader('🎯 SL & Target Prices (per position)')
        target_cols = ['initial_sl_price'] + [f'target_{i}_price' for i in range(1, len(target_pcts)+1)]
        sl_table = df[['symbol'] + target_cols].fillna(0).reset_index(drop=True)
        st.dataframe(sl_table, use_container_width=True)
    except Exception:
        st.write('Could not render SL & Targets table.')

# ------------------ R-multiple summary ------------------
st.subheader('📈 R-multiple Summary')
c1, c2, c3 = st.columns(3)
c1.metric("Weighted Avg R", f"{weighted_R:.2f}")
c2.metric("Sum of R (all positions)", f"{sum_R:.2f}")
c3.metric("Max Drawdown if all SL hit", f"₹{total_initial_risk:,.2f}")

st.markdown("**Top R performers (≥ 5R):**")
top_r = df[df['current_R'] >= 5].sort_values('current_R', ascending=False)
if not top_r.empty:
    st.dataframe(top_r[['symbol','quantity','avg_buy_price','ltp','current_R','overall_pnl']].reset_index(drop=True), use_container_width=True)
else:
    st.info("No stock has reached +5R yet. Keep patience and discipline. 💪")

# ------------------ Export & download ------------------
st.subheader('📥 Export Data')
csv_bytes = df.to_csv(index=False).encode('utf-8')
st.download_button('Download positions with PnL (CSV)', csv_bytes, file_name='positions_pnl_with_r.csv', mime='text/csv')

# Optionally export the trading plan summary as markdown for PPT
def build_markdown_plan():
    md = []
    md.append("# Trading Plan & Portfolio Snapshot - Generated\n")
    md.append(f"- Date: {datetime.now().isoformat()}\n")
    md.append("## Summary KPIs\n")
    md.append(f"- Total Invested: ₹{total_invested:,.2f}\n")
    md.append(f"- Total Current: ₹{total_current:,.2f}\n")
    md.append(f"- Unrealized PnL: ₹{total_overall_pnl:,.2f}\n")
    md.append(f"- Max Drawdown if SLs hit: ₹{total_initial_risk:,.2f}\n")
    md.append(f"- EV per trade (est): ₹{EV_per_trade:,.2f}\n")
    md.append(f"- ET per trade (days): {ET_days:.2f}\n")
    if trades_needed:
        md.append(f"- Trades needed for target ₹{target_profit:,.0f}: {trades_needed} (~{int(total_days_serial)} days)\n")
    md.append("\n## Top Positions by R\n")
    if not top_r.empty:
        md.append(top_r[['symbol','current_R','overall_pnl']].to_markdown(index=False))
    else:
        md.append("No 5R+ positions currently.\n")
    return "\n".join(md)

md = build_markdown_plan()
b = md.encode('utf-8')
st.download_button("Download trading plan summary (Markdown)", data=b, file_name="trading_plan_summary.md", mime="text/markdown")

st.success("Dashboard updated ✅ — shows live R-multiples, EV, ET, trades-to-target and max drawdown.")
