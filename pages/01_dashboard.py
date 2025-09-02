import streamlit as st
import pandas as pd
import numpy as np
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

# ------------------ Helper: robust historical CSV parser ------------------
def parse_historical_csv(raw_csv_text):
    """
    Robustly parse historical CSV text to a dataframe with a reliable DateTime column and Close column.
    Returns (hist_df, error_message_or_None).
    """
    s = raw_csv_text
    if isinstance(s, bytes):
        try:
            s = s.decode("utf-8", "ignore")
        except Exception:
            s = str(s)
    s = str(s)
    if not s.strip():
        return None, "empty CSV"

    separators = [",", ";", "\t", "|"]
    best_candidate = None
    best_score = -1
    best_reason = None

    def try_parse_series_to_datetime(srs):
        """Try multiple strategies to parse a series to datetimes; return parsed Series and valid_count."""
        n = len(srs)
        if n == 0:
            return pd.Series([pd.NaT]*0), 0

        # first try direct pandas inference (strings)
        parsed = pd.to_datetime(srs, dayfirst=True, errors="coerce")
        valid = parsed.notna().sum()
        # if parsed yields years that look sane, prefer it
        try:
            max_year = parsed.dt.year.dropna().max() if valid > 0 else None
        except Exception:
            max_year = None

        if valid / max(1, n) >= 0.6 and (max_year is None or (max_year and max_year >= 1990)):
            return parsed, valid

        # if not good enough, try numeric epoch conversions if series can be numeric
        numeric = pd.to_numeric(srs, errors="coerce")
        if numeric.notna().sum() == 0:
            # no numeric values, return what we have
            return parsed, valid

        for unit in ["ns", "us", "ms", "s"]:
            try:
                parsed2 = pd.to_datetime(numeric, unit=unit, errors="coerce")
                valid2 = parsed2.notna().sum()
                try:
                    max_year2 = parsed2.dt.year.dropna().max() if valid2 > 0 else None
                except Exception:
                    max_year2 = None
                if valid2 / max(1, n) >= 0.6 and (max_year2 is None or (max_year2 and max_year2 >= 1990)):
                    return parsed2, valid2
            except Exception:
                continue

        # if none hit threshold, return the best we have (direct parse)
        return parsed, valid

    # Try different separators and header options; pick the best candidate datetime column
    for sep in separators:
        for header_option in [0, None]:
            try:
                df_try = pd.read_csv(io.StringIO(s), sep=sep, header=header_option)
            except Exception:
                continue

            # If file is empty after read, skip
            if df_try.shape[0] == 0:
                continue

            # For each column, try parsing as datetime
            for col in df_try.columns:
                try:
                    parsed_series, valid_count = try_parse_series_to_datetime(df_try[col])
                except Exception:
                    parsed_series, valid_count = pd.Series([pd.NaT]*len(df_try)), 0

                # Score candidate: prefer more valid parsed datetimes and recent years
                score = valid_count

                # boost score if parsed years look recent
                try:
                    year_max = parsed_series.dt.year.dropna().max() if valid_count > 0 else None
                    if year_max and year_max >= 2000:
                        score += 1000
                    elif year_max and (1975 <= year_max < 2000):
                        score += 200
                except Exception:
                    pass

                if score > best_score:
                    best_score = score
                    best_candidate = {
                        "df": df_try.copy(),
                        "sep": sep,
                        "header": header_option,
                        "date_col": col,
                        "parsed_dt": parsed_series,
                        "valid_count": valid_count
                    }
                    best_reason = f"sep={sep} header={header_option} col={col} valid={valid_count}"

    # if no candidate found, fallback: try default read with comma and header=0
    if best_candidate is None:
        try:
            df_fallback = pd.read_csv(io.StringIO(s), header=0)
            # try to parse first column
            first_col = df_fallback.columns[0] if len(df_fallback.columns) > 0 else None
            if first_col is not None:
                parsed_dt = pd.to_datetime(df_fallback[first_col], dayfirst=True, errors="coerce")
                df_fallback["DateTime"] = parsed_dt
                return df_fallback, None
            else:
                return None, "could not parse CSV"
        except Exception as exc:
            return None, f"fallback read failed: {exc}"

    # Build hist_df from best candidate
    hist_df = best_candidate["df"]
    parsed_dt = best_candidate["parsed_dt"]

    # If parsed_dt has too many NaT or looks like 1970 (bad parse), try numeric-unit-only approach on the chosen column
    if parsed_dt.notna().sum() / max(1, len(parsed_dt)) < 0.3:
        # attempt numeric conversions explicitly
        numeric = pd.to_numeric(hist_df[best_candidate["date_col"]], errors="coerce")
        for unit in ["ns", "us", "ms", "s"]:
            try:
                maybe = pd.to_datetime(numeric, unit=unit, errors="coerce")
                if maybe.notna().sum() / max(1, len(maybe)) >= 0.6 and (maybe.dt.year.dropna().max() or 0) >= 1990:
                    parsed_dt = maybe
                    break
            except Exception:
                continue

    # If parsed_dt still bad but parsed years are 1970 etc, we still accept it but mark a warning (we'll try to avoid 1970 later)
    hist_df["DateTime"] = parsed_dt

    # Now try to ensure Close column exists. Common cases:
    cols_lower = [c.lower() for c in hist_df.columns]
    if "close" not in cols_lower:
        # if header missing or unnamed, try mapping by position
        if hist_df.shape[1] >= 5:
            # assume order DateTime, Open, High, Low, Close, Volume, OI (common)
            expected = ["DateTime", "Open", "High", "Low", "Close", "Volume", "OI"]
            # create copy of values and assign expected names for the first n columns
            hist_df = hist_df.copy()
            hist_df.columns = expected[:hist_df.shape[1]]
        else:
            # try to find column whose values look like prices (numeric, not huge)
            numeric_counts = {}
            for c in hist_df.columns:
                num = pd.to_numeric(hist_df[c], errors="coerce")
                numeric_counts[c] = num.notna().sum()
            # choose column (other than DateTime) with highest numeric counts
            cand = max((c for c in hist_df.columns if c != "DateTime"), key=lambda x: numeric_counts.get(x, 0), default=None)
            if cand:
                hist_df = hist_df.rename(columns={cand: "Close"})

    # Final cleanup: coerce Close to numeric if present
    if "Close" in hist_df.columns:
        hist_df["Close"] = pd.to_numeric(hist_df["Close"], errors="coerce")

    # Drop rows without DateTime if too many
    if hist_df["DateTime"].isna().all():
        return None, f"parsed DateTime seems invalid ({best_reason})"

    # If parsed DateTime rows have year < 1990 for majority, warn but continue
    try:
        yr_min = hist_df["DateTime"].dt.year.dropna().min()
        if yr_min is not None and yr_min < 1990:
            # still accept but return a warning
            return hist_df, f"warning: parsed DateTime contains early years (min_year={yr_min}) - check CSV format"
    except Exception:
        pass

    return hist_df, None


