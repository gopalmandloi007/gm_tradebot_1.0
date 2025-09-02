# pages/01_dashboard.py
import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta, date
import plotly.graph_objects as go
import traceback

# ------------------ Configuration ------------------
st.set_page_config(layout="wide")
st.title("📊 Trading Dashboard — Definedge (Risk Managed — Improved)")

# ------------------ Defaults ------------------
DEFAULT_TOTAL_CAPITAL = 1400000
DEFAULT_INITIAL_SL_PCT = 2.0
DEFAULT_TARGETS = [10, 20, 30, 40]

# ------------------ Helper: parse Definedge CSV (kept for advanced use) ------------------
def parse_definedge_csv(raw_text, timeframe="day"):
    """
    Try to parse headerless Definedge CSV into DataFrame with DateTime and Close.
    Returns (df, error_or_none).
    This is more strict — we'll use a simpler extractor below as first choice.
    """
    if raw_text is None:
        return None, "empty response"
    try:
        s = raw_text.decode("utf-8", "ignore") if isinstance(raw_text, (bytes, bytearray)) else str(raw_text)
        s = s.strip()
        if not s:
            return None, "empty CSV"
        df = pd.read_csv(io.StringIO(s), header=None)
    except Exception as exc:
        return None, f"read_csv error: {exc}"

    if df.shape[0] == 0:
        return None, "no rows"

    # best-effort column naming for day/minute
    if timeframe in ("day", "minute"):
        if df.shape[1] >= 6:
            colnames = ["DateTime", "Open", "High", "Low", "Close", "Volume"]
            if df.shape[1] > 6:
                extras = [f"X{i}" for i in range(df.shape[1] - len(colnames))]
                df.columns = colnames + extras
            else:
                df.columns = colnames
        else:
            df.columns = [f"C{i}" for i in range(df.shape[1])]
            df = df.rename(columns={df.columns[0]: "DateTime"})
    else:
        df.columns = [f"C{i}" for i in range(df.shape[1])]

    # try parse numeric and datetime where possible (best-effort)
    try:
        if "DateTime" in df.columns:
            df["DateTime"] = pd.to_datetime(df["DateTime"], dayfirst=True, errors="coerce")
        for c in ["Open", "High", "Low", "Close", "Volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
    except Exception as exc:
        return None, f"parse error: {exc}"

    df = df.sort_values("DateTime").reset_index(drop=True) if "DateTime" in df.columns else df.reset_index(drop=True)
    return df, None


# ------------------ Simpler robust extractor for prev close from headerless CSV ------------------
def get_prev_close_from_hist_csv(raw_csv_text, today_date: date, debug=False):
    """
    Simpler extractor:
      - read headerless into df
      - prefer column index 4 as Close if present and numeric
      - try to parse first column to datetimes to pick last trading date < today
      - else dedupe closes and pick second-last distinct close if available
      - returns (prev_close_or_None, reason, closes_list_for_debug)
    """
    if raw_csv_text is None:
        return None, "empty_response", []

    try:
        s = raw_csv_text.decode("utf-8", "ignore") if isinstance(raw_csv_text, (bytes, bytearray)) else str(raw_csv_text)
        s = s.strip()
        if not s:
            return None, "empty_csv", []
        df = pd.read_csv(io.StringIO(s), header=None)
    except Exception as exc:
        return None, f"read_error:{exc}", []

    if df.shape[0] == 0:
        return None, "no_rows", []

    closes = []
    # If at least 5 columns, try column index 4 as Close
    if df.shape[1] >= 5:
        col4 = pd.to_numeric(df.iloc[:, 4], errors="coerce").dropna().tolist()
        if col4:
            closes = [float(x) for x in col4]
    # If we didn't get closes from col4, scan all rows and collect last numeric-like value from each row (heuristic)
    if not closes:
        for ridx in range(df.shape[0]):
            row = df.iloc[ridx].tolist()
            # find numeric values in row (right-to-left preference)
            numeric_vals = []
            for v in row:
                try:
                    numeric_vals.append(float(str(v).replace(",", "")))
                except Exception:
                    continue
            if numeric_vals:
                closes.append(numeric_vals[-1])  # last numeric value in the row
    # dedupe preserves first occurrence order
    dedup = []
    seen = set()
    for v in closes:
        if v not in seen:
            dedup.append(v)
            seen.add(v)

    # Try to parse first column as datetime to find last trading date < today
    prev_by_date = None
    try:
        firstcol = df.iloc[:, 0]
        parsed_dates = pd.to_datetime(firstcol, dayfirst=True, errors="coerce")
        valid_frac = parsed_dates.notna().sum() / max(1, len(parsed_dates))
        if valid_frac >= 0.5:
            # we have reasonable dates — construct mapping date -> closes in that row
            df_dates = df.copy()
            df_dates["__parsed_dt"] = parsed_dates
            df_dates["__date_only"] = df_dates["__parsed_dt"].dt.date
            # attempt to extract close numeric from column 4 if available else last numeric in row
            df_dates["__close"] = pd.to_numeric(df_dates.iloc[:, 4], errors="coerce") if df.shape[1] >= 5 else pd.NA
            # where __close is NaN, try fallback last numeric in row
            for ridx in df_dates.index:
                if pd.isna(df_dates.at[ridx, "__close"]):
                    row = df_dates.loc[ridx].tolist()
                    # find numeric in row
                    numeric_vals = []
                    for v in row:
                        try:
                            numeric_vals.append(float(str(v).replace(",", "")))
                        except Exception:
                            continue
                    if numeric_vals:
                        df_dates.at[ridx, "__close"] = numeric_vals[-1]
            # select rows with date strictly before today_date
            prior_rows = df_dates[df_dates["__date_only"] < today_date]
            if not prior_rows.empty:
                # take last prior date's last close
                last_prior_date = prior_rows["__date_only"].max()
                last_rows = prior_rows[prior_rows["__date_only"] == last_prior_date]
                last_rows = last_rows.sort_values("__parsed_dt")
                last_close_vals = pd.to_numeric(last_rows["__close"], errors="coerce").dropna().tolist()
                if last_close_vals:
                    prev_by_date = float(last_close_vals[-1])
                    return prev_by_date, "prev_trading_date", dedup
    except Exception:
        prev_by_date = None

    # if we reach here, use dedupe logic
    if len(dedup) >= 2:
        return float(dedup[-2]), "dedup_second_last", dedup
    if len(dedup) == 1:
        return float(dedup[-1]), "single_close", dedup

    return None, "no_numeric_closes", dedup


# ------------------ Client check ------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

# ------------------ Sidebar (user controls) ------------------
st.sidebar.header("⚙️ Dashboard Settings & Risk")
capital = st.sidebar.number_input(layout="wide", label="Total Capital (₹)", value=DEFAULT_TOTAL_CAPITAL, step=10000, key="capital_input")
initial_sl_pct = st.sidebar.number_input("Initial Stop Loss (%)", value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1, key="initial_sl_input")/100
targets_input = st.sidebar.text_input("Targets % (comma separated)", ",".join(map(str, DEFAULT_TARGETS)), key="targets_input")
show_debug = st.sidebar.checkbox("🐞 Show debug info (closes, CSV sample)", value=False)

try:
    target_pcts = sorted([max(0.0, float(t.strip())/100.0) for t in targets_input.split(",") if t.strip()])
    if not target_pcts:
        target_pcts = [t/100.0 for t in DEFAULT_TARGETS]
except Exception:
    st.sidebar.error("Invalid Targets input — using defaults")
    target_pcts = [t/100.0 for t in DEFAULT_TARGETS]

trailing_thresholds = target_pcts

# ------------------ Fetch holdings ------------------
try:
    holdings_resp = client.get_holdings()
    if not holdings_resp or not isinstance(holdings_resp, dict) or holdings_resp.get("status") != "SUCCESS":
        st.warning("⚠️ No holdings found or API returned error")
        st.stop()

    holdings = holdings_resp.get("data", [])
    if not holdings:
        st.info("✅ No holdings found.")
        st.stop()

    # build normalized rows
    rows = []
    for item in holdings:
        # defensive numeric parsing
        try:
            avg_buy_price = float(item.get("avg_buy_price") or item.get("avgprice") or 0)
        except Exception:
            avg_buy_price = 0.0
        try:
            dp_qty = float(item.get("dp_qty") or item.get("dpqty") or 0)
        except Exception:
            dp_qty = 0.0
        try:
            t1_qty = float(item.get("t1_qty") or 0)
        except Exception:
            t1_qty = 0.0
        try:
            holding_used = float(item.get("holding_used") or 0)
        except Exception:
            holding_used = 0.0

        total_qty = int(dp_qty + t1_qty + holding_used)

        tradings = item.get("tradingsymbol") or []
        if isinstance(tradings, dict):
            tradings = [tradings]
        if isinstance(tradings, str):
            rows.append({
                "symbol": tradings,
                "token": item.get("token") or item.get("instrument_token"),
                "avg_buy_price": avg_buy_price,
                "quantity": total_qty,
                "product_type": item.get("product_type", "")
            })
        else:
            for sym in tradings:
                sym_obj = sym if isinstance(sym, dict) else {}
                sym_exchange = sym_obj.get("exchange") if isinstance(sym_obj, dict) else None
                # keep only NSE entries (your original logic did this)
                if sym_exchange and sym_exchange != "NSE":
                    continue
                rows.append({
                    "symbol": sym_obj.get("tradingsymbol") or sym_obj.get("symbol") or (item.get("tradingsymbol") if isinstance(item.get("tradingsymbol"), str) else None),
                    "token": sym_obj.get("token") or item.get("token") or sym_obj.get("instrument_token"),
                    "avg_buy_price": avg_buy_price,
                    "quantity": total_qty,
                    "product_type": item.get("product_type", "")
                })

    if not rows:
        st.warning("⚠️ No NSE holdings found.")
        st.stop()

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["symbol"]).reset_index(drop=True)

    # ------------------ Prices (LTP + Prev Close) ------------------
    st.info("Fetching live prices and previous close (robust logic). This may take a few seconds.")
    ltp_list = []
    prev_close_list = []
    prev_source_list = []
    last_hist_sample = None

    today_dt = datetime.now()
    today_date = today_dt.date()

    POSSIBLE_PREV_KEYS = [
        "prev_close", "previous_close", "previousClose", "previousClosePrice", "prevClose",
        "prevclose", "previousclose", "prev_close_price", "yesterdayClose", "previous_close_price",
        "prev_close_val", "previous_close_val", "yesterday_close"
    ]

    for idx, row in df.iterrows():
        token = row.get("token")
        symbol = row.get("symbol")
        ltp = 0.0
        prev_close = None
        prev_source = None

        # --- 1) try quotes API for LTP and prev-close keys ---
        try:
            quote_resp = client.get_quotes(exchange="NSE", token=token)
            if isinstance(quote_resp, dict):
                ltp_candidates = [
                    quote_resp.get("ltp"),
                    quote_resp.get("last_price"),
                    quote_resp.get("lastTradedPrice"),
                    quote_resp.get("lastPrice"),
                    quote_resp.get("ltpPrice")
                ]
                # pick first non-empty numeric
                for cand in ltp_candidates:
                    if cand not in (None, "", "null"):
                        try:
                            ltp = float(str(cand).replace(",", ""))
                            break
                        except Exception:
                            continue

                # try possible prev-close keys
                for k in POSSIBLE_PREV_KEYS:
                    if k in quote_resp and quote_resp.get(k) not in (None, "", "null"):
                        try:
                            prev_close = float(str(quote_resp.get(k)).replace(",", ""))
                            prev_source = f"quote:{k}"
                            break
                        except Exception:
                            prev_close = None
                            prev_source = None
        except Exception:
            # ignore and fallback to history
            quote_resp = None

        # --- 2) if prev_close still missing -> try historical CSV (single request covering recent days) ---
        if prev_close is None:
            try:
                # request last N days (use 14 days lookback, tweakable)
                lookback_days = 14
                from_dt = (today_dt - timedelta(days=lookback_days)).strftime("%d%m%Y")
                to_dt = today_dt.strftime("%d%m%Y")
                frm = f"{from_dt}0000"
                to = f"{to_dt}2359"
                hist_csv = client.historical_csv(segment="NSE", token=token, timeframe="day", frm=frm, to=to)

                # keep sample for UI debug
                last_hist_sample = hist_csv

                # use simpler extractor first
                prev_val, reason, closes_debug = get_prev_close_from_hist_csv(hist_csv, today_date, debug=show_debug)
                if prev_val is not None:
                    prev_close = float(prev_val)
                    prev_source = f"historical:{reason}"
                else:
                    # fallback: try the stricter parser if you want (kept for safety)
                    hist_df, err = parse_definedge_csv(hist_csv, timeframe="day")
                    if hist_df is not None:
                        prev_val2, reason2 = None, None
                        try:
                            prev_val2, reason2 = (get_robust_prev_close_from_hist(hist_df, today_date) if 'get_robust_prev_close_from_hist' in globals() else (None, None))
                        except Exception:
                            prev_val2, reason2 = None, None
                        if prev_val2 is not None:
                            prev_close = float(prev_val2)
                            prev_source = f"historical_strict:{reason2}"
                # optionally show debug closes
                if show_debug:
                    try:
                        st.write(f"🔎 {symbol} ({token}) historical closes snippet: {closes_debug[:10]} (len={len(closes_debug)})")
                        if last_hist_sample and len(str(last_hist_sample)) < 10000:
                            st.code(str(last_hist_sample)[:4000])
                    except Exception:
                        pass

            except Exception as exc:
                # historical failed
                prev_close = None
                prev_source = f"hist_error:{str(exc)[:120]}"

        # --- 3) final fallback(s) ---
        # If prev_close is still None, prefer to set prev_close = ltp (so today_pnl -> 0) rather than 0 which inflates today's pnl.
        if prev_close is None:
            if ltp and ltp > 0:
                prev_close = float(ltp)
                prev_source = prev_source or "fallback:ltp"
            else:
                # try to use last available close from closes_debug if present
                # else set to 0
                prev_close = 0.0
                prev_source = prev_source or "fallback:0"

        # append
        ltp_list.append(float(ltp or 0.0))
        prev_close_list.append(float(prev_close or 0.0))
        prev_source_list.append(prev_source or "unknown")

    # attach to df
    df["ltp"] = ltp_list
    df["prev_close"] = prev_close_list
    df["prev_close_source"] = prev_source_list

