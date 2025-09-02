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
        avg_buy_price = float(item.get("avg_buy_price") or 0)
        dp_qty = float(item.get("dp_qty") or 0)
        t1_qty = float(item.get("t1_qty") or 0)
        holding_used = float(item.get("holding_used") or 0)
        total_qty = int(dp_qty + t1_qty + holding_used)

        for sym in item.get("tradingsymbol", []):
            if sym.get("exchange") != "NSE":
                continue
            rows.append({
                "symbol": sym.get("tradingsymbol"),
                "token": sym.get("token"),
                "avg_buy_price": avg_buy_price,
                "quantity": total_qty,
                "product_type": item.get("product_type", "")
            })

    if not rows:
        st.warning("⚠️ No NSE holdings found.")
        st.stop()

    df = pd.DataFrame(rows)

    # ------------------ Function 1: Fetch LTP ------------------
def fetch_ltp(client, token):
    """Fetch live LTP from quotes API."""
    try:
        quote_resp = client.get_quotes(exchange="NSE", token=token)
        if isinstance(quote_resp, dict):
            ltp_val = (
                quote_resp.get("ltp")
                or quote_resp.get("last_price")
                or quote_resp.get("lastTradedPrice")
            )
        else:
            ltp_val = None
        return float(ltp_val or 0.0)
    except Exception:
        return 0.0