# ------------------ Client check ------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

# ------------------ Sidebar (user controls) ------------------
st.sidebar.header("⚙️ Dashboard Settings & Risk")
capital = st.sidebar.number_input("Total Capital (₹)", value=DEFAULT_TOTAL_CAPITAL, step=10000)
initial_sl_pct = st.sidebar.number_input("Initial Stop Loss (%)", value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1)/100
targets_input = st.sidebar.text_input("Targets % (comma separated)", ",".join(map(str, DEFAULT_TARGETS)))

try:
    # parse targets and ensure sorted ascending
    target_pcts = sorted([max(0.0, float(t.strip())/100.0) for t in targets_input.split(",") if t.strip()])
    if not target_pcts:
        target_pcts = [t/100.0 for t in DEFAULT_TARGETS]
except Exception:
    st.sidebar.error("Invalid Targets input — using defaults")
    target_pcts = [t/100.0 for t in DEFAULT_TARGETS]

# trailing thresholds are the same as target thresholds (user-specified)
trailing_thresholds = target_pcts

auto_refresh = st.sidebar.checkbox("Auto-refresh LTP on page interaction", value=False)
show_actions = st.sidebar.checkbox("Show Action Buttons (Square-off / Place SL)", value=False)
st.sidebar.markdown("---")

