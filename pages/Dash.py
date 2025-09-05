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
def parse_definedge_csv_text(csv_text: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(io.StringIO(csv_text), header=None, names=["Date", "Symbol", "EntryPrice", "SLPrice", "TargetPrice", "ExitPrice", "Profit/Loss", "Quantity"])
        df['Date'] = pd.to_datetime(df['Date'])
        df['Profit/Loss'] = pd.to_numeric(df['Profit/Loss'], errors='coerce')
        df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Error parsing CSV: {e}")
        return pd.DataFrame()

# ------------------ Helper: get robust previous close ------------------
def get_robust_prev_close_from_hist(hist_df: pd.DataFrame, today_date: date):
    """
    Given a parsed historical DataFrame with 'DateTime' and 'Close',
    return (prev_close_value_or_None, reason_string).
    """
    try:
        if "DateTime" not in hist_df.columns or "Close" not in hist_df.columns:
            return None, "Missing required columns"

        df = hist_df.dropna(subset=["DateTime", "Close"]).copy()
        if df.empty:
            return None, "No valid data"

        df['date_only'] = df["DateTime"].dt.date
        df['Close_numeric'] = pd.to_numeric(df["Close"], errors='coerce')

        # 1) Find most recent trading date before today
        prev_dates = [d for d in sorted(df['date_only'].unique()) if d < today_date]
        if prev_dates:
            prev_trading_date = prev_dates[-1]
            prev_rows = df[df['date_only'] == prev_trading_date].sort_values("DateTime")
            val = prev_rows["Close_numeric"].dropna().iloc[-1]
            return float(val), "prev_trading_date"

        # 2) Deduplicate Close sequence
        closes_series = df["Close_numeric"].dropna().tolist()
        if not closes_series:
            return None, "No numeric closes"

        seen = set()
        dedup = []
        for v in closes_series:
            if v not in seen:
                dedup.append(v)
                seen.add(v)
        if len(dedup) >= 2:
            return float(dedup[-2]), "dedup_second_last"
        else:
            return float(closes_series[-1]), "last_available"
    except Exception as exc:
        return None, f"error:{str(exc)[:120]}"

# ------------------ Main code ------------------

# Placeholder for client - replace with your actual API client
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

# Sidebar inputs
st.sidebar.header("⚙️ Dashboard Settings & Risk")
capital = st.sidebar.number_input("Total Capital (₹)", value=DEFAULT_TOTAL_CAPITAL, step=10000, key="capital_input")
initial_sl_pct = st.sidebar.number_input("Initial Stop Loss (%)", value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1, key="initial_sl_input")/100
targets_input = st.sidebar.text_input("Targets % (comma separated)", ",".join(map(str, DEFAULT_TARGETS)), key="targets_input")
try:
    target_pcts = sorted([max(0.0, float(t.strip())/100.0) for t in targets_input.split(",") if t.strip()])
    if not target_pcts:
        target_pcts = [t/100.0 for t in DEFAULT_TARGETS]
except:
    st.sidebar.error("Invalid Targets input — using defaults")
    target_pcts = [t/100.0 for t in DEFAULT_TARGETS]

trailing_thresholds = target_pcts
auto_refresh = st.sidebar.checkbox("Auto-refresh LTP on page interaction", value=False, key="auto_refresh")
show_actions = st.sidebar.checkbox("Show Action Buttons (Square-off / Place SL)", value=False, key="show_actions")
st.sidebar.markdown("---")

# Fetch holdings
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
        try:
            avg_buy_price = float(item.get("avg_buy_price") or 0)
        except:
            avg_buy_price = 0.0
        try:
            dp_qty = float(item.get("dp_qty") or 0)
        except:
            dp_qty = 0.0
        try:
            t1_qty = float(item.get("t1_qty") or 0)
        except:
            t1_qty = 0.0
        try:
            holding_used = float(item.get("holding_used") or 0)
        except:
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

    df = pd.DataFrame(rows).dropna(subset=["symbol"]).reset_index(drop=True)

    # Fetch LTP + previous close
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
        ltp = 0.0

        # Get live quote
        try:
            quote_resp = client.get_quotes(exchange="NSE", token=token)
            if isinstance(quote_resp, dict):
                ltp_val = (quote_resp.get("ltp") or quote_resp.get("last_price") or
                           quote_resp.get("lastTradedPrice") or quote_resp.get("lastPrice") or quote_resp.get("ltpPrice"))
                try:
                    ltp = float(ltp_val or 0.0)
                except:
                    ltp = 0.0
                # Check for prev_close in quote
                for k in POSSIBLE_PREV_KEYS:
                    if k in quote_resp and quote_resp.get(k) not in (None, "", []):
                        try:
                            prev_close_from_quote = float(str(quote_resp.get(k)).replace(",", ""))
                            break
                        except:
                            prev_close_from_quote = None
        except:
            prev_close_from_quote = None
            # ltp remains 0.0 if error

        # Fall back to historical data
        if prev_close_from_quote is None:
            try:
                from_date = (today_dt - timedelta(days=30)).strftime("%d%m%Y%H%M")
                to_date = today_dt.strftime("%d%m%Y%H%M")
                hist_csv = client.historical_csv(segment="NSE", token=token, timeframe="day", frm=from_date, to=to_date)
                hist_df, err = parse_definedge_csv_text(hist_csv)
                if hist_df is None:
                    raise Exception(f"Parsing error: {err}")
                last_hist_df = hist_df.copy()

                prev_close_val, reason = get_robust_prev_close_from_hist(hist_df, today_date)
                if prev_close_val is not None:
                    prev_close = float(prev_close_val)
                    prev_source = f"historical_csv:{reason}"
                else:
                    prev_close = float(ltp or 0.0)
                    prev_source = f"historical_fallback:{reason}"
            except Exception as exc:
                prev_close = float(ltp or 0.0)
                prev_source = f"fallback_error:{str(exc)[:120]}"
        else:
            prev_close = prev_close_from_quote
            prev_source = "quote"

        ltp_list.append(ltp)
        prev_close_list.append(prev_close)
        prev_source_list.append(prev_source)

except Exception as e:
    st.error(f"⚠️ Error fetching holdings or prices: {e}")
    st.text(traceback.format_exc())
    st.stop()

# Optional: show last fetched historical data
try:
    if last_hist_df is not None and last_hist_df.shape[0] > 0:
        st.write("Historical data sample (last fetched symbol):")
        st.dataframe(last_hist_df.head())
except:
    pass

# Calculate P&L, invested, current, etc.
for col in ["avg_buy_price", "quantity", "ltp", "prev_close"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

# Calculate invested_value
df["invested_value"] = df["avg_buy_price"] * df["quantity"]

# Check for 'ltp'
if 'ltp' in df.columns:
    df["current_value"] = df["ltp"] * df["quantity"]
    df["today_pnl"] = (df["ltp"] - df["prev_close"]) * df["quantity"]
else:
    st.error("LTP column missing. Cannot compute current value or today's P&L.")
    df["current_value"] = 0
    df["today_pnl"] = 0

# Calculate overall P&L
df["overall_pnl"] = df["current_value"] - df["invested_value"]
# Capital allocation
df["capital_allocation_%"] = (df["invested_value"] / capital) * 100

# ------------------ Calculate stops and targets ------------------
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

# Apply stops/targets to DataFrame
results = df.apply(calc_stops_targets, axis=1, result_type="expand")
df = pd.concat([df, results], axis=1)

# Explode targets into columns
for i, tp in enumerate(target_pcts, start=1):
    df[f"target_{i}_pct"] = tp * 100
    df[f"target_{i}_price"] = df["targets"].apply(lambda lst: round(lst[i-1], 4) if isinstance(lst, list) and len(lst) >= i else 0.0)

# Portfolio KPIs
total_invested = df["invested_value"].sum()
total_current = df["current_value"].sum()
total_overall_pnl = df["overall_pnl"].sum()
total_today_pnl = df["today_pnl"].sum()
total_initial_risk = df["initial_risk"].sum()
total_open_risk = df["open_risk"].sum()
total_realized_if_all_tsl = df["realized_if_tsl_hit"].sum()

# Display KPIs
st.subheader("💰 Overall Summary")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Invested", f"₹{total_invested:,.2f}")
k2.metric("Total Current", f"₹{total_current:,.2f}")
k3.metric("Unrealized PnL", f"₹{total_overall_pnl:,.2f}")
k4.metric("Today PnL", f"₹{total_today_pnl:,.2f}")
k5.metric("Open Risk (TSL)", f"₹{total_open_risk:,.2f}")

# Messaging
total_positions = len(df)
breakeven_count = int((df["open_risk"] == 0).sum())
profitable_by_ltp = int((df["ltp"] > df["avg_buy_price"]).sum())

if breakeven_count == total_positions:
    st.success(f"✅ All {total_positions} positions have TSL >= AvgBuy (no open risk). {profitable_by_ltp} currently profitable.")
else:
    st.info(f"ℹ️ {breakeven_count}/{total_positions} positions have no open risk. {profitable_by_ltp} profitable by LTP.")
    risky = df[df["open_risk"] > 0].sort_values(by="open_risk", ascending=False).head(10)
    if not risky.empty:
        st.table(risky[["symbol", "quantity", "avg_buy_price", "ltp", "tsl_price", "open_risk"]])

# Scenario analysis
st.subheader("🔮 Scenario: If ALL TSL get hit")
st.write("Assuming each position is closed at its TSL price.")
st.metric("Total if TSL hit", f"₹{total_realized_if_all_tsl:,.2f}")
delta = total_realized_if_all_tsl - total_overall_pnl
st.metric("Delta vs Unrealized", f"₹{delta:,.2f}")
st.write(f"That is {total_realized_if_all_tsl/capital*100:.2f}% of total capital.")

# Winners and Losers
df["realized_if_tsl_sign"] = df["realized_if_tsl_hit"].apply(lambda x: "profit" if x > 0 else ("loss" if x < 0 else "breakeven"))
winners = df[df["realized_if_tsl_hit"] > 0]
losers = df[df["realized_if_tsl_hit"] < 0]
breakevens = df[df["realized_if_tsl_hit"] == 0]

st.write(f"Winners: {len(winners)}, Losers: {len(losers)}, Breakeven: {len(breakevens)}")
if not winners.empty:
    st.table(winners[["symbol", "quantity", "avg_buy_price", "tsl_price", "realized_if_tsl_hit"]].sort_values(by="realized_if_tsl_hit", ascending=False).head(10))
if not losers.empty:
    st.table(losers[["symbol", "quantity", "avg_buy_price", "tsl_price", "realized_if_tsl_hit"]].sort_values(by="realized_if_tsl_hit").head(10))

# Positions & risk table
display_cols = ["symbol", "quantity", "side", "avg_buy_price", "ltp", "prev_close", "prev_close_source", "invested_value", "current_value", "overall_pnl", "today_pnl",
                "capital_allocation_%", "initial_sl_price", "tsl_price", "initial_risk", "open_risk", "realized_if_tsl_hit"]
for i in range(1, len(target_pcts) + 1):
    display_cols += [f"target_{i}_pct", f"target_{i}_price"]

st.subheader("📋 Positions & Risk Table")
st.dataframe(df[display_cols].sort_values(by="capital_allocation_%", ascending=False).reset_index(drop=True), use_container_width=True)

# Visuals
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
fig2 = go.Figure(data=[go.Bar(x=risk_df["symbol"], y=risk_df["initial_risk_pct_of_capital"])])
fig2.update_layout(yaxis_title="% of Capital", xaxis_title="Symbol")
st.plotly_chart(fig2, use_container_width=True)

# Per-symbol expanders & actions
st.subheader("🔍 Per-symbol details & actions")
for idx, row in df.sort_values(by="capital_allocation_%", ascending=False).iterrows():
    key_base = f"{row['symbol']}_{idx}"
    with st.expander(f"{row['symbol']} — Qty: {row['quantity']} | Invested: ₹{row['invested_value']:.0f}"):
        st.write(row[display_cols].to_frame().T)
        st.write("**Targets (price):**", row["targets"])
        st.write("**Potential profit/loss if TSL hit (₹):**", row["realized_if_tsl_hit"])

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

# Export
st.subheader("📥 Export")
csv_bytes = df.to_csv(index=False).encode('utf-8')
st.download_button("Download positions with risk data (CSV)", csv_bytes, file_name="positions_risk.csv", mime="text/csv")
