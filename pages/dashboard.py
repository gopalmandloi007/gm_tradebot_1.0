import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, timedelta
import plotly.graph_objects as go
import traceback

# ------------------ User-configurable defaults ------------------
DEFAULT_TOTAL_CAPITAL = 1400000  # Default portfolio capital
DEFAULT_INITIAL_SL_PCT = 2.0     # Percent (2 means 2%)
DEFAULT_TARGETS = [10, 20, 30, 40]  # Targets in percent

# ------------------ Page header ------------------
st.set_page_config(layout="wide")
st.title("📊 Trading Dashboard — Definedge (Risk Managed)")

# ------------------ Client check ------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

# ------------------ Sidebar settings ------------------
st.sidebar.header("⚙️ Dashboard Settings & Risk")
capital = st.sidebar.number_input("Total Capital (₹)", value=DEFAULT_TOTAL_CAPITAL, step=10000)
initial_sl_pct = st.sidebar.number_input("Initial Stop Loss (%)", value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1)/100
targets_input = st.sidebar.text_input("Targets % (comma separated)", ",".join(map(str, DEFAULT_TARGETS)))
try:
    target_pcts = sorted([float(t.strip())/100 for t in targets_input.split(",") if t.strip()])
    if not target_pcts:
        target_pcts = [t/100 for t in DEFAULT_TARGETS]
except Exception:
    st.sidebar.error("Invalid Targets input — using defaults")
    target_pcts = [t/100 for t in DEFAULT_TARGETS]

# trailing thresholds will use the same target steps (10%,20%,...)
trailing_thresholds = target_pcts

auto_refresh = st.sidebar.checkbox("Auto-refresh LTP on page interaction (recommended)", value=False)
show_actions = st.sidebar.checkbox("Show Action Buttons (Square-off / Place SL)", value=False)

st.markdown("---")

