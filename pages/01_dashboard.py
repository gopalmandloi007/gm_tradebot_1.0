import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# ------------------ Configuration ------------------
st.set_page_config(layout="wide")
st.title("📊 Trading Dashboard — Simplified Risk & PnL")

# ------------------ Defaults ------------------
DEFAULT_TOTAL_CAPITAL = 1400000
DEFAULT_INITIAL_SL_PCT = 2.0
DEFAULT_TARGETS = [10, 20, 30, 40]  # in %

# ------------------ Client check ------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

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
        token = item.get("token")
        tradingsymbol = item.get("tradingsymbol")
        avg_buy_price = float(item.get("avg_buy_price") or 0)
        quantity = int(sum([
            float(item.get(k) or 0) for k in ["dp_qty", "t1_qty", "holding_used"]
        ]))
        rows.append({
            "symbol": tradingsymbol,
            "token": token,
            "avg_buy_price": avg_buy_price,
            "quantity": quantity
        })

    if not rows:
        st.warning("⚠️ No holdings found.")
        st.stop()

    df = pd.DataFrame(rows)

except Exception as e:
    st.error(f"⚠️ Error fetching holdings: {e}")
    st.stop()

# ------------------ Helper: Parse historical CSV ------------------
def parse_definedge_csv(raw_text):
    import io
    df = pd.read_csv(io.StringIO(raw_text), header=None)
    if df.shape[1] >= 6:
        df.columns = ["DateTime","Open","High","Low","Close","Volume"] + [f"X{i}" for i in range(df.shape[1]-6)]
    df["DateTime"] = pd.to_datetime(df[0], errors="coerce")
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["DateTime", "Close"]).sort_values("DateTime").reset_index(drop=True)
    return df

# ------------------ Sidebar Settings ------------------
capital = st.sidebar.number_input("Total Capital (₹)", value=DEFAULT_TOTAL_CAPITAL, step=10000)
initial_sl_pct = st.sidebar.number_input("Initial Stop Loss (%)", value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1)/100
targets_input = st.sidebar.text_input("Targets % (comma separated)", ",".join(map(str, DEFAULT_TARGETS)))
try:
    target_pcts = sorted([max(0.0, float(t.strip())/100.0) for t in targets_input.split(",") if t.strip()])
except Exception:
    target_pcts = [t/100.0 for t in DEFAULT_TARGETS]

today_dt = datetime.now()

# ------------------ Fetch LTP & Prev Close ------------------
ltp_list, prev_close_list = [], []

for idx, row in df.iterrows():
    token = row["token"]
    ltp, prev_close = 0.0, 0.0

    # 1) Quote first
    try:
        quote = client.get_quotes(exchange="NSE", token=token)
        ltp = float(quote.get("ltp") or 0)
        prev_close = float(quote.get("prev_close") or 0)
    except:
        pass

    # 2) Fallback to historical last 3 days
    if prev_close == 0:
        try:
            frm = (today_dt - timedelta(days=3)).strftime("%d%m%Y%H%M")
            to  = today_dt.strftime("%d%m%Y%H%M")
            raw_csv = client.historical_csv(segment="NSE", token=token, timeframe="day", frm=frm, to=to)
            hist_df = parse_definedge_csv(raw_csv)
            if not hist_df.empty:
                prev_close = hist_df[hist_df["DateTime"].dt.date < today_dt.date()]["Close"].max()
        except:
            prev_close = ltp  # fallback

    ltp_list.append(ltp)
    prev_close_list.append(prev_close)

df["ltp"] = ltp_list
df["prev_close"] = prev_close_list

# ------------------ Calculate P&L and Risk ------------------
df["invested_value"] = df["avg_buy_price"] * df["quantity"]
df["current_value"] = df["ltp"] * df["quantity"]
df["today_pnl"] = (df["ltp"] - df["prev_close"]) * df["quantity"]
df["overall_pnl"] = df["current_value"] - df["invested_value"]

def calc_stops_targets(row):
    avg, qty, ltp = row["avg_buy_price"], row["quantity"], row["ltp"]
    if qty == 0 or avg == 0: return {"initial_sl_price": 0.0, "targets": [0]*len(target_pcts), "tsl_price":0.0}

    initial_sl_price = round(avg*(1-initial_sl_pct),2)
    targets = [round(avg*(1+t),2) for t in target_pcts]
    perc = (ltp/avg - 1)
    crossed_indices = [i for i, th in enumerate(target_pcts) if perc >= th]
    tsl_price = targets[crossed_indices[-1]] if crossed_indices else initial_sl_price
    return {"initial_sl_price": initial_sl_price, "targets": targets, "tsl_price": tsl_price}

stops_targets = df.apply(calc_stops_targets, axis=1, result_type="expand")
df = pd.concat([df, stops_targets], axis=1)

# ------------------ Display ------------------
st.subheader("📋 Holdings with LTP, Prev Close & PnL")
st.dataframe(df[["symbol","quantity","avg_buy_price","ltp","prev_close","today_pnl","overall_pnl","initial_sl_price","tsl_price","targets"]])