# ------------------ Fetch holdings ------------------
try:
    holdings_resp = client.get_holdings()
    if not holdings_resp or holdings_resp.get("status") != "SUCCESS":
        st.warning("⚠️ No holdings found or API returned error")
        st.stop()

    holdings = holdings_resp.get("data", [])
    if not holdings:
        st.info("✅ No holdings found.")
        st.stop()

    rows = []
    for item in holdings:
        # Defensive parsing for numeric fields
        try:
            avg_buy_price = float(item.get("avg_buy_price") or 0)
        except Exception:
            avg_buy_price = 0.0
        try:
            dp_qty = float(item.get("dp_qty") or 0)
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
                "token": item.get("token"),
                "avg_buy_price": avg_buy_price,
                "quantity": total_qty,
                "product_type": item.get("product_type", "")
            })
        else:
            for sym in tradings:
                sym_obj = sym if isinstance(sym, dict) else {}
                sym_exchange = sym_obj.get("exchange") if isinstance(sym_obj, dict) else None
                if sym_exchange and sym_exchange != "NSE":
                    continue
                rows.append({
                    "symbol": sym_obj.get("tradingsymbol") or sym_obj.get("symbol") or item.get("tradingsymbol"),
                    "token": sym_obj.get("token") or item.get("token"),
                    "avg_buy_price": avg_buy_price,
                    "quantity": total_qty,
                    "product_type": item.get("product_type", "")
                })

    if not rows:
        st.warning("⚠️ No NSE holdings found.")
        st.stop()

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["symbol"]).reset_index(drop=True)

    # ------------------ Fetch LTP + robust prev_close per symbol ------------------
    st.info("Fetching live prices and previous close (robust logic).")
    ltp_list = []
    prev_close_list = []
    prev_source_list = []

    today_dt = datetime.now()
    today_date = today_dt.date()

    POSSIBLE_PREV_KEYS = [
        "prev_close", "previous_close", "previousClose", "previousClosePrice", "prevClose",
        "prevclose", "previousclose", "prev_close_price", "yesterdayClose", "previous_close_price",
        "prev_close_val", "previous_close_val", "yesterday_close"
    ]

    last_hist_df = None
    for idx, row in df.iterrows():
        token = row.get("token")
        symbol = row.get("symbol")
        prev_close_from_quote = None
        try:
            quote_resp = client.get_quotes(exchange="NSE", token=token)
            if isinstance(quote_resp, dict):
                ltp_val = (quote_resp.get("ltp") or quote_resp.get("last_price") or
                           quote_resp.get("lastTradedPrice") or quote_resp.get("lastPrice") or quote_resp.get("ltpPrice"))
                for k in POSSIBLE_PREV_KEYS:
                    if k in quote_resp and quote_resp.get(k) not in (None, "", []):
                        try:
                            prev_close_from_quote = float(quote_resp.get(k))
                            break
                        except Exception:
                            try:
                                prev_close_from_quote = float(str(quote_resp.get(k)).replace(",", ""))
                                break
                            except Exception:
                                prev_close_from_quote = None
                try:
                    ltp = float(ltp_val or 0.0)
                except Exception:
                    ltp = 0.0
            else:
                ltp = 0.0
                prev_close_from_quote = None
        except Exception:
            ltp = 0.0
            prev_close_from_quote = None

        ltp_list.append(ltp)
        prev_close = prev_close_from_quote if prev_close_from_quote is not None else ltp
        prev_source = "quote" if prev_close_from_quote is not None else None

        if prev_close_from_quote is None:
            try:
                from_date = (today_dt - timedelta(days=30)).strftime("%d%m%Y%H%M")
                to_date = today_dt.strftime("%d%m%Y%H%M")
                hist_csv = client.historical_csv(segment="NSE", token=token, timeframe="day", frm=from_date, to=to_date)

                hist_df, err = parse_historical_csv(hist_csv)
                if hist_df is None:
                    raise Exception(f"parse_historical_csv failed: {err}")

                # store for sample view
                last_hist_df = hist_df.copy()

                # ensure Close exists
                if "Close" not in hist_df.columns:
                    raise Exception("No Close column detected in historical data")

                # make sure DateTime is timezone-naive python datetime
                hist_df = hist_df.sort_values(by="DateTime").reset_index(drop=True)
                # find most recent trading date strictly before today
                hist_df["date_only"] = hist_df["DateTime"].dt.date
                prev_dates = [d for d in sorted(hist_df["date_only"].unique()) if d < today_date]
                if prev_dates:
                    prev_trading_date = prev_dates[-1]
                    prev_rows = hist_df[hist_df["date_only"] == prev_trading_date]
                    prev_close_val = prev_rows.iloc[-1].get("Close")
                    prev_close = float(prev_close_val)
                else:
                    # fallback to last available close in file
                    prev_close = float(hist_df.iloc[-1]["Close"])
                prev_source = "historical_csv"
            except Exception as exc:
                # fallback: keep prev_close as ltp (already set), mark source
                prev_close = prev_close if prev_close is not None else ltp
                prev_source = f"fallback:{str(exc)[:120]}"

        prev_close_list.append(prev_close)
        prev_source_list.append(prev_source)

    df["ltp"] = ltp_list
    df["prev_close"] = prev_close_list
    df["prev_close_source"] = prev_source_list