# ------------------ Fetch holdings ------------------
try:
    holdings_resp = client.get_holdings()
    if not holdings_resp or holdings_resp.get("status") != "SUCCESS":
        st.warning("⚠️ No holdings found or API error.")
        st.stop()

    holdings = holdings_resp.get("data", [])
    if not holdings:
        st.info("✅ No holdings found.")
        st.stop()

    # Flatten holdings to rows (NSE only)
    rows = []
    for item in holdings:
        tradingsymbols = item.get("tradingsymbol", [])
        avg_buy_price = float(item.get("avg_buy_price", 0) or 0)
        dp_qty = float(item.get("dp_qty", 0) or 0)
        t1_qty = float(item.get("t1_qty", 0) or 0)
        holding_used = float(item.get("holding_used", 0) or 0)
        total_qty = int(dp_qty + t1_qty + holding_used)

        for sym in tradingsymbols:
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

    # ------------------ Fetch LTPs & optional prev_close ------------------
    st.info("Fetching live prices (LTP). This may take a moment for large holdings.")
    ltp_list = []
    prev_close_list = []
    today = datetime.today()

    for idx, row in df.iterrows():
        token = row.get("token")
        try:
            quote_resp = client.get_quotes(exchange="NSE", token=token)
            # try common keys
            ltp = None
            if isinstance(quote_resp, dict):
                ltp = quote_resp.get("ltp") or quote_resp.get("last_price") or quote_resp.get("lastTradedPrice")
            ltp = float(ltp or 0)
        except Exception:
            ltp = 0.0

        ltp_list.append(ltp)

        # prev_close: best-effort — if API/historical fails we put LTP as prev_close
        prev_close = ltp
        try:
            from_date = (today - timedelta(days=10)).strftime("%d%m%Y%H%M")
            to_date = today.strftime("%d%m%Y%H%M")
            hist_csv = client.historical_csv(segment="NSE", token=token, timeframe="day", frm=from_date, to=to_date)
            hist_df = pd.read_csv(io.StringIO(hist_csv), header=None)
            if hist_df.shape[1] >= 6:
                if hist_df.shape[1] == 7:
                    hist_df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume", "OI"]
                else:
                    hist_df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]
                hist_df["DateTime"] = pd.to_datetime(hist_df["DateTime"], dayfirst=True, errors='coerce')
                hist_df = hist_df.sort_values("DateTime")
                prev_close = float(hist_df.iloc[-2]["Close"]) if len(hist_df) >= 2 else float(hist_df.iloc[-1]["Close"]) if len(hist_df) >= 1 else ltp
        except Exception:
            prev_close = ltp

        prev_close_list.append(prev_close)

    df["ltp"] = ltp_list
    df["prev_close"] = prev_close_list

    # ------------------ Calculations: PnL, Targets, SLs, Risk ------------------
    df["invested_value"] = df["avg_buy_price"] * df["quantity"]
    df["current_value"] = df["ltp"] * df["quantity"]
    df["today_pnl"] = (df["ltp"] - df["prev_close"]) * df["quantity"]
    df["overall_pnl"] = df["current_value"] - df["invested_value"]
    df["capital_allocation_%"] = (df["invested_value"] / capital) * 100

    # initial stop price (long vs short)
    def calc_stops_targets(row):
        avg = float(row["avg_buy_price"]) if row["avg_buy_price"] is not None else 0.0
        qty = int(row["quantity"])
        ltp = float(row.get("ltp", 0.0))

        # identify side
        side = "FLAT"
        if qty > 0:
            side = "LONG"
        elif qty < 0:
            side = "SHORT"

        # long logic
        if side == "LONG":
            initial_sl_price = round(avg * (1 - initial_sl_pct), 4)

            # targets
            targets = [round(avg * (1 + t), 4) for t in target_pcts]

            # trailing logic - incremental steps based on thresholds
            perc = (ltp / avg - 1) if avg > 0 else 0
            satisfied = [t for t in trailing_thresholds if perc >= t]
            if satisfied:
                max_t = max(satisfied)
                tsl_pct = max_t - (trailing_thresholds[0] if len(trailing_thresholds) else 0.1)
                # formula ensures mapping: for thresholds [0.1,0.2,...] tsl_pct becomes [0,0.1,0.2,...]
                tsl_price = round(avg * (1 + max_t - trailing_thresholds[0]), 4)
                # Recompute using explicit mapping: tsl = avg*(1 + (max_t - 0.10))
                tsl_price = round(avg * (1 + (max_t - trailing_thresholds[0])), 4)
            else:
                tsl_price = initial_sl_price

            # ensure tsl never decreases below initial stop
            tsl_price = max(tsl_price, initial_sl_price)

            # open risk (based on TSL)
            open_risk = round(max(0.0, (avg - tsl_price) * qty), 2)
            initial_risk = round(max(0.0, (avg - initial_sl_price) * qty), 2)

            # potential gains at targets
            potential_gains = [round((tp - avg) * qty, 2) for tp in targets]

            return {
                "side": side,
                "initial_sl_price": initial_sl_price,
                "tsl_price": tsl_price,
                "targets": targets,
                "open_risk": open_risk,
                "initial_risk": initial_risk,
                "potential_gains": potential_gains
            }

        # short logic - mirror the calculations
        elif side == "SHORT":
            avg = abs(avg)
            initial_sl_price = round(avg * (1 + initial_sl_pct), 4)
            targets = [round(avg * (1 - t), 4) for t in target_pcts]

            perc = (avg / ltp - 1) if ltp > 0 else 0  # how much price has fallen from avg
            satisfied = [t for t in trailing_thresholds if perc >= t]
            if satisfied:
                max_t = max(satisfied)
                tsl_price = round(avg * (1 - (max_t - trailing_thresholds[0])), 4)
            else:
                tsl_price = initial_sl_price

            # for short, ensure tsl never moves in wrong direction
            # open risk for short is (tsl - avg) * abs(qty)
            open_risk = round(max(0.0, (tsl_price - avg) * abs(qty)), 2)
            initial_risk = round(max(0.0, (initial_sl_price - avg) * abs(qty)), 2)
            potential_gains = [round((avg - tp) * abs(qty), 2) for tp in targets]

            return {
                "side": side,
                "initial_sl_price": initial_sl_price,
                "tsl_price": tsl_price,
                "targets": targets,
                "open_risk": open_risk,
                "initial_risk": initial_risk,
                "potential_gains": potential_gains
            }

        else:
            return {
                "side": "FLAT",
                "initial_sl_price": 0,
                "tsl_price": 0,
                "targets": [0]*len(target_pcts),
                "open_risk": 0,
                "initial_risk": 0,
                "potential_gains": [0]*len(target_pcts)
            }

    calc_results = df.apply(calc_stops_targets, axis=1)

    df["side"] = calc_results.apply(lambda x: x["side"]) if not calc_results.empty else None
    df["initial_sl_price"] = calc_results.apply(lambda x: x["initial_sl_price"]) 
    df["tsl_price"] = calc_results.apply(lambda x: x["tsl_price"]) 
    df["initial_risk_amt"] = calc_results.apply(lambda x: x["initial_risk"]) 
    df["open_risk_amt"] = calc_results.apply(lambda x: x["open_risk"]) 
    df["targets_list"] = calc_results.apply(lambda x: x["targets"]) 
    df["potential_gains_list"] = calc_results.apply(lambda x: x["potential_gains"]) 

    # explode targets into separate columns for clarity
    for i, t in enumerate(target_pcts, start=1):
        df[f"target_{i}_pct"] = t * 100
        df[f"target_{i}_price"] = df["targets_list"].apply(lambda lst: round(lst[i-1], 4) if isinstance(lst, list) and len(lst) >= i else 0)
        df[f"gain_at_target_{i}"] = df["potential_gains_list"].apply(lambda lst: round(lst[i-1], 2) if isinstance(lst, list) and len(lst) >= i else 0)

    # ------------------ Portfolio level metrics ------------------
    total_invested = df["invested_value"].sum()
    total_current = df["current_value"].sum()
    total_overall_pnl = df["overall_pnl"].sum()
    total_today_pnl = df["today_pnl"].sum()
    total_initial_risk = df["initial_risk_amt"].sum()
    total_open_risk = df["open_risk_amt"].sum()

    # ------------------ Display Summary KPIs ------------------
    st.subheader("💰 Overall Summary")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Invested", f"₹{total_invested:,.2f}")
    k2.metric("Total Current", f"₹{total_current:,.2f}")
    k3.metric("Overall PnL", f"₹{total_overall_pnl:,.2f}")
    k4.metric("Today PnL", f"₹{total_today_pnl:,.2f}")
    k5.metric("Total Open Risk (TSL)", f"₹{total_open_risk:,.2f}")

    # ------------------ Display holdings table with risk columns ------------------
    display_cols = ["symbol", "quantity", "side", "avg_buy_price", "ltp", "invested_value", "current_value", "overall_pnl", "today_pnl",
                    "capital_allocation_%", "initial_sl_price", "tsl_price", "initial_risk_amt", "open_risk_amt"] + [f"target_{i}_pct" for i in range(1, len(target_pcts)+1)] + [f"target_{i}_price" for i in range(1, len(target_pcts)+1)] + [f"gain_at_target_{i}" for i in range(1, len(target_pcts)+1)]

    st.subheader("📋 Positions & Risk Table")
    st.dataframe(df[display_cols].sort_values(by="capital_allocation_%", ascending=False).reset_index(drop=True), use_container_width=True)

    # ------------------ Capital allocation pie (and cash) ------------------
    st.subheader("📊 Capital Allocation & Risk")
    pie_df = df[["symbol", "capital_allocation_%"]].copy()
    cash_pct = max(0.0, 100 - pie_df["capital_allocation_%"].sum())
    cash_row = pd.DataFrame([{"symbol": "Cash", "capital_allocation_%": cash_pct}])
    pie_df = pd.concat([pie_df, cash_row], ignore_index=True)

    fig = go.Figure(data=[go.Pie(labels=pie_df["symbol"], values=pie_df["capital_allocation_%"], hole=0.35)])
    fig.update_traces(textinfo='label+percent')
    st.plotly_chart(fig, use_container_width=True)

    # ------------------ Risk Exposure Chart ------------------
    st.subheader("⚠️ Risk Exposure by Position (Initial Risk % of Capital)")
    risk_df = df[["symbol", "initial_risk_amt"]].copy()
    risk_df["initial_risk_pct_of_capital"] = (risk_df["initial_risk_amt"] / capital) * 100
    fig2 = go.Figure(data=[go.Bar(x=risk_df["symbol"], y=risk_df["initial_risk_pct_of_capital"])])
    fig2.update_layout(yaxis_title="% of Capital", xaxis_title="Symbol")
    st.plotly_chart(fig2, use_container_width=True)

    # ------------------ Per-symbol detail expander & actions ------------------
    st.subheader("🔍 Per-symbol details & actions")
    for idx, row in df.sort_values(by="capital_allocation_%", ascending=False).iterrows():
        with st.expander(f"{row['symbol']} — Qty: {row['quantity']} | Invested: ₹{row['invested_value']:.0f}"):
            st.write(row[display_cols].to_frame().T)
            st.write("**Targets (price)**:", row["targets_list"])
            st.write("**Potential gains (₹)**:", row["potential_gains_list"])

            if show_actions and row['side'] in ["LONG", "SHORT"]:
                cols = st.columns(3)
                if cols[0].button(f"Square-off {row['symbol']}", key=f"sq_{row['symbol']}"):
                    try:
                        # attempt square-off using API (best-effort - depends on broker API)
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
                    st.info("Modify SL functionality depends on having order_id. Use manual modify in Orders page.")

    # ------------------ Export final CSV ------------------
    st.subheader("📥 Export")
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    st.download_button("Download positions with risk data (CSV)", csv_bytes, file_name="positions_risk.csv", mime="text/csv")

except Exception as e:
    st.error(f"⚠️ Dashboard fetch failed: {e}")
    st.text(traceback.format_exc())

st.caption("Notes:\n- Initial SL is calculated as AvgBuy * (1 - InitialSL%).\n- Targets are calculated from AvgBuy using the percent values you set in the sidebar.\n- Trailing SL steps are mapped to the same thresholds as targets (first threshold moves SL to breakeven, next moves SL to breakeven+previous target, etc.).\n- Short positions are mirrored logically.\n- Action buttons attempt API calls if your broker client supports them — use with caution.")
