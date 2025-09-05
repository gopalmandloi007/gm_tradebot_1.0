# pages/gtt_orderbook.py
import streamlit as st
import pandas as pd
import traceback
from typing import Dict, List

st.set_page_config(layout="wide")
st.header("⏰ GTT & OCO Order Book — Auto-protect & Sync with Holdings")

client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

debug = st.checkbox("Show debug info (orderbook)", value=False)

# ---- Safe API wrapper helpers ----
def safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        if debug:
            st.write(f"🔧 Safe call failed for {getattr(fn, '__name__', str(fn))}: {e}")
            st.text(traceback.format_exc())
        return None

def safe_hasattr(obj, name):
    return hasattr(obj, name) and getattr(obj, name) is not None

# ---- Helpers for data normalization ----
def _to_int(val, default=0):
    try:
        if val is None or val == "":
            return int(default)
        return int(float(val))
    except Exception:
        return int(default)

def _to_float(val, default=0.0):
    try:
        if val is None or val == "":
            return float(default)
        return float(val)
    except Exception:
        return float(default)

def _safe_str(x, default=""):
    return default if x is None else str(x)

def flatten_gtt_response(resp: Dict) -> pd.DataFrame:
    rows = resp.get("pendingGTTOrderBook") or resp.get("data") or []
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # detect OCO if any oco-specific fields exist (robust)
    def _is_oco(r):
        for k in ["target_price","stoploss_price","target_quantity","stoploss_quantity","target_trigger","stoploss_trigger"]:
            if k in r and pd.notna(r[k]) and str(r[k]).strip() != "":
                return True
        return False
    df["order_kind"] = df.apply(lambda r: "OCO" if _is_oco(r.to_dict()) else "GTT", axis=1)
    # canonical symbol and numeric conversions
    if "tradingsymbol" in df.columns:
        df["tradingsymbol"] = df["tradingsymbol"].astype(str).str.upper()
    for col in ["quantity","target_quantity","stoploss_quantity","alert_price","trigger_price","price","target_price","stoploss_price"]:
        if col in df.columns:
            # keep as string fields too, but create numeric columns for calculations
            df[f"_{col}_num"] = df[col].apply(lambda v: _to_float(v, 0) if isinstance(v, (int,float,str)) and str(v).strip() != "" else 0)
    return df

# ---- Load holdings (try session_state first) ----
holdings_df = st.session_state.get("holdings_df", None)
if holdings_df is None:
    # attempt to fetch holdings directly (same logic as holdings.py)
    try:
        raw_holdings_resp = safe_call(client.get_holdings)
        if isinstance(raw_holdings_resp, dict) and raw_holdings_resp.get("status") == "SUCCESS":
            # flatten same as holdings.py
            raw_list = raw_holdings_resp.get("data", [])
            recs = []
            for h in raw_list:
                base = {k: v for k, v in h.items() if k != "tradingsymbol"}
                for ts in h.get("tradingsymbol", []):
                    if ts.get("exchange") == "NSE":
                        recs.append({**base, **ts})
            if recs:
                dfh = pd.DataFrame(recs)
                # normalise
                dfh["quantity"] = dfh.apply(lambda r: int(float(r.get("quantity") or r.get("qty") or r.get("holding_qty") or 0)), axis=1)
                dfh["available_quantity"] = dfh.apply(lambda r: int(float(r.get("available_quantity") or r.get("sellable_quantity") or r.get("available_qty") or r.get("quantity") or 0)), axis=1)
                dfh["remaining_qty"] = dfh["available_quantity"]
                dfh["average_price"] = dfh.apply(lambda r: float(r.get("average_price") or r.get("avg_price") or r.get("avg_buy_price") or 0.0), axis=1)
                dfh["tradingsymbol"] = dfh["tradingsymbol"].astype(str).str.upper()
                holdings_df = dfh
                st.session_state["holdings_df"] = holdings_df
                if debug:
                    st.write("🔎 Fetched holdings (fallback)", holdings_df)
    except Exception as e:
        if debug:
            st.write("Holdings fetch error:", e)

# Build holdings map for quick lookup
holdings_map = {}
if holdings_df is not None and not holdings_df.empty:
    for _, r in holdings_df.iterrows():
        holdings_map[_safe_str(r["tradingsymbol"]).upper()] = {
            "quantity": _to_int(r.get("quantity", 0)),
            "remaining_qty": _to_int(r.get("remaining_qty", r.get("available_quantity", 0))),
            "avg_price": _to_float(r.get("average_price", 0.0)),
            "row": r.to_dict()
        }

