# final_holdings_dashboard_full.py
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
    """Recursively look for any key in keys (case-insensitive) inside nested dict/list."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        klower = {k.lower() for k in keys}
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

# (Optional) small safe converter for names
def to_symbol_str(x):
    if x is None:
        return ""
    return str(x).strip()

# ------------------ UI: Sidebar ------------------
debug = st.sidebar.checkbox("Show debug (raw responses)", value=False)
use_definedge_api_key = st.sidebar.checkbox("Use Definedge API key for history fallback", value=False)
if use_definedge_api_key:
    st.sidebar.text_input("Definedge API key (also put into session_state 'definedge_api_key')", key="definedge_api_key_input")

capital = st.sidebar.number_input("Total Capital (₹)", value=DEFAULT_TOTAL_CAPITAL, step=10000)
initial_sl_pct = st.sidebar.number_input("Initial Stop Loss (%)", value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1)/100
targets_input = st.sidebar.text_input("Targets % (comma sep.)", ", ".join(map(str, DEFAULT_TARGETS)))
try:
    target_pcts = sorted([max(0.0, float(t.strip())/100.0) for t in targets_input.split(",") if t.strip() != ""])
    if not target_pcts:
        target_pcts = [t/100.0 for t in DEFAULT_TARGETS]
except Exception:
    st.sidebar.error("Invalid targets input, using defaults")
    target_pcts = [t/100.0 for t in DEFAULT_TARGETS]
trailing_thresholds = target_pcts
show_actions = st.sidebar.checkbox("Show Action Buttons (square-off / place SL)", value=False)

# ------------------ Parse & Fetch holdings ------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first (session_state['client'] required).")
    st.stop()

try:
    holdings_resp = client.get_holdings()
    if debug:
        st.write("🔎 Raw holdings response (first 2 items):")
        try:
            st.json(holdings_resp if isinstance(holdings_resp, dict) else str(holdings_resp)[:2000])
        except Exception:
            st.write(str(holdings_resp)[:2000])
    if not holdings_resp or not isinstance(holdings_resp, dict) or holdings_resp.get("status") not in ("SUCCESS", "Success", "OK", "success"):
        st.warning("⚠️ No holdings returned or API error. See debug for raw response.")
        st.stop()

    raw = holdings_resp.get("data", []) or []
    if len(raw) == 0:
        st.info("✅ No holdings present.")
        st.stop()

    # Build normalized rows — keep only NSE entries
    rows = []
    for item in raw:
        # quantities from top-level fields
        dp_qty = safe_float(item.get("dp_qty") or item.get("dpQty") or 0) or 0.0
        t1_qty = safe_float(item.get("t1_qty") or item.get("t1Qty") or 0) or 0.0
        # sold qty: prefer trade_qty, fallback to holding_used
        trade_qty = safe_float(item.get("trade_qty") or item.get("tradeQty"))
        if trade_qty is None:
            trade_qty = safe_float(item.get("holding_used") or item.get("holdingUsed")) or 0.0
        else:
            trade_qty = trade_qty or 0.0
        # sell amount might be 'sell_amt' or 'sell_amount'
        sell_amt = safe_float(item.get("sell_amt") or item.get("sell_amount") or item.get("sellAmt")) or 0.0
        # average buy price: prefer avg_buy_price / average_price
        avg_buy_price = safe_float(item.get("avg_buy_price") or item.get("average_price") or item.get("avgPrice")) or 0.0

        # tradingsymbol may be list/dict/str
        ts = item.get("tradingsymbol") or item.get("tradingsymbols") or item.get("symbol")
        nse_entry = None
        if isinstance(ts, list):
            for t in ts:
                if isinstance(t, dict) and (t.get("exchange") == "NSE" or t.get("exchange") == "NSE "):
                    nse_entry = t
                    break
                # sometimes object keys are lowercase
                if isinstance(t, dict) and str(t.get("exchange")).upper() == "NSE":
                    nse_entry = t
                    break
        elif isinstance(ts, dict):
            if str(ts.get("exchange", "")).upper() == "NSE":
                nse_entry = ts
        elif isinstance(ts, str):
            # no token info, but symbol string provided — assume NSE
            nse_entry = {"tradingsymbol": ts, "token": item.get("token")}

        # also try to collect token from top-level item if nse_entry missing token
        token = None
        symbol = None
        if nse_entry:
            symbol = to_symbol_str(nse_entry.get("tradingsymbol") or nse_entry.get("symbol"))
            token = nse_entry.get("token") or item.get("token") or ""
        else:
            # fallback: if top-level tradingsymbol exists as string
            ttop = item.get("tradingsymbol")
            if isinstance(ttop, str):
                symbol = to_symbol_str(ttop)
                token = item.get("token") or ""
            else:
                # skip non-NSE or unidentifiable
                continue

        rows.append({
            "symbol": symbol,
            "token": token,
            "dp_qty": int(dp_qty),
            "t1_qty": int(t1_qty),
            "buy_qty_partial": int(dp_qty + t1_qty),  # buys present
            "trade_qty": int(trade_qty),
            "sell_amt": float(sell_amt),
            "avg_buy_price": float(avg_buy_price),
            "raw": item
        })

    if not rows:
        st.warning("⚠️ No NSE holdings parsed from response.")
        st.stop()

    df = pd.DataFrame(rows)

    # Aggregate by symbol (if duplicates)
    def _agg(g):
        buy_qty = int(g["buy_qty_partial"].sum())
        sold_qty = int(g["trade_qty"].sum())
        sell_amt = float(g["sell_amt"].sum())
        # weighted average price based on buy quantities (if no buys, fallback to simple mean)
        denom = max(g["buy_qty_partial"].sum(), 1)
        weighted_avg = float((g["avg_buy_price"] * g["buy_qty_partial"]).sum() / denom) if denom > 0 else float(g["avg_buy_price"].mean())
        token = g["token"].iat[0] if "token" in g else ""
        return pd.Series({
            "dp_qty": int(g["dp_qty"].sum()),
            "t1_qty": int(g["t1_qty"].sum()),
            "buy_qty": buy_qty,
            "trade_qty": sold_qty,
            "sold_amt": sell_amt,
            "avg_buy_price": weighted_avg,
            "token": token
        })

    df = df.groupby("symbol", as_index=False).apply(_agg).reset_index()

    # Compute open / sold / quantity fields
    df["sold_qty"] = df["trade_qty"].astype(int)
    df["buy_qty"] = df["buy_qty"].astype(int)
    df["open_qty"] = (df["buy_qty"] - df["sold_qty"]).clip(lower=0).astype(int)
    df["quantity"] = df["open_qty"]  # compatibility

    # ------------------ Fetch LTP and prev_close (quote or fallback) ------------------
    st.info("Fetching LTP & prev_close (quotes) — will fallback to historical if needed.")
    LTP_KEYS = ["ltp", "last_price", "lastTradedPrice", "lastPrice", "last"]
    POSSIBLE_PREV_KEYS = ["prev_close", "previous_close", "previousClose", "previousClosePrice", "prevClose", "prevclose"]

    ltp_list = []
    prev_list = []
    prev_source_list = []
    today_dt = datetime.now()
    today_date = today_dt.date()
    last_hist_df = None

    for _, r in df.iterrows():
        token = r.get("token") or ""
        symbol = r.get("symbol")
        ltp_val = None
        prev_from_quote = None

        # try broker quote
        try:
            quote_resp = client.get_quotes(exchange="NSE", token=token)
            if debug:
                st.write(f"Quote raw for {symbol} (token={token}):", quote_resp if isinstance(quote_resp, dict) else str(quote_resp)[:400])
            if isinstance(quote_resp, dict) and quote_resp:
                found_ltp = find_in_nested(quote_resp, LTP_KEYS)
                if found_ltp is not None:
                    ltp_val = safe_float(found_ltp)
                found_prev = find_in_nested(quote_resp, POSSIBLE_PREV_KEYS)
                if found_prev is not None:
                    prev_from_quote = safe_float(found_prev)
        except Exception as e:
            # ignore quote error, we'll fallback
            if debug:
                st.write(f"Quote fetch error for {symbol}: {e}")

        prev_close = None
        prev_source = None

        if prev_from_quote is not None:
            prev_close = float(prev_from_quote)
            prev_source = "quote"
        else:
            # fallback to historical CSV via client.historical_csv or Definedge API if configured
            try:
                hist_df = pd.DataFrame()
                if hasattr(client, "historical_csv"):
                    try:
                        frm = (today_dt - timedelta(days=30)).strftime("%d%m%Y%H%M")
                        to = today_dt.strftime("%d%m%Y%H%M")
                        hist_csv = client.historical_csv(segment="NSE", token=token, timeframe="day", frm=frm, to=to)
                        hist_df = pd.read_csv(io.StringIO(hist_csv), header=None, dtype=str) if isinstance(hist_csv, str) and hist_csv.strip() else pd.DataFrame()
                        # use parse_definedge_csv_text if CSV in that format (robust)
                        if not hist_df.empty:
                            hist_df = parse_definedge_csv_text("\n".join(hist_csv.splitlines()))
                    except Exception:
                        hist_df = pd.DataFrame()
                if (hist_df is None or hist_df.empty) and use_definedge_api_key:
                    api_key = st.session_state.get("definedge_api_key") or st.session_state.get("definedge_api_key_input")
                    if api_key:
                        try:
                            hist_df = fetch_hist_for_date_range(api_key, "NSE", token, today_dt - timedelta(days=30), today_dt)
                        except Exception:
                            hist_df = pd.DataFrame()
                if hist_df is not None and not hist_df.empty:
                    last_hist_df = hist_df.copy()
                    prev_close_val, reason = get_robust_prev_close_from_hist(hist_df, today_date)
                    if prev_close_val is not None:
                        prev_close = float(prev_close_val)
                        prev_source = f"historical:{reason}"
                else:
                    prev_close = None
                    prev_source = "no_hist"
            except Exception as exc:
                prev_close = None
                prev_source = f"hist_error:{str(exc)[:120]}"

        ltp_list.append(float(ltp_val) if ltp_val is not None else 0.0)
        prev_list.append(prev_close)
        prev_source_list.append(prev_source or "unknown")

    # attach prices
    df["ltp"] = pd.to_numeric(pd.Series(ltp_list), errors="coerce").fillna(0.0)
    df["prev_close"] = pd.to_numeric(pd.Series(prev_list), errors="coerce")
    df["prev_close_source"] = prev_source_list

    # ------------------ PnL calculations ------------------
    # realized = sell_amt - (sold_qty * avg_buy_price)
    df["realized_pnl"] = df["sold_amt"].fillna(0.0) - (df["sold_qty"].astype(float) * df["avg_buy_price"].astype(float))
    df["unrealized_pnl"] = (df["ltp"].astype(float) - df["avg_buy_price"].astype(float)) * df["open_qty"].astype(float)
    # Today PnL uses prev_close, if missing -> NaN
    df["today_pnL"] = (df["ltp"].astype(float) - df["prev_close"].astype(float)) * df["open_qty"].astype(float)
    df["pct_change"] = df.apply(lambda r: ((r["ltp"] - r["prev_close"]) / r["prev_close"] * 100) if pd.notna(r["prev_close"]) and r["prev_close"] != 0 else None, axis=1)
    df["total_pnl"] = df["realized_pnl"] + df["unrealized_pnl"]

    # invested / current / allocation
    df["invested_value"] = df["avg_buy_price"].astype(float) * df["open_qty"].astype(float)
    df["current_value"] = df["ltp"].astype(float) * df["open_qty"].astype(float)
    df["overall_pnl"] = df["current_value"] - df["invested_value"]
    df["capital_allocation_%"] = (df["invested_value"] / float(max(capital, 1))) * 100

    # ------------------ Stops / Targets / Risk (uses open_qty) ------------------
    def calc_stops_targets(row):
        avg = float(row.get("avg_buy_price") or 0.0)
        qty = int(row.get("open_qty") or 0)
        ltp = float(row.get("ltp") or 0.0)
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
                "side": side,
                "initial_sl_price": initial_sl_price,
                "tsl_price": tsl_price,
                "targets": targets,
                "initial_risk": initial_risk,
                "open_risk": open_risk,
                "realized_if_tsl_hit": realized_if_tsl_hit
            })
        else:
            # SHORT handling (kept for completeness)
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

    # explode target columns for display
    for i, tp in enumerate(target_pcts, start=1):
        df[f"target_{i}_pct"] = tp * 100
        df[f"target_{i}_price"] = df["targets"].apply(lambda lst: round(lst[i-1], 4) if isinstance(lst, list) and len(lst) >= i else 0.0)

    # ------------------ KPIs ------------------
    total_invested = df["invested_value"].sum()
    total_current = df["current_value"].sum()
    total_unrealized = df["unrealized_pnl"].sum()
    total_today_pnl = df["today_pnL"].fillna(0.0).sum()
    total_open_risk = df["open_risk"].sum()

    st.subheader("💰 Overall Summary")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Invested", f"₹{total_invested:,.2f}")
    k2.metric("Total Current", f"₹{total_current:,.2f}")
    k3.metric("Unrealized PnL", f"₹{total_unrealized:,.2f}")
    if total_today_pnl >= 0:
        k4.metric("Today PnL", f"₹{total_today_pnl:,.2f}", delta=f"₹{total_today_pnl:,.2f}")
    else:
        k4.metric("Today PnL", f"₹{total_today_pnl:,.2f}", delta=f"₹{total_today_pnl:,.2f}", delta_color="inverse")
    k5.metric("Open Risk (TSL)", f"₹{total_open_risk:,.2f}")

    # ------------------ Winners / Losers ------------------
    winners = int((df["total_pnl"] > 0).sum())
    losers = int((df["total_pnl"] < 0).sum())
    breakeven = int((df["total_pnl"] == 0).sum())
    st.write(f"🏆 Winners: {winners} | ❌ Losers: {losers} | ⚖️ Breakeven: {breakeven}")

    # ------------------ Visuals: Capital Pie & Risk Bar ------------------
    st.subheader("📊 Capital Allocation & Risk Visuals")
    col_a, col_b = st.columns([1, 1])

    # Pie - capital allocation (only positive allocation)
    with col_a:
        try:
            pie_df = df[["symbol", "capital_allocation_%"]].copy()
            pie_df = pie_df[pie_df["capital_allocation_%"] > 0]
            # add cash slice if needed
            cash_pct = max(0.0, 100.0 - pie_df["capital_allocation_%"].sum()) if not pie_df.empty else 100.0
            pie_plot_df = pie_df.copy()
            if cash_pct > 0:
                pie_plot_df = pd.concat([pie_plot_df, pd.DataFrame([{"symbol": "Cash", "capital_allocation_%": cash_pct}])], ignore_index=True)
            fig = go.Figure(data=[go.Pie(labels=pie_plot_df["symbol"], values=pie_plot_df["capital_allocation_%"], hole=0.35)])
            fig.update_traces(textinfo="label+percent")
            fig.update_layout(title_text="Capital Allocation %")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.write("Pie chart error:", e)

    # Bar - initial vs open risk
    with col_b:
        try:
            risk_df = df[["symbol", "initial_risk", "open_risk"]].copy()
            # keep only rows with any risk > 0 for clarity
            risk_df = risk_df[(risk_df["initial_risk"] > 0) | (risk_df["open_risk"] > 0)]
            if not risk_df.empty:
                fig2 = go.Figure()
                fig2.add_trace(go.Bar(x=risk_df["symbol"], y=risk_df["initial_risk"], name="Initial Risk"))
                fig2.add_trace(go.Bar(x=risk_df["symbol"], y=risk_df["open_risk"], name="Open Risk"))
                fig2.update_layout(barmode="group", title_text="Risk: Initial vs Open (₹)", xaxis_title="Symbol", yaxis_title="₹")
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.write("No positions with risk to show in bar chart.")
        except Exception as e:
            st.write("Risk chart error:", e)

    # ------------------ Positions table ------------------
    st.subheader("📋 Positions & Risk Table")
    display_cols = [
        "symbol", "quantity", "open_qty", "buy_qty", "sold_qty",
        "avg_buy_price", "ltp", "prev_close", "pct_change", "today_pnL",
        "realized_pnl", "unrealized_pnl", "total_pnl", "capital_allocation_%",
        "initial_sl_price", "tsl_price", "initial_risk", "open_risk"
    ]
    # ensure columns exist
    display_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[display_cols].sort_values(by="capital_allocation_%", ascending=False).reset_index(drop=True), use_container_width=True)

    # Export
    st.subheader("📥 Export")
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download positions with PnL (CSV)", csv_bytes, file_name="positions_pnl.csv", mime="text/csv")

    # optional show last historical sample (debug)
    if debug:
        try:
            if "last_hist_df" in locals() and last_hist_df is not None and hasattr(last_hist_df, "shape") and last_hist_df.shape[0] > 0:
                st.write("Historical data sample (last symbol):")
                st.dataframe(last_hist_df.head())
        except Exception:
            pass

except Exception as ee:
    st.error(f"⚠️ Error building dashboard: {ee}")
    st.text(traceback.format_exc())
