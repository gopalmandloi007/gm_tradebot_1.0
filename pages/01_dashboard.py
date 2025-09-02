# pages/01_dashboard.py
import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta
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
initial_sl_pct = st.sidebar.number_input(
    "Initial Stop Loss (%)", value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1
) / 100.0
targets_input = st.sidebar.text_input("Targets % (comma separated)", ",".join(map(str, DEFAULT_TARGETS)))

try:
    target_pcts = sorted([max(0.0, float(t.strip()) / 100.0) for t in targets_input.split(",") if t.strip()])
    if not target_pcts:
        target_pcts = [t / 100.0 for t in DEFAULT_TARGETS]
except Exception:
    st.sidebar.error("Invalid Targets input — using defaults")
    target_pcts = [t / 100.0 for t in DEFAULT_TARGETS]

trailing_thresholds = target_pcts
auto_refresh = st.sidebar.checkbox("Auto-refresh LTP on page interaction", value=False)
show_actions = st.sidebar.checkbox("Show Action Buttons (Square-off / Place SL)", value=False)
st.sidebar.markdown("---")

# ================= Helper functions =================

def pick_nse_entry_from_tradingsymbol(ts):
    """
    ts can be:
      - list of dicts -> prefer dict with exchange == 'NSE'
      - dict -> return as-is
      - other -> None
    """
    if isinstance(ts, list):
        for entry in ts:
            if isinstance(entry, dict) and entry.get("exchange") == "NSE":
                return entry
        # fallback to first dict entry
        for entry in ts:
            if isinstance(entry, dict):
                return entry
        return None
    if isinstance(ts, dict):
        return ts
    return None


def parse_holding_item(item):
    """
    Given one holding item (dict), return a normalized row dict or None.
    Handles tradingsymbol being a list (NSE/BSE) as in your sample.
    """
    if not isinstance(item, dict):
        return None

    try:
        avg_buy_price = float(item.get("avg_buy_price") or 0.0)
    except Exception:
        avg_buy_price = 0.0

    try:
        dp_qty = float(item.get("dp_qty") or 0.0)
        t1_qty = float(item.get("t1_qty") or 0.0)
        holding_used = float(item.get("holding_used") or 0.0)
        total_qty = int(dp_qty + t1_qty + holding_used)
    except Exception:
        total_qty = 0

    ts_raw = item.get("tradingsymbol")
    ts_entry = pick_nse_entry_from_tradingsymbol(ts_raw)

    if not ts_entry:
        return None

    exchange = ts_entry.get("exchange")
    symbol = ts_entry.get("tradingsymbol") or ts_entry.get("symbol")
    token = ts_entry.get("token") or ts_entry.get("instrument_token") or item.get("token")

    if exchange != "NSE" or not symbol or not token or total_qty == 0:
        # skip non-NSE or missing fields or zero quantity
        return None

    return {
        "symbol": symbol,
        "token": str(token),
        "avg_buy_price": avg_buy_price,
        "quantity": total_qty,
        "product_type": item.get("product_type", ""),
    }


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


def fetch_prev_close(client, token, today_dt=None):
    """Fetch previous close (yesterday's close price)."""
    if today_dt is None:
        today_dt = datetime.now()

    try:
        # पिछले 3 दिन का history लो (safe buffer)
        from_dt = (today_dt - timedelta(days=3)).strftime("%Y%m%d")
        to_dt = (today_dt - timedelta(days=1)).strftime("%Y%m%d")

        hist_csv = client.historical_csv(
            segment="NSE",
            token=token,
            timeframe="day",
            frm=f"{from_dt}0000",
            to=f"{to_dt}2359",
        )

        if not isinstance(hist_csv, str):
            hist_csv = str(hist_csv)

        hist_df = pd.read_csv(io.StringIO(hist_csv), header=None)

        if hist_df.empty:
            return 0.0

        # format: [date, open, high, low, close, volume]
        prev_close_val = hist_df.iloc[-1, 4]
        return float(prev_close_val)
    except Exception as e:
        print("Prev close fetch error:", e)
        return 0.0


# ------------------ Risk & TSL / Targets calculations ------------------
def calc_stops_targets(row, initial_sl_pct, target_pcts, trailing_thresholds):
    avg = float(row.get("avg_buy_price") or 0.0)
    qty = int(row.get("quantity") or 0)
    ltp = float(row.get("ltp") or 0.0)

    if qty == 0 or avg == 0:
        return {
            "side": "FLAT",
            "initial_sl_price": 0.0,
            "tsl_price": 0.0,
            "targets": [0.0] * len(target_pcts),
            "initial_risk": 0.0,
            "open_risk": 0.0,
            "realized_if_tsl_hit": 0.0,
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
            "realized_if_tsl_hit": realized_if_tsl_hit,
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
            "realized_if_tsl_hit": realized_if_tsl_hit,
        }


