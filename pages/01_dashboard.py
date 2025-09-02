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

# ------------------ Helper: parse Definedge CSV (headerless) ------------------
def parse_definedge_csv(raw_text, timeframe="day"):
    if raw_text is None:
        return None, "empty response"

    if isinstance(raw_text, bytes):
        try:
            s = raw_text.decode("utf-8", "ignore")
        except Exception:
            s = str(raw_text)
    else:
        s = str(raw_text)

    s = s.strip()
    if not s:
        return None, "empty CSV"

    try:
        df = pd.read_csv(io.StringIO(s), header=None)
    except Exception as exc:
        return None, f"read_csv error: {exc}"

    if df.shape[0] == 0:
        return None, "no rows"

    if timeframe in ("day", "minute"):
        if df.shape[1] >= 6:
            colnames = ["DateTime", "Open", "High", "Low", "Close", "Volume"]
            if df.shape[1] >= 7:
                colnames = ["DateTime", "Open", "High", "Low", "Close", "Volume", "OI"]
            extras = []
            if df.shape[1] > len(colnames):
                extras = [f"X{i}" for i in range(df.shape[1] - len(colnames))]
            df.columns = colnames + extras
        else:
            df.columns = [f"C{i}" for i in range(df.shape[1])]
            df = df.rename(columns={df.columns[0]: "DateTime"})
    elif timeframe == "tick":
        if df.shape[1] >= 4:
            df.columns = ["UTC", "LTP", "LTQ", "OI"] + [f"X{i}" for i in range(df.shape[1] - 4)]
        else:
            df.columns = [f"C{i}" for i in range(df.shape[1])]
    else:
        df.columns = [f"C{i}" for i in range(df.shape[1])]

    try:
        if timeframe in ("day", "minute"):
            dt_series = None
            candidates = [
                "%d-%m-%Y %H:%M:%S",
                "%d-%m-%Y %H:%M",
                "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M"
            ]
            for fmt in candidates:
                try:
                    dt_series = pd.to_datetime(df["DateTime"], format=fmt, dayfirst=True, errors="coerce")
                    if dt_series.notna().sum() / max(1, len(dt_series)) >= 0.6:
                        break
                except Exception:
                    dt_series = None

            if dt_series is None:
                dt_series = pd.to_datetime(df["DateTime"], dayfirst=True, errors="coerce")

            df["DateTime"] = dt_series
            for c in ["Open", "High", "Low", "Close", "Volume", "OI"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
        elif timeframe == "tick":
            df["UTC"] = pd.to_numeric(df["UTC"], errors="coerce")
            df["DateTime"] = pd.to_datetime(df["UTC"], unit="s", errors="coerce")
            if "LTP" in df.columns:
                df["LTP"] = pd.to_numeric(df["LTP"], errors="coerce")
            if "LTQ" in df.columns:
                df["LTQ"] = pd.to_numeric(df["LTQ"], errors="coerce")
        else:
            if "DateTime" in df.columns:
                df["DateTime"] = pd.to_datetime(df["DateTime"], dayfirst=True, errors="coerce")
    except Exception as exc:
        return None, f"datetime parse error: {exc}"

    if "DateTime" not in df.columns or df["DateTime"].isna().all():
        return None, "DateTime parse failed (all NaT)"

    df = df.sort_values("DateTime").reset_index(drop=True)
    return df, None


# ------------------ Robust prev-close helper (fixed) ------------------
def get_robust_prev_close_from_hist(hist_df: pd.DataFrame, today_date: date):
    """
    Pick prev close from yesterday (<= today - 1).
    """
    try:
        if "DateTime" not in hist_df.columns or "Close" not in hist_df.columns:
            return None, "missing DateTime/Close"

        df = hist_df.dropna(subset=["DateTime", "Close"]).copy()
        if df.empty:
            return None, "no valid rows"

        df["date_only"] = df["DateTime"].dt.date
        df["Close_numeric"] = pd.to_numeric(df["Close"], errors="coerce")

        yesterday = today_date - timedelta(days=1)
        candidates = df[df["date_only"] <= yesterday]

        if not candidates.empty:
            last_row = candidates.sort_values("DateTime").iloc[-1]
            return float(last_row["Close_numeric"]), "yesterday_or_latest_before"

        last_row = df.sort_values("DateTime").iloc[-1]
        return float(last_row["Close_numeric"]), "fallback_last"
    except Exception as exc:
        return None, f"error:{str(exc)[:120]}"


# ------------------ Client check ------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

# ------------------ Sidebar ------------------
st.sidebar.header("⚙️ Dashboard Settings & Risk")
capital = st.sidebar.number_input("Total Capital (₹)", value=DEFAULT_TOTAL_CAPITAL, step=10000)
initial_sl_pct = st.sidebar.number_input("Initial Stop Loss (%)", value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1) / 100
targets_input = st.sidebar.text_input("Targets % (comma separated)", ",".join(map(str, DEFAULT_TARGETS)))

try:
    target_pcts = sorted([max(0.0, float(t.strip()) / 100.0) for t in targets_input.split(",") if t.strip()])
    if not target_pcts:
        target_pcts = [t / 100.0 for t in DEFAULT_TARGETS]
except Exception:
    st.sidebar.error("Invalid Targets input — using defaults")
    target_pcts = [t / 100.0 for t in DEFAULT_TARGETS]

trailing_thresholds = target_pcts
auto_refresh = st.sidebar.checkbox("Auto-refresh LTP", value=False)
show_actions = st.sidebar.checkbox("Show Action Buttons", value=False)
st.sidebar.markdown("---")

# ------------------ Fetch holdings ------------------
try:
    holdings_resp = client.get_holdings()
    if not holdings_resp or holdings_resp.get("status") != "SUCCESS":
        st.warning("⚠️ No holdings found or API error")
        st.stop()

    holdings = holdings_resp.get("data", [])
    if not holdings:
        st.info("✅ No holdings found.")
        st.stop()

    rows = []
    for item in holdings:
        avg_buy_price = float(item.get("avg_buy_price") or 0)
        dp_qty = float(item.get("dp_qty") or 0)
        t1_qty = float(item.get("t1_qty") or 0)
        holding_used = float(item.get("holding_used") or 0)
        total_qty = int(dp_qty + t1_qty + holding_used)

        tradings = item.get("tradingsymbol") or []
        if isinstance(tradings, str):
            rows.append({
                "symbol": tradings,
                "token": item.get("token"),
                "avg_buy_price": avg_buy_price,
                "quantity": total_qty,
                "product_type": item.get("product_type", "")
            })
        elif isinstance(tradings, list):
            for sym_obj in tradings:
                if sym_obj.get("exchange") != "NSE":
                    continue
                rows.append({
                    "symbol": sym_obj.get("tradingsymbol"),
                    "token": sym_obj.get("token"),
                    "avg_buy_price": avg_buy_price,
                    "quantity": total_qty,
                    "product_type": item.get("product_type", "")
                })

    if not rows:
        st.warning("⚠️ No NSE holdings found.")
        st.stop()

    df = pd.DataFrame(rows).dropna(subset=["symbol"]).reset_index(drop=True)

    st.info("Fetching live prices and previous close (robust logic).")
    ltp_list, prev_close_list, prev_source_list = [], [], []

    today_dt = datetime.now()
    today_date = today_dt.date()
    last_hist_df = None

    POSSIBLE_PREV_KEYS = [
        "prev_close", "previous_close", "previousClose", "previousClosePrice",
        "prevClose", "prevclose", "previousclose", "yesterdayClose"
    ]

    for idx, row in df.iterrows():
        token = row["token"]
        symbol = row["symbol"]
        prev_close_from_quote, ltp = None, 0.0

        try:
            quote_resp = client.get_quotes(exchange="NSE", token=token)
            if isinstance(quote_resp, dict):
                ltp_val = (quote_resp.get("ltp") or quote_resp.get("last_price"))
                ltp = float(ltp_val or 0.0)

                for k in POSSIBLE_PREV_KEYS:
                    if k in quote_resp and quote_resp.get(k):
                        prev_close_from_quote = float(str(quote_resp.get(k)).replace(",", ""))
                        break
        except Exception:
            pass

        if prev_close_from_quote is not None:
            prev_close, prev_source = prev_close_from_quote, "quote"
        else:
            try:
                from_date = (today_dt - timedelta(days=30)).strftime("%d%m%Y%H%M")
                to_date = today_dt.strftime("%d%m%Y%H%M")
                hist_csv = client.historical_csv(segment="NSE", token=token, timeframe="day", frm=from_date, to=to_date)

                hist_df, err = parse_definedge_csv(hist_csv, timeframe="day")
                if hist_df is None:
                    raise Exception(err)
                last_hist_df = hist_df.copy()

                prev_close_val, reason = get_robust_prev_close_from_hist(hist_df, today_date)
                if prev_close_val is not None:
                    prev_close, prev_source = float(prev_close_val), f"historical:{reason}"
                else:
                    prev_close, prev_source = float(ltp or 0.0), f"historical_fallback:{reason}"
            except Exception as exc:
                prev_close, prev_source = float(ltp or 0.0), f"error:{exc}"

        ltp_list.append(ltp)
        prev_close_list.append(prev_close)
        prev_source_list.append(prev_source)

    df["ltp"], df["prev_close"], df["prev_close_source"] = ltp_list, prev_close_list, prev_source_list

except Exception as e:
    st.error(f"⚠️ Error: {e}")
    st.text(traceback.format_exc())
    st.stop()

# ------------------ Further code (PnL, targets, visuals, etc.) ------------------
# (keep your same logic from here onwards unchanged)

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
    key_base = f"{row['symbol']}_{idx}"
    with st.expander(f"{row['symbol']} — Qty: {row['quantity']} | Invested: ₹{row['invested_value']:.0f}"):
        st.write(row[[c for c in display_cols if c in row.index]].to_frame().T)
        st.write("**Targets (price)**:", row["targets"])
        st.write("**Potential realized if TSL hit (₹)**:", row["realized_if_tsl_hit"])

        if show_actions and row['side'] in ["LONG", "SHORT"]:
            cols = st.columns(3)
            if cols[0].button(f"Square-off {row['symbol']}", key=f"sq_{key_base}"):
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

            if cols[1].button(f"Place SL Order @ TSL ({row['tsl_price']})", key=f"sl_{key_base}"):
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

            if cols[2].button(f"Modify SL to initial ({row['initial_sl_price']})", key=f"modsl_{key_base}"):
                st.info("Modify SL functionality depends on existing order_id. Use Orders page to modify specific orders.")

# ------------------ Export ------------------
st.subheader("📥 Export")
csv_bytes = df.to_csv(index=False).encode('utf-8')
st.download_button("Download positions with risk data (CSV)", csv_bytes, file_name="positions_risk.csv", mime="text/csv")