# ------------------ Function 2: Fetch Previous Close ------------------
def fetch_prev_close(client, token, today_dt=None):
    """Fetch previous close (yesterday's close price)."""
    if today_dt is None:
        today_dt = datetime.now()

    try:
        # Yesterday’s date string
        yesterday = today_dt.date() - timedelta(days=1)
        date_str = yesterday.strftime("%Y%m%d")

        from_time = f"{date_str}0000"
        to_time = f"{date_str}1530"

        # Get historical CSV (daily data)
        hist_csv = client.historical_csv(
            segment="NSE",
            token=token,
            timeframe="day",
            frm=from_time,
            to=to_time,
        )

        if not isinstance(hist_csv, str):
            hist_csv = str(hist_csv)

        hist_df = pd.read_csv(io.StringIO(hist_csv), header=None)

        if hist_df.empty:
            return 0.0

        # Definedge format -> usually [date, open, high, low, close, volume]
        prev_close_val = hist_df.iloc[-1, 4]  # column index 4 = Close
        return float(prev_close_val)
    except Exception:
        return 0.0


    # ------------------ Usage Example ------------------
    st.info("Fetching live prices and previous close (robust logic).")
    ltp_list, prev_close_list = [], []
    today_dt = datetime.now()

    for idx, row in df.iterrows():
        token = row.get("token")
        ltp = fetch_ltp(client, token)
        prev_close = fetch_prev_close(client, token, today_dt)

        ltp_list.append(ltp)
        prev_close_list.append(prev_close)

    df["ltp"] = ltp_list
    df["prev_close"] = prev_close_list

    # ------------------ Basic P&L + allocation ------------------
    df["invested_value"] = df["avg_buy_price"] * df["quantity"]
    df["current_value"] = df["ltp"] * df["quantity"]
    df["today_pnl"] = (df["ltp"] - df["prev_close"]) * df["quantity"]
    df["overall_pnl"] = df["current_value"] - df["invested_value"]
    df["capital_allocation_%"] = (df["invested_value"] / capital) * 100

    # ------------------ Risk & TSL / Targets calculations ------------------
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

            # percent movement from avg to LTP
            perc = (ltp / avg - 1) if avg > 0 else 0.0

            # find highest threshold crossed
            crossed_indices = [i for i, th in enumerate(trailing_thresholds) if perc >= th]
            if crossed_indices:
                idx_max = max(crossed_indices)
                # mapping: if idx_max == 0 => tsl_pct = 0 (breakeven)
                tsl_pct = 0.0 if idx_max == 0 else trailing_thresholds[idx_max - 1]
                tsl_price = round(avg * (1 + tsl_pct), 4)
            else:
                tsl_price = initial_sl_price

            # ensure TSL never below initial SL
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

            # percent movement in favour of short = (avg - ltp)/avg
            perc = ((avg_abs - ltp) / avg_abs) if avg_abs > 0 else 0.0
            crossed_indices = [i for i, th in enumerate(trailing_thresholds) if perc >= th]
            if crossed_indices:
                idx_max = max(crossed_indices)
                tsl_pct_down = 0.0 if idx_max == 0 else trailing_thresholds[idx_max - 1]
                tsl_price = round(avg_abs * (1 - tsl_pct_down), 4)
            else:
                tsl_price = initial_sl_price

            # for short open risk is (tsl - avg) * abs(qty)
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

    results = df.apply(calc_stops_targets, axis=1, result_type="expand")
    # results is a DataFrame with keys same as dict keys
    df = pd.concat([df, results], axis=1)

    # explode targets into columns
    for i, tp in enumerate(target_pcts, start=1):
        df[f"target_{i}_pct"] = tp * 100
        df[f"target_{i}_price"] = df["targets"].apply(lambda lst: round(lst[i-1], 4) if isinstance(lst, list) and len(lst) >= i else 0.0)

    # ------------------ Portfolio metrics ------------------
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

    # ------------------ Intelligent Messaging about Open Risk / Breakeven ------------------
    total_positions = len(df)
    breakeven_count = int((df["open_risk"] == 0).sum())
    profitable_by_ltp = int((df["ltp"] > df["avg_buy_price"]).sum())

    if breakeven_count == total_positions:
        st.success(f"✅ All {total_positions} positions have TSL >= AvgBuy (no open risk). {profitable_by_ltp} of them currently show unrealized profit by LTP.")
    else:
        st.info(f"ℹ️ {breakeven_count}/{total_positions} positions have no open risk (TSL >= AvgBuy). {profitable_by_ltp} positions currently showing unrealized profit by LTP.")
        # show top few that still have open risk
        risky = df[df["open_risk"] > 0].sort_values(by="open_risk", ascending=False).head(10)
        if not risky.empty:
            st.table(risky[["symbol", "quantity", "avg_buy_price", "ltp", "tsl_price", "open_risk"]])

    # ------------------ If ALL TSL are hit: compute realized PnL scenario ------------------
    st.subheader("🔮 Scenario: If ALL TSL get hit (immediate exit at current TSL)")
    st.write("This assumes each position is closed at its calculated TSL price. For LONGs, PnL = (TSL - AvgBuy) * Qty. For SHORTs, PnL = (AvgBuy - TSL) * Qty.")

    st.metric("Total Realized if all TSL hit", f"₹{total_realized_if_all_tsl:,.2f}")
    delta_vs_unrealized = total_realized_if_all_tsl - total_overall_pnl
    st.metric("Delta vs Current Unrealized PnL", f"₹{delta_vs_unrealized:,.2f}")
    st.write(f"That is {total_realized_if_all_tsl/capital*100:.2f}% of your total capital.")

    # show breakdown of winners/losers under the scenario
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
    display_cols = ["symbol", "quantity", "side", "avg_buy_price", "ltp", "invested_value", "current_value", "overall_pnl", "today_pnl",
                    "capital_allocation_%", "initial_sl_price", "tsl_price", "initial_risk", "open_risk", "realized_if_tsl_hit"]
    # add target columns
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
    fig2 = go.Figure(data=[go.Bar(x=risk_df["symbol"], y=risk_df["initial_risk_pct_of_capital"])])
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

except Exception as e:
    st.error(f"⚠️ Dashboard fetch failed: {e}")
    st.text(traceback.format_exc())

st.caption("Notes:\n- Prev close is chosen using a robust 'last full trading day' logic to avoid using an incomplete current-day candle.\n- TSL mapping: when LTP crosses the first threshold (e.g. 10%) TSL -> breakeven; next threshold moves TSL to AvgBuy + previous threshold, etc.\n- If Total Open Risk == 0 then TSL >= AvgBuy for all positions (no downside left in the portfolio under current TSL).\n- The 'If ALL TSL hit' scenario computes realized P/L assuming immediate exit at each position's calculated TSL.")
