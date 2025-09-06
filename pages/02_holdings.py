"""
Enhanced Holdings page for Streamlit — robust, performant, and feature-rich.
Drop-in replacement for your original holdings.py. Key features:
- Robust flattening of varying holdings response formats (strings, dicts, lists)
- Flexible quantity detection and aggregation (dp_qty, t1_qty, holding_used, etc.)
- Optional live LTP/previous-close fetch (toggleable)
- Calculated metrics: invested, market value, unrealized PnL, today PnL
- Portfolio KPIs and visuals (allocation pie + PnL bar)
- Incremental, debuggable, and exportable results

Requirements: your `client` object must be available in `st.session_state['client']` and expose
`get_holdings()` and optionally `get_quotes(exchange, token)`.
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime

st.set_page_config(layout="wide")
st.title("📦 Holdings — Definedge (Enhanced)")

# ------------------ Sidebar / options ------------------
exchange_filter = st.sidebar.text_input("Exchange filter", value="NSE").strip().upper()
fetch_ltp = st.sidebar.checkbox("Fetch live LTP & prev_close (may be slow)", value=False)
capital = st.sidebar.number_input("Portfolio capital (for allocation%)", value=1000000, step=50000)
show_debug = st.sidebar.checkbox("Show debug / raw response", value=False)
concurrency = st.sidebar.number_input("Parallel quote threads (0 = disabled)", min_value=0, max_value=16, value=0)
st.sidebar.markdown("---")

client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in — please login on Login page and set `st.session_state['client']`.")
    st.stop()

# ------------------ Helpers ------------------

def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or (isinstance(x, str) and x.strip() == ""):
            return default
        return float(str(x).replace(",", ""))
    except Exception:
        return default


def safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(round(safe_float(x, default)))
    except Exception:
        return default


def find_in_nested(obj: Any, keys: List[str]) -> Optional[Any]:
    """Recursively find first occurrence of any candidate key names in nested dicts/lists."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        lower_keys = {k.lower(): k for k in obj.keys() if isinstance(k, str)}
        for cand in keys:
            if cand.lower() in lower_keys:
                return obj[lower_keys[cand.lower()]]
        for v in obj.values():
            res = find_in_nested(v, keys)
            if res is not None:
                return res
    elif isinstance(obj, (list, tuple)):
        for it in obj:
            res = find_in_nested(it, keys)
            if res is not None:
                return res
    return None


def _flatten_holdings(raw_data: List[Dict], exchange: Optional[str] = None) -> List[Dict]:
    """Flatten holdings records. Handles variations in 'tradingsymbol' field shapes.
    Returns list of rows with canonical keys.
    """
    rows: List[Dict] = []
    for h in raw_data:
        # copy base metadata (non-tradingsymbol keys)
        base = {k: v for k, v in h.items() if k != 'tradingsymbol' and k != 'tradingsymbols'}

        # possible containers for tradingsymbol(s)
        ts_container = h.get('tradingsymbol') or h.get('tradingsymbols') or []

        # if tradingsymbol is a single string, wrap
        if isinstance(ts_container, str):
            ts_list = [ {'tradingsymbol': ts_container} ]
        elif isinstance(ts_container, dict):
            ts_list = [ts_container]
        elif isinstance(ts_container, (list, tuple)):
            ts_list = list(ts_container)
        else:
            ts_list = []

        # If there were no explicit tradingsymbol items, create one from top-level token/symbol
        if not ts_list:
            sym = h.get('tradingsymbol') or h.get('symbol') or base.get('tradingsymbol') or base.get('symbol')
            tok = h.get('token') or base.get('token')
            if sym or tok:
                ts_list = [{'tradingsymbol': sym, 'token': tok}]

        for ts in ts_list:
            # normalize ts item to dict
            ts_obj = ts if isinstance(ts, dict) else {'tradingsymbol': ts}
            exch = (ts_obj.get('exchange') or base.get('exchange') or '').upper()
            if exchange and exch and exch != exchange:
                continue
            # merged record
            rec = {**base, **ts_obj}
            # ensure common fields exist
            rec.setdefault('token', base.get('token'))
            rec.setdefault('tradingsymbol', rec.get('tradingsymbol') or rec.get('symbol') or rec.get('TRADINGSYM'))
            rows.append(rec)
    return rows