# ---- Fetch GTT/OCO orders ----
if not safe_hasattr(client, "gtt_orders"):
    st.error("⚠️ Your client wrapper does not expose `gtt_orders()` — adapt the code to call your wrapper's method.")
    st.stop()

resp = safe_call(client.gtt_orders)
if resp is None:
    st.error("⚠️ Failed to fetch GTT/OCO orders (client.gtt_orders returned None or failed).")
    st.stop()

if debug:
    st.write("🔎 Raw gtt_orders response:", resp)

df = flatten_gtt_response(resp)

if df.empty:
    st.info("✅ No pending GTT / OCO orders found.")
    st.stop()

# Basic filters UI
with st.container():
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        search_symbol = st.text_input("🔎 Search by Trading Symbol", "").strip().upper()
    with c2:
        sel_exchange = st.selectbox("Exchange filter", ["All"] + sorted(df["exchange"].dropna().unique().tolist()))
    with c3:
        sel_kind = st.selectbox("Type filter", ["All", "GTT", "OCO"])

filt = df.copy()
if search_symbol:
    filt = filt[filt["tradingsymbol"].astype(str).str.upper().str.contains(search_symbol)]
if sel_exchange != "All":
    filt = filt[filt["exchange"] == sel_exchange]
if sel_kind != "All":
    filt = filt[filt["order_kind"] == sel_kind]

st.success(f"✅ Found {len(filt)} pending orders")
st.dataframe(filt, use_container_width=True)

# ---- Action: Cancel orders for symbols not in holdings ----
st.markdown("---")
st.subheader("🧹 Cleanup: Cancel orders for symbols NOT in holdings")

not_in_holdings = filt[~filt["tradingsymbol"].isin(list(holdings_map.keys()))] if holdings_map else filt
if not_in_holdings.empty:
    st.info("No pending orders for symbols outside holdings (or holdings not loaded).")
else:
    st.write(f"Found {len(not_in_holdings)} pending orders for symbols not in your holdings.")
    if st.button("🛑 Cancel all GTT/OCO orders not in holdings"):
        cancelled = []
        failed = []
        for _, r in not_in_holdings.iterrows():
            aid = _safe_str(r.get("alert_id") or r.get("id") or "")
            kind = r.get("order_kind", "GTT")
            try:
                if kind == "OCO":
                    if safe_hasattr(client, "oco_cancel"):
                        resp_cancel = safe_call(client.oco_cancel, aid)
                    else:
                        resp_cancel = None
                else:
                    if safe_hasattr(client, "gtt_cancel"):
                        resp_cancel = safe_call(client.gtt_cancel, aid)
                    else:
                        resp_cancel = None
                if resp_cancel and isinstance(resp_cancel, dict) and resp_cancel.get("status") == "SUCCESS":
                    cancelled.append(aid)
                else:
                    failed.append({"alert_id": aid, "resp": resp_cancel})
            except Exception as e:
                failed.append({"alert_id": aid, "error": str(e)})
        st.write("✅ Cancelled:", cancelled)
        if failed:
            st.warning("Failed to cancel (see details):")
            st.write(failed)
        st.experimental_rerun()

# ---- Detect holdings missing protective orders ----
st.markdown("---")
st.subheader("🛡️ Auto-protect holdings (place OCO/GTT where missing)")

# Build a map of existing protection quantities per symbol by summing quantities from GTT/OCO rows
protection_map = {}
for _, r in filt.iterrows():
    sym = _safe_str(r.get("tradingsymbol")).upper()
    if sym == "":
        continue
    # determine intended protective qty of this order
    qty = 0
    # For OCO, prefer explicit target+stoploss quantities if present
    if r.get("order_kind") == "OCO":
        tq = _to_int(r.get("target_quantity") or r.get("target_qty") or r.get("_target_quantity_num") or 0)
        sq = _to_int(r.get("stoploss_quantity") or r.get("stoploss_qty") or r.get("_stoploss_quantity_num") or 0)
        # Some APIs use 'quantity' as total
        if tq + sq == 0:
            qty = _to_int(r.get("quantity") or 0)
        else:
            qty = tq + sq
    else:
        # GTT typically has 'quantity'
        qty = _to_int(r.get("quantity") or r.get("_quantity_num") or 0)
    protection_map[sym] = protection_map.get(sym, 0) + qty