# ================== Main Flow ==================
try:
    holdings_resp = client.get_holdings()
    if not holdings_resp or not isinstance(holdings_resp, dict) or holdings_resp.get("status") != "SUCCESS":
        st.warning("⚠️ No holdings found or API returned error")
        st.stop()

    holdings = holdings_resp.get("data", [])
    if not holdings:
        st.info("✅ No holdings found.")
        st.stop()

    rows = []
    for item in holdings:
        parsed = parse_holding_item(item)
        if parsed:
            rows.append(parsed)

    if not rows:
        st.warning("⚠️ No NSE holdings found.")
        st.stop()

    df = pd.DataFrame(rows)

    # ------------------ Prices (LTP + Prev Close) ------------------
    st.info("Fetching live prices and previous close (robust logic).")
    ltp_list = []
    prev_close_list = []
    today_dt = datetime.now()

    for _, r in df.iterrows():
        token = str(r.get("token") or "")
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
    results = df.apply(
        lambda row: calc_stops_targets(row, initial_sl_pct, target_pcts, trailing_thresholds),
        axis=1,
        result_type="expand",
    )
    df = pd.concat([df, results], axis=1)

    # explode targets into columns
    for i, tp in enumerate(target_pcts, start=1):
        df[f"target_{i}_pct"] = tp * 100
        df[f"target_{i}_price"] = df["targets"].apply(
            lambda lst, j=i: round(lst[j - 1], 4) if isinstance(lst, list) and len(lst) >= j else 0.0
        )

    # ------------------ Portfolio metrics ------------------
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

    # ------------------ Intelligent Messaging about Open Risk / Breakeven ------------------
    total_positions = len(df)
    breakeven_count = int((df["open_risk"] == 0).sum()) if "open_risk" in df.columns else 0
    profitable_by_ltp = int((df["ltp"] > df["avg_buy_price"]).sum())

    if total_positions == 0:
        st.info("No positions to show.")
    else:
        if breakeven_count == total_positions:
            st.success(
                f"✅ All {total_positions} positions have TSL >= AvgBuy (no open risk). {profitable_by_ltp} of them currently show unrealized profit by LTP."
            )
        else:
            st.info(
                f"ℹ️ {breakeven_count}/{total_positions} positions have no open risk (TSL >= AvgBuy). {profitable_by_ltp} positions currently showing unrealized profit by LTP."
            )
            risky = df[df["open_risk"] > 0].sort_values(by="open_risk", ascending=False).head(10) if "open_risk" in df.columns else pd.DataFrame()
            if not risky.empty:
                st.table(risky[["symbol", "quantity", "avg_buy_price", "ltp", "tsl_price", "open_risk"]])

    # ------------------ If ALL TSL are hit: compute realized PnL scenario ------------------
    st.subheader("🔮 Scenario: If ALL TSL get hit (immediate exit at current TSL)")
    st.write(
        "This assumes each position is closed at its calculated TSL price. For LONGs, PnL = (TSL - AvgBuy) * Qty. For SHORTs, PnL = (AvgBuy - TSL) * Qty."
    )

    st.metric("Total Realized if all TSL hit", f"₹{total_realized_if_all_tsl:,.2f}")
    delta_vs_unrealized = total_realized_if_all_tsl - total_overall_pnl
    st.metric("Delta vs Current Unrealized PnL", f"₹{delta_vs_unrealized:,.2f}")
    st.write(f"That is {total_realized_if_all_tsl/capital*100:.2f}% of your total capital.")

    df["realized_if_tsl_sign"] = df["realized_if_tsl_hit"].apply(lambda x: "profit" if x > 0 else ("loss" if x < 0 else "breakeven")) if "realized_if_tsl_hit" in df.columns else ""
    winners = df[df["realized_if_tsl_hit"] > 0] if "realized_if_tsl_hit" in df.columns else pd.DataFrame()
    losers = df[df["realized_if_tsl_hit"] < 0] if "realized_if_tsl_hit" in df.columns else pd.DataFrame()
    breakevens = df[df["realized_if_tsl_hit"] == 0] if "realized_if_tsl_hit" in df.columns else pd.DataFrame()

    st.write(f"Winners: {len(winners)}, Losers: {len(losers)}, Breakeven: {len(breakevens)}")
    if not winners.empty:
        st.table(winners[["symbol", "quantity", "avg_buy_price", "tsl_price", "realized_if_tsl_hit"]].sort_values(by="realized_if_tsl_hit", ascending=False).head(10))
    if not losers.empty:
        st.table(losers[["symbol", "quantity", "avg_buy_price", "tsl_price", "realized_if_tsl_hit"]].sort_values(by="realized_if_tsl_hit").head(10))

    # ------------------ Positions & Risk Table ------------------
    display_cols = [
        "symbol",
        "quantity",
        "side",
        "avg_buy_price",
        "ltp",
        "invested_value",
        "current_value",
        "overall_pnl",
        "today_pnl",
        "capital_allocation_%",
        "initial_sl_price",
        "tsl_price",
        "initial_risk",
        "open_risk",
        "realized_if_tsl_hit",
    ]

    # ensure the correct name exists: we used "capital_allocation_%" earlier
    if "capital_allocation_%" not in df.columns and "capital_allocation_%" in df.columns:
        pass  # just keeping compatibility; main column is capital_allocation_%

    # add target columns to display
    for i in range(1, len(target_pcts) + 1):
        display_cols += [f"target_{i}_pct", f"target_{i}_price"]

    st.subheader("📋 Positions & Risk Table")
    # ensure only existing columns are selected
    df_display = df[[c for c in display_cols if c in df.columns]].sort_values(by="capital_allocation_%", ascending=False, na_position="last").reset_index(drop=True)
    st.dataframe(df_display, use_container_width=True)

    # ------------------ Visuals ------------------
    st.subheader("📊 Capital Allocation & Risk Visuals")
    pie_df = df[["symbol", "capital_allocation_%"]].copy() if "capital_allocation_%" in df.columns or "capital_allocation_%" in df.columns else pd.DataFrame()
    if not pie_df.empty:
        cash_pct = max(0.0, 100 - pie_df["capital_allocation_%"].sum())
        pie_df = pd.concat([pie_df, pd.DataFrame([{"symbol": "Cash", "capital_allocation_%": cash_pct}])], ignore_index=True)
        fig = go.Figure(data=[go.Pie(labels=pie_df["symbol"], values=pie_df["capital_allocation_%"], hole=0.35)])
        fig.update_traces(textinfo="label+percent")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("⚠️ Risk Exposure by Position (Initial Risk % of Capital)")
    if "initial_risk" in df.columns:
        risk_df = df[["symbol", "initial_risk"]].copy()
        risk_df["initial_risk_pct_of_capital"] = (risk_df["initial_risk"] / capital) * 100
        fig2 = go.Figure(data=[go.Bar(x=risk_df["symbol"], y=risk_df["initial_risk_pct_of_capital"])])
        fig2.update_layout(yaxis_title="% of Capital", xaxis_title="Symbol")
        st.plotly_chart(fig2, use_container_width=True)

    # ------------------ Per-symbol expanders & actions ------------------
    st.subheader("🔍 Per-symbol details & actions")
    for _, row in df.sort_values(by="capital_allocation_%", ascending=False, na_position="last").iterrows():
        with st.expander(f"{row['symbol']} — Qty: {row['quantity']} | Invested: ₹{row['invested_value']:.0f}"):
            st.write(row[[c for c in df_display.columns if c in row.index]].to_frame().T)
            st.write("**Targets (price)**:", row.get("targets", []))
            st.write("**Potential realized if TSL hit (₹)**:", row.get("realized_if_tsl_hit", 0.0))

            if show_actions and row.get("side") in ["LONG", "SHORT"]:
                cols = st.columns(3)
                if cols[0].button(f"Square-off {row['symbol']}", key=f"sq_{row['symbol']}"):
                    try:
                        payload = {
                            "exchange": "NSE",
                            "tradingsymbol": row["symbol"],
                            "quantity": int(abs(row["quantity"])),
                            "product_type": "INTRADAY",
                            "order_type": "SELL" if row["side"] == "LONG" else "BUY",
                        }
                        resp = client.square_off_position(payload)
                        st.write("🔎 Square-off API Response:", resp)
                        if isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                            st.success("Square-off placed successfully")
                        else:
                            st.error("Square-off failed: " + str(resp))
                    except Exception as e:
                        st.error(f"Square-off failed: {e}")
                        st.text(traceback.format_exc())

                if cols[1].button(f"Place SL Order @ TSL ({row.get('tsl_price')})", key=f"sl_{row['symbol']}"):
                    try:
                        payload = {
                            "exchange": "NSE",
                            "tradingsymbol": row["symbol"],
                            "quantity": int(abs(row["quantity"])),
                            "price_type": "SL-LIMIT",
                            "price": float(row.get("tsl_price") or 0.0),
                            "product_type": "INTRADAY",
                            "order_type": "SELL" if row["side"] == "LONG" else "BUY",
                        }
                        resp = client.place_order(payload)
                        st.write("🔎 Place SL API Response:", resp)
                        if isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                            st.success("SL order placed successfully")
                        else:
                            st.error("SL placement failed: " + str(resp))
                    except Exception as e:
                        st.error(f"SL placement failed: {e}")
                        st.text(traceback.format_exc())

                if cols[2].button(f"Modify SL to initial ({row.get('initial_sl_price')})", key=f"modsl_{row['symbol']}"):
                    st.info("Modify SL functionality depends on existing order_id. Use Orders page to modify specific orders.")

    # ------------------ Export ------------------
    st.subheader("📥 Export")
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download positions with risk data (CSV)", csv_bytes, file_name="positions_risk.csv", mime="text/csv")

except Exception as e:
    st.error(f"⚠️ Dashboard fetch failed: {e}")
    st.text(traceback.format_exc())

st.caption(
    "Notes:\n"
    "- Prev close is chosen using a robust 'last full trading day' logic to avoid using an incomplete current-day candle.\n"
    "- TSL mapping: when LTP crosses the first threshold (e.g. 10%) TSL -> breakeven; next threshold moves TSL to AvgBuy + previous threshold, etc.\n"
    "- If Total Open Risk == 0 then TSL >= AvgBuy for all positions (no downside left in the portfolio under current TSL).\n"
    "- The 'If ALL TSL hit' scenario computes realized P/L assuming immediate exit at each position's calculated TSL."
)