def _compute_qty_from_row(r: Dict) -> int:
    # priority: if explicit 'quantity' or 'qty' present use that, else sum dp_qty+t1_qty+holding_used or holdings_quantity
    if 'quantity' in r and r.get('quantity') not in (None, ''):
        return safe_int(r.get('quantity'))
    for k in ['qty', 'holdings_quantity', 'holding_qty', 'net_quantity']:
        if k in r and r.get(k) not in (None, ''):
            return safe_int(r.get(k))
    # otherwise sum granular fields
    parts = [safe_int(r.get('dp_qty')), safe_int(r.get('t1_qty')), safe_int(r.get('holding_used'))]
    total = sum(parts)
    if total > 0:
        return total
    # fallback to sellable or available if present
    for k in ['sellable_quantity', 'available_quantity', 'available_qty', 'sellable']:
        if k in r and r.get(k) not in (None, ''):
            return safe_int(r.get(k))
    return 0


def _pick_first(row: Dict, candidates: List[str], default=None):
    for c in candidates:
        if c in row and row[c] not in (None, ''):
            return row[c]
    return default


# ------------------ Fetch holdings ------------------
try:
    resp = client.get_holdings()
except Exception as e:
    st.error(f"Holdings fetch failed: {e}")
    st.stop()

if show_debug:
    st.write("🔎 Raw holdings response:")
    st.write(resp)

if not isinstance(resp, dict) or resp.get('status') != 'SUCCESS':
    st.error("⚠️ Holdings API returned non-success. Showing raw response below:")
    st.write(resp)
    st.stop()

raw_list = resp.get('data', [])
if not raw_list:
    st.info("No holdings returned by API.")
    st.stop()

records = _flatten_holdings(raw_list, exchange=exchange_filter)
if not records:
    st.warning(f"No holdings found for exchange {exchange_filter}.")
    st.stop()

# Build dataframe
df = pd.DataFrame(records)

# Clean/normalize columns
# symbol/token
if 'tradingsymbol' in df.columns:
    df['symbol'] = df['tradingsymbol'].astype(str).str.upper()
elif 'symbol' in df.columns:
    df['symbol'] = df['symbol'].astype(str).str.upper()
else:
    df['symbol'] = df.get('TRADINGSYM', df.get('SYMBOL', '')).astype(str).str.upper()

if 'token' not in df.columns:
    df['token'] = df.get('TOKEN')

# quantities
df['quantity'] = df.apply(_compute_qty_from_row, axis=1)
# available / sellable
df['available_quantity'] = df.apply(lambda r: safe_int(_pick_first(r, ['sellable_quantity','available_quantity','available_qty','sellable'], r.get('quantity'))), axis=1)

# average price
df['avg_buy_price'] = df.apply(lambda r: safe_float(_pick_first(r, ['avg_buy_price','average_price','avg_price','buy_price','avg_price_paid'], r.get('average_price', 0.0))), axis=1)

# product / product_type (if provided)
df['product_type'] = df.get('product_type').fillna(df.get('productType'))

# invested value
df['invested_value'] = df['avg_buy_price'] * df['quantity']

# optional: fetch live LTP and prev_close
if fetch_ltp:
    tokens = df['token'].fillna('').astype(str).tolist()
    ltp_list = []
    prev_list = []

    # best-effort sequential fetching (optionally parallelizable)
    if concurrency and concurrency > 0:
        # lightweight parallelization; avoid large threadpools for many symbols
        from concurrent.futures import ThreadPoolExecutor, as_completed
        def _fetch_one(tok):
            try:
                q = client.get_quotes(exchange=exchange_filter, token=tok)
                l = find_in_nested(q, ['ltp','last_price','lastTradedPrice','lastPrice','ltpPrice','last'])
                p = find_in_nested(q, ['prev_close','previous_close','previousClose','prevclose','yesterdayClose'])
                return safe_float(l, 0.0), (safe_float(p, np.nan) if p is not None else np.nan)
            except Exception:
                return 0.0, np.nan

        with ThreadPoolExecutor(max_workers=min(8, concurrency)) as ex:
            futures = {ex.submit(_fetch_one, t): t for t in tokens}
            for fut in as_completed(futures):
                l, p = fut.result()
                ltp_list.append(l)
                prev_list.append(p)
    else:
        for tok in tokens:
            try:
                q = client.get_quotes(exchange=exchange_filter, token=tok)
                l = find_in_nested(q, ['ltp','last_price','lastTradedPrice','lastPrice','ltpPrice','last'])
                p = find_in_nested(q, ['prev_close','previous_close','previousClose','prevclose','yesterdayClose'])
                ltp_list.append(safe_float(l, 0.0))
                prev_list.append(safe_float(p, np.nan) if p is not None else np.nan)
            except Exception:
                ltp_list.append(0.0)
                prev_list.append(np.nan)

    df['ltp'] = pd.to_numeric(pd.Series(ltp_list), errors='coerce').fillna(0.0)
    df['prev_close'] = pd.to_numeric(pd.Series(prev_list), errors='coerce')