except Exception as e:
    st.error(f"⚠️ Error fetching holdings or prices: {e}")
    st.text(traceback.format_exc())
    st.stop()

# ------------------ Final historical sample display (optional) ------------------
try:
    if last_hist_df is not None and last_hist_df.shape[0] > 0:
        st.write("Historical data sample (last fetched symbol):")
        st.dataframe(last_hist_df.head())
except Exception:
    pass

# ------------------ Calculate P&L and other metrics ------------------
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
total_initial_risk = df["initial_risk"].sum()
total_open_risk = df["open_risk"].sum()
total_realized_if_all_tsl = df["realized_if_tsl_hit"].sum()

# ------------------ Display KPIs ------------------
st.subheader("💰 Overall Summary")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Invested", f"₹{total_invested:,.2f}")
k2.metric("Total Current", f"₹{total_current:,.2f}")
k3.metric("Overall Unrealized PnL", f"₹{total_overall_pnl:,.2f}")
k4.metric("Today PnL", f"₹{total_today_pnl:,.2f}")
k5.metric("Total Open Risk (TSL)", f"₹{total_open_risk:,.2f}")

# ------------------ Messaging about open risk ------------------
total_positions = len(df)
breakeven_count = int((df["open_risk"] == 0).sum())
profitable_by_ltp = int((df["ltp"] > df["avg_buy_price"]).sum())

if breakeven_count == total_positions:
    st.success(f"✅ All {total_positions} positions have TSL >= AvgBuy (no open risk). {profitable_by_ltp} of them currently show unrealized profit by LTP.")
else:
    st.info(f"ℹ️ {breakeven_count}/{total_positions} positions have no open risk (TSL >= AvgBuy). {profitable_by_ltp} positions currently showing unrealized profit by LTP.")
    risky = df[df["open_risk"] > 0].sort_values(by="open_risk", ascending=False).head(10)
    if not risky.empty:
        st.table(risky[["symbol", "quantity", "avg_buy_price", "ltp", "tsl_price", "open_risk"]])

# ------------------ Scenario analysis ------------------
st.subheader("🔮 Scenario: If ALL TSL get hit (immediate exit at current TSL)")
st.write("This assumes each position is closed at its calculated TSL price. For LONGs, PnL = (TSL - AvgBuy) * Qty. For SHORTs, PnL = (AvgBuy - TSL) * Qty.")

st.metric("Total Realized if all TSL hit", f"₹{total_realized_if_all_tsl:,.2f}")
delta_vs_unrealized = total_realized_if_all_tsl - total_overall_pnl
st.metric("Delta vs Current Unrealized PnL", f"₹{delta_vs_unrealized:,.2f}")
st.write(f"That is {total_realized_if_all_tsl/capital*100:.2f}% of your total capital.")

# Breakdown of winners/losers
df["realized_if_tsl_sign"] = df["realized_if_tsl_hit"].apply(lambda x: "profit" if x > 0 else ("loss" if x < 0 else "breakeven"))
winners = df[df["realized_if_tsl_hit"] > 0]
losers = df[df["realized_if_tsl_hit"] < 0]
breakevens = df[df["realized_if_tsl_hit"] == 0]

st.write(f"Winners: {len(winners)}, Losers: {len(losers)}, Breakeven: {len(breakevens)}")
if not winners.empty:
    st.table(winners[["symbol", "quantity", "avg_buy_price", "tsl_price", "realized_if_tsl_hit"]].sort_values(by="realized_if_tsl_hit", ascending=False).head(10))
if not losers.empty:
    st.table(losers[["symbol", "quantity", "avg_buy_price", "tsl_price", "realized_if_tsl_hit"]].sort_values(by="realized_if_tsl_hit").head(10))

# ------------------ Positions & Risk Table ------------------
display_cols = ["symbol", "quantity", "side", "avg_buy_price", "ltp", "prev_close", "prev_close_source", "invested_value", "current_value", "overall_pnl", "today_pnl",
                "capital_allocation_%", "initial_sl_price", "tsl_price", "initial_risk", "open_risk", "realized_if_tsl_hit"]