except Exception as e:
    st.error(f"⚠️ Error fetching holdings or prices: {e}")
    st.text(traceback.format_exc())
    st.stop()

# ------------------ Optional: show last hist csv sample ------------------
try:
    if show_debug and last_hist_sample:
        st.subheader("Raw historical CSV sample (last fetched symbol)")
        st.code(str(last_hist_sample)[:8000])
except Exception:
    pass

# ------------------ Calculate P&L and other metrics ------------------
# Ensure numeric coercion
for col in ["avg_buy_price", "quantity", "ltp", "prev_close"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

df["invested_value"] = df["avg_buy_price"] * df["quantity"]
df["current_value"] = df["ltp"] * df["quantity"]
df["today_pnl"] = (df["ltp"] - df["prev_close"]) * df["quantity"]
df["overall_pnl"] = df["current_value"] - df["invested_value"]
df["capital_allocation_%"] = (df["invested_value"] / capital) * 100

# ------------------ Function to calculate stops and targets ------------------
def calc_stops_targets(row):
    avg = float(row.get("avg_buy_price") or 0.0)
    qty = int(row.get("quantity") or 0)
    ltp = float(row.get("ltp") or 0.0)

    if qty == 0 or avg == 0:
        return {
            "side": "FLAT",
            "initial_sl_price": 0.0,
            "tsl_price": 0.0,
            "targets": [0.0]*len(target_pcts),
            "initial_risk": 0.0,
            "open_risk": 0.0,
            "realized_if_tsl_hit": 0.0
        }

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

        return {
            "side": side,
            "initial_sl_price": initial_sl_price,
            "tsl_price": tsl_price,
            "targets": targets,
            "initial_risk": initial_risk,
            "open_risk": open_risk,
            "realized_if_tsl_hit": realized_if_tsl_hit
        }
    else:  # SHORT
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

        return {
            "side": side,
            "initial_sl_price": initial_sl_price,
            "tsl_price": tsl_price,
            "targets": targets,
            "initial_risk": initial_risk,
            "open_risk": open_risk,
            "realized_if_tsl_hit": realized_if_tsl_hit
        }

# ------------------ Apply stops and targets ------------------
results = df.apply(calc_stops_targets, axis=1, result_type="expand")
df = pd.concat([df, results], axis=1)

# ------------------ Explode targets into columns ------------------
for i, tp in enumerate(target_pcts, start=1):
    df[f"target_{i}_pct"] = tp * 100
    df[f"target_{i}_price"] = df["targets"].apply(lambda lst: round(lst[i-1], 4) if isinstance(lst, list) and len(lst) >= i else 0.0)

# ------------------ Portfolio Metrics ------------------
total_invested = df["invested_value"].sum()
total_current = df["current_value"].sum()
total_overall_pnl = df["overall_pnl"].sum()
total_today_pnl = df["today_pnl"].sum()
total_initial_risk = df["initial_risk"].sum() if "initial_risk" in df.columns else 0.0
total_open_risk = df["open_risk"].sum() if "open_risk" in df.columns else 0.0
total_realized_if_all_tsl = df["realized_if_tsl_hit"].sum() if "realized_if_tsl_hit" in df.columns else 0.0

# ------------------ Display KPIs ------------------
st.subheader("💰 Overall Summary")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Invested", f"₹{total_invested:,.2f}")
k2.metric("Total Current", f"₹{total_current:,.2f}")
k3.metric("Overall Unrealized PnL", f"₹{total_overall_pnl:,.2f}")
k4.metric("Today PnL", f"₹{total_today_pnl:,.2f}")
k5.metric("Total Open Risk (TSL)", f"₹{total_open_risk:,.2f}")

# ------------------ Display table (with prev_close source) ------------------
display_cols = ["symbol", "quantity", "side", "avg_buy_price", "ltp", "prev_close", "prev_close_source",
                "invested_value", "current_value", "overall_pnl", "today_pnl", "capital_allocation_%",
                "initial_sl_price", "tsl_price", "initial_risk", "open_risk", "realized_if_tsl_hit"]
for i in range(1, len(target_pcts) + 1):
    display_cols += [f"target_{i}_pct", f"target_{i}_price"]

st.subheader("📋 Positions & Risk Table")
st.dataframe(df[[c for c in display_cols if c in df.columns]].sort_values(by="capital_allocation_%", ascending=False).reset_index(drop=True), use_container_width=True)

# ------------------ Export ------------------
st.subheader("📥 Export")
csv_bytes = df.to_csv(index=False).encode("utf-8")
st.download_button("Download positions with risk data (CSV)", csv_bytes, file_name="positions_risk.csv", mime="text/csv")