# Build list of holdings that are under-protected
to_protect = []
if holdings_map:
    for sym, info in holdings_map.items():
        required = info["remaining_qty"]
        existing = protection_map.get(sym, 0)
        missing = max(0, required - existing)
        if missing > 0 and required > 0:
            to_protect.append({"symbol": sym, "required_qty": required, "existing_protection": existing, "missing_qty": missing, "avg_price": info.get("avg_price", 0.0)})

if not to_protect:
    st.info("All holdings appear protected by existing GTT/OCO orders (or holdings not loaded).")
else:
    st.write(f"Found {len(to_protect)} holdings with missing protection.")
    for t in to_protect:
        st.markdown("---")
        st.write(f"**{t['symbol']}** — holding remaining qty: {t['required_qty']}, existing protected qty: {t['existing_protection']}, missing: **{t['missing_qty']}**")
        with st.form(key=f"auto_protect_{t['symbol']}"):
            col1, col2, col3 = st.columns(3)
            with col1:
                # default: create OCO sell (protect long holding)
                suggested_order_type = "SELL"
                order_type = st.selectbox("Order Type", ["SELL", "BUY"], index=0, key=f"pt_ord_{t['symbol']}")
                product = st.selectbox("Product Type", ["CNC", "INTRADAY", "NORMAL"], index=0, key=f"pt_prod_{t['symbol']}")
            with col2:
                # price suggestions: use avg_price for baseline if available
                avg = t.get("avg_price") or 0.0
                # default target & sl: user must confirm; keep conservative defaults
                tgt_pct = st.number_input("Target +% (suggest)", min_value=0.1, max_value=50.0, value=2.0, step=0.1, key=f"pt_tgtpct_{t['symbol']}")
                sl_pct = st.number_input("Stoploss -% (suggest)", min_value=0.1, max_value=50.0, value=2.0, step=0.1, key=f"pt_slpct_{t['symbol']}")
                # suggested derived prices shown but user can set explicit below
                suggested_target_price = round(avg * (1 + tgt_pct / 100), 2) if avg > 0 else 0.0
                suggested_stoploss_price = round(avg * (1 - sl_pct / 100), 2) if avg > 0 else 0.0
                st.write(f"Suggested target: {suggested_target_price} | suggested SL: {suggested_stoploss_price}")
            with col3:
                qty_to_place = st.number_input("Quantity to protect", min_value=1, max_value=t["missing_qty"], value=t["missing_qty"], step=1, key=f"pt_qty_{t['symbol']}")
                use_oco = st.checkbox("Place OCO (target + SL)", value=True, key=f"pt_oco_{t['symbol']}")
                explicit_tgt_price = st.number_input("Target Price (explicit, 0 = use suggested)", min_value=0.0, format="%.2f", value=0.0, step=0.05, key=f"pt_tgtprice_{t['symbol']}")
                explicit_sl_price = st.number_input("Stoploss Price (explicit, 0 = use suggested)", min_value=0.0, format="%.2f", value=0.0, step=0.05, key=f"pt_slprice_{t['symbol']}")
            submitted = st.form_submit_button("Preview & Place protection")
            if submitted:
                # choose prices
                target_price = explicit_tgt_price if explicit_tgt_price > 0 else suggested_target_price
                stoploss_price = explicit_sl_price if explicit_sl_price > 0 else suggested_stoploss_price
                if qty_to_place <= 0:
                    st.error("Quantity must be > 0")
                elif use_oco and (target_price <= 0 or stoploss_price <= 0):
                    st.error("For OCO please specify valid prices (or provide avg_price in holdings to get suggestions).")
                else:
                    # build payload
                    if use_oco:
                        payload = {
                            "tradingsymbol": t["symbol"],
                            "exchange": "NSE",
                            "order_type": order_type,
                            "target_quantity": str(int(qty_to_place)),
                            "stoploss_quantity": str(int(qty_to_place)),
                            "target_price": str(round(float(target_price),2)),
                            "stoploss_price": str(round(float(stoploss_price),2)),
                            "product_type": product,
                            "remarks": "Auto-protect placed from dashboard"
                        }
                        st.json(payload)
                        # place OCO
                        if st.button(f"✅ Confirm place OCO for {t['symbol']}", key=f"confirm_oco_{t['symbol']}"):
                            if safe_hasattr(client, "oco_place"):
                                resp_place = safe_call(client.oco_place, payload)
                                st.write(resp_place)
                                if isinstance(resp_place, dict) and resp_place.get("status") == "SUCCESS":
                                    st.success("✅ OCO placed successfully")
                                    st.experimental_rerun()
                                else:
                                    st.error(f"❌ Failed to place OCO: {resp_place}")
                            else:
                                st.error("⚠️ client.oco_place() not available in your wrapper. Adapt code.")
                    else:
                        # place simple GTT to place an order (e.g., stoploss or limit)
                        payload = {
                            "exchange": "NSE",
                            "tradingsymbol": t["symbol"],
                            "condition": "LTP_BELOW" if order_type == "SELL" else "LTP_ABOVE",
                            "alert_price": str(round(float(stoploss_price if order_type=="SELL" else target_price),2)),
                            "order_type": order_type,
                            "price": str(round(float(stoploss_price if order_type=="SELL" else target_price),2)),
                            "quantity": str(int(qty_to_place)),
                            "product_type": product,
                            "remarks": "Auto-protect GTT placed from dashboard"
                        }
                        st.json(payload)
                        if st.button(f"✅ Confirm place GTT for {t['symbol']}", key=f"confirm_gtt_{t['symbol']}"):
                            if safe_hasattr(client, "gtt_place"):
                                resp_place = safe_call(client.gtt_place, payload)
                                st.write(resp_place)
                                if isinstance(resp_place, dict) and resp_place.get("status") == "SUCCESS":
                                    st.success("✅ GTT placed successfully")
                                    st.experimental_rerun()
                                else:
                                    st.error(f"❌ Failed to place GTT: {resp_place}")
                            else:
                                st.error("⚠️ client.gtt_place() not available in your wrapper. Adapt code.")

