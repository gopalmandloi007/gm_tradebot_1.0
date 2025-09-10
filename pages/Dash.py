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
    """Recursively search for any of the keys in a nested dict/list and return first value found."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k is None:
                continue
            if str(k).lower() in {kk.lower() for kk in keys}:
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


# --- User-supplied parser (adapted) ---
def parse_definedge_csv_text(csv_text: str) -> pd.DataFrame:
    """Parse a Definedge history CSV (headerless) and return a DataFrame with DateTime and Close columns.
    This function is tolerant of slight format differences and converts Close to numeric.
    """
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

    # Try parse the DateTime column in common formats. Many feeds use ddmmyyyyHHMM
    df['DateTime_parsed'] = pd.to_datetime(df['DateTime'], format="%d%m%Y%H%M", errors='coerce')
    if df['DateTime_parsed'].isna().all():
        # try date-only
        df['DateTime_parsed'] = pd.to_datetime(df['DateTime'], format="%d%m%Y", errors='coerce')
    # final generic attempt
    df['DateTime_parsed'] = pd.to_datetime(df['DateTime_parsed'], errors='coerce')

    # Clean numeric Close
    df['Close'] = pd.to_numeric(df['Close'].str.replace(',', '').astype(str), errors='coerce')

    res = df[['DateTime_parsed', 'Close']].dropna(subset=['DateTime_parsed']).rename(columns={'DateTime_parsed': 'DateTime'})
    res = res.sort_values('DateTime').reset_index(drop=True)
    return res


# Optional: fetch historical CSV directly from Definedge endpoint (if you prefer to use API key instead of broker client)
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


# Robust previous-close extractor (expects DataFrame with DateTime and Close)
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

# Placeholder for client - replace with your actual API client stored in session_state
client = st.session_state.get('client')
if not client:
    st.error('⚠️ Not logged in. Please login first from the Login page.')
    st.stop()

# Sidebar inputs
st.sidebar.header('⚙️ Dashboard Settings & Risk')
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
auto_refresh = st.sidebar.checkbox('Auto-refresh LTP on page interaction', value=False, key='auto_refresh')
show_actions = st.sidebar.checkbox('Show Action Buttons (Square-off / Place SL)', value=False, key='show_actions')
use_definedge_api_key = st.sidebar.checkbox('Use Definedge API key for history fetch (if broker client lacks historical_csv)', value=False)
if use_definedge_api_key:
    st.sidebar.text_input('Definedge API key (put into session_state as definedge_api_key)', key='definedge_api_key_input')
st.sidebar.markdown('---')

# Fetch holdings
try:
    holdings_resp = client.get_holdings()
    if not holdings_resp or holdings_resp.get('status') != 'SUCCESS':
        st.warning('⚠️ No holdings found or API returned error')
        st.stop()

    holdings = holdings_resp.get('data', [])
    if not holdings:
        st.info('✅ No holdings found.')
        st.stop()

    # ------------------ FIXED: robust parsing and aggregation ------------------
    rows = []
    for item in holdings:
        # Defensive numeric parsing
        try:
            avg_buy_price = float(item.get('avg_buy_price') or 0)
        except Exception:
            avg_buy_price = 0.0
        try:
            dp_qty = float(item.get('dp_qty') or 0)
        except Exception:
            dp_qty = 0.0
        try:
            t1_qty = float(item.get('t1_qty') or 0)
        except Exception:
            t1_qty = 0.0
        try:
            holding_used = float(item.get('holding_used') or 0)
        except Exception:
            holding_used = 0.0

        # total quantity for this holding record (may be 0)
        total_qty = int(round(dp_qty + t1_qty + holding_used))

        # get the raw tradingsymbols field (APIs vary)
        tradings = item.get('tradingsymbol') if 'tradingsymbol' in item else item.get('tradings') or item.get('tradingsymbol')
        # Normalize possible None to empty
        if tradings is None:
            tradings = []

        symbols = []  # will hold dicts: {'symbol': str, 'token': token_str}
        # 1) single string (common case)
        if isinstance(tradings, str):
            symbols = [{'symbol': tradings, 'token': item.get('token')}]
        # 2) a dict (single structured entry)
        elif isinstance(tradings, dict):
            sym_str = tradings.get('tradingsymbol') or tradings.get('symbol') or item.get('tradingsymbol')
            symbols = [{'symbol': sym_str, 'token': tradings.get('token') or item.get('token')}]
        # 3) list/tuple (could contain strings or dicts)
        elif isinstance(tradings, (list, tuple)):
            for sym in tradings:
                if isinstance(sym, dict):
                    sym_str = sym.get('tradingsymbol') or sym.get('symbol') or item.get('tradingsymbol')
                    token_sym = sym.get('token') or item.get('token')
                else:
                    # If element is a plain string, use it directly (fixes duplication bug)
                    sym_str = str(sym) if sym is not None else item.get('tradingsymbol')
                    token_sym = item.get('token')
                if sym_str:
                    symbols.append({'symbol': sym_str, 'token': token_sym})
        else:
            # fallback: use item-level field if present
            if item.get('tradingsymbol'):
                symbols = [{'symbol': item.get('tradingsymbol'), 'token': item.get('token')}]

        # If we couldn't detect symbol(s) skip this record
        if not symbols:
            continue

        # Add one row per symbol entry. quantity for this record is total_qty.
        for s in symbols:
            rows.append({
                'symbol': s['symbol'],
                'token': s.get('token') or item.get('token'),
                'avg_buy_price': avg_buy_price,
                'quantity': total_qty,
                'product_type': item.get('product_type', '')
            })

    if not rows:
        st.warning('⚠️ No NSE holdings found.')
        st.stop()

    _raw_df = pd.DataFrame(rows).dropna(subset=['symbol']).reset_index(drop=True)

    # Aggregate by symbol+token to avoid duplicate rows (sum quantity and weighted avg of avg_buy_price)
    def _agg_group(g):
        qty_sum = int(g['quantity'].sum())
        if qty_sum > 0:
            weighted_avg = float((g['avg_buy_price'] * g['quantity']).sum() / g['quantity'].sum())
        else:
            weighted_avg = float(g['avg_buy_price'].mean() if len(g) > 0 else 0.0)
        return pd.Series({
            'quantity': qty_sum,
            'avg_buy_price': weighted_avg,
            'product_type': g['product_type'].iloc[0] if 'product_type' in g.columns else ''
        })

    grouped = _raw_df.groupby(['symbol', 'token'], dropna=False).apply(_agg_group).reset_index()

    df = grouped[['symbol', 'token', 'avg_buy_price', 'quantity', 'product_type']].copy()

    # Ensure numeric types
    df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').fillna(0).astype(int)
    df['avg_buy_price'] = pd.to_numeric(df['avg_buy_price'], errors='coerce').fillna(0.0)

    # ------------------ END FIXED PARSING ------------------

    # Fetch LTP + previous close
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
        symbol = row.get('symbol')
        prev_close_from_quote = None
        ltp_val = None

        # Get live quote (robustly)
        try:
            quote_resp = client.get_quotes(exchange='NSE', token=token)
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

        # 1) If quote provided prev_close, use it
        if prev_close_from_quote is not None:
            prev_close = float(prev_close_from_quote)
            prev_source = 'quote'
        else:
            # 2) Try to fetch historical data to derive prev close
            try:
                hist_df = pd.DataFrame()
                # prefer broker client's historical CSV if available
                if hasattr(client, 'historical_csv'):
                    try:
                        from_date = (today_dt - timedelta(days=30)).strftime('%d%m%Y%H%M')
                        to_date = today_dt.strftime('%d%m%Y%H%M')
                        hist_csv = client.historical_csv(segment='NSE', token=token, timeframe='day', frm=from_date, to=to_date)
                        hist_df = parse_definedge_csv_text(hist_csv)
                    except Exception:
                        hist_df = pd.DataFrame()
                # fallback: if user wants, use Definedge API key to fetch
                if hist_df.empty and use_definedge_api_key:
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

        # NOTE: We intentionally DO NOT fall back prev_close to LTP here. If prev_close is missing it will be NaN.
        # This preserves the semantic difference between LTP and previous-close. If you prefer to force prev_close=ltp
        # set `prev_close = ltp_val` here.

        ltp_list.append(safe_float(ltp_val) or 0.0)
        prev_close_list.append(prev_close)
        prev_source_list.append(prev_source or 'unknown')

except Exception as e:
    st.error(f'⚠️ Error fetching holdings or prices: {e}')
    st.text(traceback.format_exc())
    st.stop()

# Optional: show last fetched historical data
try:
    if 'last_hist_df' in locals() and last_hist_df is not None and last_hist_df.shape[0] > 0:
        st.write('Historical data sample (last fetched symbol):')
        st.dataframe(last_hist_df.head())
except Exception:
    pass

# Assign the fetched 'ltp' and 'prev_close' to df (and convert to numeric)
df['ltp'] = pd.to_numeric(pd.Series(ltp_list), errors='coerce').fillna(0.0)
# prev_close left as NaN when not available so we can highlight missingness
_df_prev = pd.to_numeric(pd.Series(prev_close_list), errors='coerce')
df['prev_close'] = _df_prev

df['prev_close_source'] = prev_source_list

# Convert other columns to numeric safely
for col in ['avg_buy_price', 'quantity']:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

# Calculate invested_value
df['invested_value'] = df['avg_buy_price'] * df['quantity']

# Calculate current value & today's pnl
df['current_value'] = df['ltp'] * df['quantity']
# Today PnL: (LTP - PrevClose) * Qty. Rows with missing prev_close will be NaN
df['today_pnL'] = (df['ltp'] - df['prev_close']) * df['quantity']

# Calculate overall P&L
df['overall_pnl'] = df['current_value'] - df['invested_value']
# Capital allocation %
df['capital_allocation_%'] = (df['invested_value'] / capital) * 100

# ------------------ Calculate stops and targets ------------------

def calc_stops_targets(row):
    avg = float(row.get('avg_buy_price') or 0.0)
    qty = int(row.get('quantity') or 0)
    ltp = float(row.get('ltp') or 0.0)

    if qty == 0 or avg == 0:
        return pd.Series({
            'side': 'FLAT',
            'initial_sl_price': 0.0,
            'tsl_price': 0.0,
            'targets': [0.0] * len(target_pcts),
            'initial_risk': 0.0,
            'open_risk': 0.0,
            'realized_if_tsl_hit': 0.0
        })

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

        return pd.Series({
            'side': side,
            'initial_sl_price': initial_sl_price,
            'tsl_price': tsl_price,
            'targets': targets,
            'initial_risk': initial_risk,
            'open_risk': open_risk,
            'realized_if_tsl_hit': realized_if_tsl_hit
        })
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

        return pd.Series({
            'side': side,
            'initial_sl_price': initial_sl_price,
            'tsl_price': tsl_price,
            'targets': targets,
            'initial_risk': initial_risk,
            'open_risk': open_risk,
            'realized_if_tsl_hit': realized_if_tsl_hit
        })

# Apply stops/targets to DataFrame
stoppers = df.apply(calc_stops_targets, axis=1)
df = pd.concat([df, stoppers], axis=1)

# Explode targets into columns
for i, tp in enumerate(target_pcts, start=1):
    df[f'target_{i}_pct'] = tp * 100
    df[f'target_{i}_price'] = df['targets'].apply(lambda lst: round(lst[i-1], 4) if isinstance(lst, list) and len(lst) >= i else 0.0)

# Portfolio KPIs
total_invested = df['invested_value'].sum()
total_current = df['current_value'].sum()
total_overall_pnl = df['overall_pnl'].sum()
# Sum today's PnL only treating missing prev_close as 0 for portfolio-level KPI
missing_prev_count = int(df['prev_close'].isna().sum())
total_today_pnl = df['today_pnL'].fillna(0.0).sum()
total_initial_risk = df['initial_risk'].sum()
total_open_risk = df['open_risk'].sum()
total_realized_if_all_tsl = df['realized_if_tsl_hit'].sum()

# ------------------ Display KPIs ------------------
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

# Messaging
total_positions = len(df)
breakeven_count = int((df['open_risk'] == 0).sum())

# Check if 'ltp' exists before calculating profitable_by_ltp
if 'ltp' in df.columns:
    profitable_by_ltp = int((df['ltp'] > df['avg_buy_price']).sum())
else:
    profitable_by_ltp = 0

if breakeven_count == total_positions:
    st.success(f'✅ All {total_positions} positions have TSL >= AvgBuy (no open risk). {profitable_by_ltp} currently profitable.')
else:
    st.info(f'ℹ️ {breakeven_count}/{total_positions} positions have no open risk. {profitable_by_ltp} profitable by LTP.')
    risky = df[df['open_risk'] > 0].sort_values(by='open_risk', ascending=False).head(10)
    if not risky.empty:
        st.table(risky[[ 'symbol', 'quantity', 'avg_buy_price', 'ltp', 'tsl_price', 'open_risk']])

# Scenario analysis
st.subheader('🔮 Scenario: If ALL TSL get hit')
st.write('Assuming each position is closed at its TSL price.')
st.metric('Total if TSL hit', f'₹{total_realized_if_all_tsl:,.2f}')
delta = total_realized_if_all_tsl - total_overall_pnl
st.metric('Delta vs Unrealized', f'₹{delta:,.2f}')
try:
    st.write(f'That is {total_realized_if_all_tsl/capital*100:.2f}% of total capital.')
except Exception:
    pass

# Winners and Losers
df['realized_if_tsl_sign'] = df['realized_if_tsl_hit'].apply(lambda x: 'profit' if x > 0 else ('loss' if x < 0 else 'breakeven'))
winners = df[df['realized_if_tsl_hit'] > 0]
losers = df[df['realized_if_tsl_hit'] < 0]
breakevens = df[df['realized_if_tsl_hit'] == 0]

st.write(f'Winners: {len(winners)}, Losers: {len(losers)}, Breakeven: {len(breakevens)}')
if not winners.empty:
    st.table(winners[['symbol', 'quantity', 'avg_buy_price', 'tsl_price', 'realized_if_tsl_hit']].sort_values(by='realized_if_tsl_hit', ascending=False).head(10))
if not losers.empty:
    st.table(losers[['symbol', 'quantity', 'avg_buy_price', 'tsl_price', 'realized_if_tsl_hit']].sort_values(by='realized_if_tsl_hit').head(10))

# Positions & risk table
display_cols = ['symbol', 'quantity', 'side', 'avg_buy_price', 'ltp', 'prev_close', 'prev_close_source', 'invested_value', 'current_value', 'overall_pnl', 'today_pnL',
                'capital_allocation_%', 'initial_sl_price', 'tsl_price', 'initial_risk', 'open_risk', 'realized_if_tsl_hit']
for i in range(1, len(target_pcts) + 1):
    display_cols += [f'target_{i}_pct', f'target_{i}_price']

st.subheader('📋 Positions & Risk Table')
st.dataframe(df[display_cols].sort_values(by='capital_allocation_%', ascending=False).reset_index(drop=True), use_container_width=True)

# Visuals
st.subheader('📊 Capital Allocation & Risk Visuals')
pie_df = df[['symbol', 'capital_allocation_%']].copy()
try:
    cash_pct = max(0.0, 100 - pie_df['capital_allocation_%'].sum())
except Exception:
    cash_pct = 0.0
pie_df = pd.concat([pie_df, pd.DataFrame([{'symbol': 'Cash', 'capital_allocation_%': cash_pct}])], ignore_index=True)
fig = go.Figure(data=[go.Pie(labels=pie_df['symbol'], values=pie_df['capital_allocation_%'], hole=0.35)])
fig.update_traces(textinfo='label+percent')
st.plotly_chart(fig, use_container_width=True)

st.subheader('⚠️ Risk Exposure by Position (Initial Risk % of Capital)')
risk_df = df[['symbol', 'initial_risk']].copy()
risk_df['initial_risk_pct_of_capital'] = (risk_df['initial_risk'] / capital) * 100
fig2 = go.Figure(data=[go.Bar(x=risk_df['symbol'], y=risk_df['initial_risk_pct_of_capital'])])
fig2.update_layout(yaxis_title='% of Capital', xaxis_title='Symbol')
st.plotly_chart(fig2, use_container_width=True)

# Per-symbol expanders & actions
st.subheader('🔍 Per-symbol details & actions')
for idx, row in df.sort_values(by='capital_allocation_%', ascending=False).iterrows():
    key_base = f"{row['symbol']}_{idx}"
    with st.expander(f"{row['symbol']} — Qty: {row['quantity']} | Invested: ₹{row['invested_value']:.0f}"):
        st.write(row[display_cols].to_frame().T)
        st.write('**Targets (price):**', row['targets'])
        st.write('**Potential profit/loss if TSL hit (₹):**', row['realized_if_tsl_hit'])

        if show_actions and row['side'] in ['LONG', 'SHORT']:
            cols = st.columns(3)
            if cols[0].button(f"Square-off {row['symbol']}", key=f"sq_{key_base}"):
                try:
                    payload = {
                        'exchange': 'NSE',
                        'tradingsymbol': row['symbol'],
                        'quantity': int(abs(row['quantity'])),
                        'product_type': 'INTRADAY',
                        'order_type': 'SELL' if row['side'] == 'LONG' else 'BUY'
                    }
                    resp = client.square_off_position(payload)
                    st.write('🔎 Square-off API Response:', resp)
                    if resp.get('status') == 'SUCCESS':
                        st.success('Square-off placed successfully')
                    else:
                        st.error('Square-off failed: ' + str(resp))
                except Exception as e:
                    st.error(f'Square-off failed: {e}')
                    st.text(traceback.format_exc())

            if cols[1].button(f"Place SL Order @ TSL ({row['tsl_price']})", key=f"sl_{key_base}"):
                try:
                    payload = {
                        'exchange': 'NSE',
                        'tradingsymbol': row['symbol'],
                        'quantity': int(abs(row['quantity'])),
                        'price_type': 'SL-LIMIT',
                        'price': float(row['tsl_price']),
                        'product_type': 'INTRADAY',
                        'order_type': 'SELL' if row['side'] == 'LONG' else 'BUY'
                    }
                    resp = client.place_order(payload)
                    st.write('🔎 Place SL API Response:', resp)
                    if resp.get('status') == 'SUCCESS':
                        st.success('SL order placed successfully')
                    else:
                        st.error('SL placement failed: ' + str(resp))
                except Exception as e:
                    st.error(f'SL placement failed: {e}')
                    st.text(traceback.format_exc())

            if cols[2].button(f"Modify SL to initial ({row['initial_sl_price']})", key=f"modsl_{key_base}"):
                st.info('Modify SL functionality depends on existing order_id. Use Orders page to modify specific orders.')

# Export
st.subheader('📥 Export')
csv_bytes = df.to_csv(index=False).encode('utf-8')
st.download_button('Download positions with risk data (CSV)', csv_bytes, file_name='positions_risk.csv', mime='text/csv')