else:
    df['ltp'] = 0.0
    df['prev_close'] = np.nan

# derived values
df['current_value'] = df['ltp'] * df['quantity']
df['unrealized_pnl'] = df['current_value'] - df['invested_value']
# today's PnL uses prev_close; rows with missing prev_close are NaN
df['today_pnl'] = (df['ltp'] - df['prev_close']) * df['quantity']

# capital allocation
df['capital_allocation_%'] = (df['invested_value'] / float(capital)) * 100

# tidy & sort
display_cols = [
    'symbol','token','quantity','available_quantity','avg_buy_price','invested_value','ltp','prev_close','current_value','unrealized_pnl','today_pnl','capital_allocation_%','product_type'
]
# keep only columns that exist
display_cols = [c for c in display_cols if c in df.columns]
df_display = df[display_cols].copy()

# rounding
for col in ['avg_buy_price','invested_value','ltp','current_value','unrealized_pnl','today_pnl','capital_allocation_%']:
    if col in df_display.columns:
        df_display[col] = df_display[col].map(lambda x: float(np.round(x,2)) if pd.notna(x) else x)

# set index by symbol for nicer display
if 'symbol' in df_display.columns:
    df_display = df_display.sort_values(by='capital_allocation_%', ascending=False).reset_index(drop=True)

# store
st.session_state['holdings_df'] = df.copy()

# ------------------ KPIs ------------------
st.subheader("Portfolio Summary")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Positions", f"{len(df)}")
col2.metric("Total Invested", f"₹{df['invested_value'].sum():,.2f}")
col3.metric("Market Value (LTP)", f"₹{df['current_value'].sum():,.2f}")
# treat missing today's pnl as zero for portfolio metric but show missing count
today_sum = df['today_pnl'].fillna(0.0).sum()
missing_today = int(df['today_pnl'].isna().sum())
col4.metric("Today PnL", f"₹{today_sum:,.2f}")
if missing_today > 0:
    st.caption(f"Note: {missing_today} positions missing prev_close → Today PnL not available for them (enable fetch LTP).")

# Show top winners/losers
st.subheader("Top Winners / Losers (Unrealized)")
if 'unrealized_pnl' in df.columns:
    winners = df.sort_values('unrealized_pnl', ascending=False).head(5)
    losers = df.sort_values('unrealized_pnl').head(5)
    wcol, lcol = st.columns(2)
    with wcol:
        st.write("Winners")
        st.table(winners[['symbol','quantity','avg_buy_price','ltp','unrealized_pnl']])
    with lcol:
        st.write("Losers")
        st.table(losers[['symbol','quantity','avg_buy_price','ltp','unrealized_pnl']])

# Display main table
st.subheader("Holdings table")
st.dataframe(df_display, use_container_width=True)

# Visuals
try:
    import plotly.graph_objects as go
    st.subheader("Capital Allocation")
    pie_df = df[['symbol','capital_allocation_%']].copy()
    cash_pct = max(0.0, 100 - pie_df['capital_allocation_%'].sum()) if not pie_df.empty else 100.0
    pie_df = pd.concat([pie_df, pd.DataFrame([{'symbol':'Cash','capital_allocation_%':cash_pct}])], ignore_index=True)
    fig = go.Figure(data=[go.Pie(labels=pie_df['symbol'], values=pie_df['capital_allocation_%'], hole=0.35)])
    fig.update_traces(textinfo='label+percent')
    st.plotly_chart(fig, use_container_width=True)

    st.subheader('Unrealized PnL by position')
    upnl = df[['symbol','unrealized_pnl']].copy()
    upnl = upnl.sort_values('unrealized_pnl', ascending=False)
    fig2 = go.Figure(data=[go.Bar(x=upnl['symbol'], y=upnl['unrealized_pnl'])])
    fig2.update_layout(yaxis_title='Unrealized PnL', xaxis_title='Symbol')
    st.plotly_chart(fig2, use_container_width=True)
except Exception:
    pass

# Export
st.subheader('Export / Actions')
csv_bytes = df_display.to_csv(index=False).encode('utf-8')
st.download_button('Download holdings CSV', csv_bytes, file_name='holdings_cleaned.csv', mime='text/csv')

st.success('Holdings loaded and normalized. You can use `st.session_state["holdings_df"]` in other pages.')

# ------------------ End ------------------