for i in range(1, len(target_pcts) + 1):
    display_cols += [f"target_{i}_pct", f"target_{i}_price"]

st.subheader("📋 Positions & Risk Table")
st.dataframe(df[display_cols].sort_values(by="capital_allocation_%", ascending=False).reset_index(drop=True), use_container_width=True)

# ------------------ Visuals ------------------
st.subheader("📊 Capital Allocation & Risk Visuals")
pie_df = df[["symbol", "capital_allocation_%"]].copy()
cash_pct = max(0.0, 100 - pie_df["capital_allocation_%"].sum())
pie_df = pd.concat([pie_df, pd.DataFrame([{"symbol": "Cash", "capital_allocation_%": cash_pct}])], ignore_index=True)
fig = go.Figure(data=[go.Pie(labels=pie_df["symbol"], values=pie_df["capital_allocation_%"], hole=0.35)])
fig.update_traces(textinfo='label+percent')
st.plotly_chart(fig, use_container_width=True)

st.subheader("⚠️ Risk Exposure by Position (Initial Risk % of Capital)")
risk_df = df[["symbol", "initial_risk"]].copy()
risk_df["initial_risk_pct_of_capital"] = (risk_df["initial_risk"] / capital) * 100
fig2 = go.Figure(data=[go.Bar(x=risk_df["symbol"], y=risk_df["initial_risk_pct_of_capital"])] )
fig2.update_layout(yaxis_title="% of Capital", xaxis_title="Symbol")
st.plotly_chart(fig2, use_container_width=True)

# ------------------ Per-symbol expanders & actions ------------------
st.subheader("🔍 Per-symbol details & actions")
for idx, row in df.sort_values(by="capital_allocation_%", ascending=False).iterrows():
    with st.expander(f"{row['symbol']} — Qty: {row['quantity']} | Invested: ₹{row['invested_value']:.0f}"):
        st.write(row[[c for c in display_cols if c in row.index]].to_frame().T)
        st.write("**Targets (price)**:", row["targets"])
        st.write("**Potential realized if TSL hit (₹)**:", row["realized_if_tsl_hit"])

        if show_actions and row['side'] in ["LONG", "SHORT"]:
            cols = st.columns(3)
            if cols[0].button(f"Square-off {row['symbol']}", key=f"sq_{row['symbol']}"):
                try:
                    payload = {
                        "exchange": "NSE",
                        "tradingsymbol": row['symbol'],
                        "quantity": int(abs(row['quantity'])),
                        "product_type": "INTRADAY",
                        "order_type": "SELL" if row['side']=="LONG" else "BUY"
                    }
                    resp = client.square_off_position(payload)
                    st.write("🔎 Square-off API Response:", resp)
                    if resp.get("status") == "SUCCESS":
                        st.success("Square-off placed successfully")
                    else:
                        st.error("Square-off failed: " + str(resp))
                except Exception as e:
                    st.error(f"Square-off failed: {e}")
                    st.text(traceback.format_exc())

            if cols[1].button(f"Place SL Order @ TSL ({row['tsl_price']})", key=f"sl_{row['symbol']}"):
                try:
                    payload = {
                        "exchange": "NSE",
                        "tradingsymbol": row['symbol'],
                        "quantity": int(abs(row['quantity'])),
                        "price_type": "SL-LIMIT",
                        "price": float(row['tsl_price']),
                        "product_type": "INTRADAY",
                        "order_type": "SELL" if row['side']=="LONG" else "BUY"
                    }
                    resp = client.place_order(payload)
                    st.write("🔎 Place SL API Response:", resp)
                    if resp.get("status") == "SUCCESS":
                        st.success("SL order placed successfully")
                    else:
                        st.error("SL placement failed: " + str(resp))
                except Exception as e:
                    st.error(f"SL placement failed: {e}")
                    st.text(traceback.format_exc())

            if cols[2].button(f"Modify SL to initial ({row['initial_sl_price']})", key=f"modsl_{row['symbol']}"):
                st.info("Modify SL functionality depends on existing order_id. Use Orders page to modify specific orders.")

# ------------------ Export ------------------
st.subheader("📥 Export")
csv_bytes = df.to_csv(index=False).encode('utf-8')
st.download_button("Download positions with risk data (CSV)", csv_bytes, file_name="positions_risk.csv", mime="text/csv")