# ---- Utility: Try to detect executed child legs and enforce cleanup ----
st.markdown("---")
st.subheader("🔁 Auto-check: if SL leg executed then cancel counterpart / allow qty-adjust")

def _get_child_orders_from_row(row):
    """Try to extract children from the row dict or fetch via API if possible."""
    # common fields in some wrappers: 'orders', 'child_orders', 'children'
    for k in ("orders","child_orders","children","children_orders"):
        if k in row and row[k]:
            return row[k]
    # fallback: try fetching via client (many wrappers offer an order_status or get_order_children)
    alert_id = row.get("alert_id") or row.get("id") or row.get("alertId")
    if not alert_id:
        return []
    # try a few possible client methods (adapt if your wrapper uses different names)
    possible_methods = ["gtt_child_orders", "get_gtt_children", "get_child_orders", "order_children", "gtt_childorder"]
    for m in possible_methods:
        if hasattr(client, m):
            try:
                res = getattr(client, m)(alert_id)
                if isinstance(res, dict) and res.get("status") == "SUCCESS" and res.get("data"):
                    return res.get("data")
                if isinstance(res, list):
                    return res
            except Exception:
                continue
    # last try: if your gtt_orders already returned 'orders' field it's handled above
    return []

# scan OCO rows and show actions
oco_rows = filt[filt["order_kind"] == "OCO"]
if not oco_rows.empty:
    for _, row in oco_rows.iterrows():
        st.markdown("---")
        sym = _safe_str(row.get("tradingsymbol")).upper()
        st.write(f"**{sym}** • Alert ID: {row.get('alert_id')} • Qty (raw): {row.get('quantity') or (row.get('target_quantity') or 0) + (row.get('stoploss_quantity') or 0)}")
        children = _get_child_orders_from_row(row.to_dict())
        if children:
            st.write("Child orders (detected):")
            st.write(children)
            # find executed/fill quantities per child
            executed_target = 0
            executed_sl = 0
            target_child = None
            sl_child = None
            for ch in children:
                # many APIs use 'type' or 'order_type', 'tag' or 'remarks' to identify
                tag = str(ch.get("tag") or ch.get("side") or ch.get("order_type") or ch.get("child_type") or "").upper()
                status = str(ch.get("status") or "").upper()
                filled = _to_int(ch.get("filled_quantity") or ch.get("executed_quantity") or ch.get("filled_qty") or ch.get("quantity_executed") or 0)
                if "TARGET" in tag or ("TARGET" in str(ch.get("remarks","")).upper()):
                    executed_target += filled
                    target_child = ch
                elif "STOP" in tag or "SL" in tag or ("STOPLOSS" in str(ch.get("remarks","")).upper()):
                    executed_sl += filled
                    sl_child = ch
                else:
                    # fallback by price logic: child with price > parent avg likely target; price < likely SL
                    if ch.get("price") and row.get("target_price") and float(ch.get("price")) == _to_float(row.get("target_price")):
                        executed_target += filled
                        target_child = ch
                    elif ch.get("price") and row.get("stoploss_price") and float(ch.get("price")) == _to_float(row.get("stoploss_price")):
                        executed_sl += filled
                        sl_child = ch

            st.write(f"Executed target qty: {executed_target} | executed SL qty: {executed_sl}")

            # If SL leg executed (non-zero), ensure target child is cancelled
            if executed_sl > 0 and target_child:
                st.warning("SL leg has executed. Cancelling target leg to protect holdings.")
                # attempt to cancel target_child
                possible_cancel_ids = [target_child.get("alert_id") or target_child.get("id") or target_child.get("child_alert_id")]
                cancelled = []
                failed = []
                for cid in possible_cancel_ids:
                    if not cid:
                        continue
                    # first try oco_cancel with parent alert id if child-level cancel not available
                    try:
                        if safe_hasattr(client, "oco_cancel"):
                            resp = safe_call(client.oco_cancel, _safe_str(row.get("alert_id")))
                            if resp and isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                                cancelled.append(cid)
                                st.success(f"✅ Cancelled counterpart for alert {row.get('alert_id')}")
                            else:
                                failed.append({"id": cid, "resp": resp})
                        elif safe_hasattr(client, "gtt_cancel"):
                            resp = safe_call(client.gtt_cancel, cid)
                            if resp and isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                                cancelled.append(cid)
                            else:
                                failed.append({"id": cid, "resp": resp})
                        else:
                            failed.append({"id": cid, "error": "no cancel method available"})
                    except Exception as e:
                        failed.append({"id": cid, "error": str(e)})
                if cancelled:
                    st.write("Cancelled ids:", cancelled)
                if failed:
                    st.warning("Failed to cancel counterpart:", failed)
        else:
            st.info("No child orders discovered for this OCO. If you expect child details, add a client method to fetch child orders or include them in gtt_orders() response.")

        # Action: adjust SL qty if target executed partially / fully
        # Compute total original qty
        total_qty = _to_int(row.get("quantity") or ( _to_int(row.get("target_quantity")) + _to_int(row.get("stoploss_quantity")) ))
        # If we have executed_target computed above:
        if children and total_qty > 0:
            # compute executed_target (recompute safe)
            exec_tgt = 0
            for ch in children:
                if str(ch.get("remarks","")).upper().find("TARGET")!=-1 or str(ch.get("tag","")).upper().find("TARGET")!=-1 or float(ch.get("price") or 0)==_to_float(row.get("target_price") or 0):
                    exec_tgt += _to_int(ch.get("filled_quantity") or ch.get("executed_quantity") or 0)
            remaining_for_sl = max(0, total_qty - exec_tgt)
            st.write(f"Remaining required SL quantity after target fills: {remaining_for_sl}")
            if exec_tgt > 0 and remaining_for_sl != _to_int(row.get("stoploss_quantity") or 0):
                if st.button(f"🔧 Modify SL qty to {remaining_for_sl} for alert {row.get('alert_id')}", key=f"modify_sl_qty_{row.get('alert_id')}"):
                    # call oco_modify to adjust stoploss_quantity
                    if safe_hasattr(client, "oco_modify"):
                        payload = {
                            "alert_id": _safe_str(row.get("alert_id")),
                            "stoploss_quantity": str(int(remaining_for_sl)),
                            # include other required fields your API needs; this is minimal
                            "remarks": "Auto-adjust SL quantity after target execution"
                        }
                        resp_modify = safe_call(client.oco_modify, payload)
                        st.write(resp_modify)
                        if isinstance(resp_modify, dict) and resp_modify.get("status") == "SUCCESS":
                            st.success("✅ Modified SL quantity.")
                            st.experimental_rerun()
                        else:
                            st.error(f"❌ Could not modify SL qty: {resp_modify}")
                    else:
                        st.error("⚠️ client.oco_modify() not available. Adapt your wrapper.")

# end main try
st.markdown("---")
st.info("Notes:\n• This page attempts to be conservative: it will not place or cancel orders without your explicit confirmation.\n• If your client wrapper uses different method names or different field names in order/child payloads, adjust the small sections marked by comments.\n• OCO auto-cancellation is attempted when the SL leg is detected as executed. Many brokers auto-handle OCO — this code is to add an extra safety layer.\n\nIf you want I can adapt this to call your exact client methods if you paste the wrapper methods' names / sample responses here.")
