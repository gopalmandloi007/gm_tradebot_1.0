# pages/order_gtt.1.1.py
import streamlit as st
import traceback
import time
from datetime import datetime
from typing import Dict

st.set_page_config(layout="wide")
st.header("📌 Place GTT / Advanced Multi-tier OCO — Definedge")

# ------------------ client & pre-check ------------------
client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

debug = st.checkbox("Show debug info", value=False)

# Ensure columns exist BEFORE using them
gtt_col, oco_col = st.columns(2)

# -------------------- Helpers --------------------
def _safe_str(x, default=""):
    return default if x is None else str(x)

def _payload_clean(d: Dict) -> Dict:
    return {k: _safe_str(v) for k, v in d.items() if v is not None and str(v) != ""}

def _to_float(val, default=0.0):
    try:
        if val is None or val == "":
            return default
        return float(val)
    except Exception:
        return default

def _to_int(val, default=0):
    try:
        if val is None or val == "":
            return default
        return int(float(val))
    except Exception:
        return default

def build_gtt_payload(exchange, tradingsymbol, condition, alert_price, quantity, side, price, product_type, remarks):
    return {
        "exchange": exchange,
        "tradingsymbol": tradingsymbol,
        "condition": condition,
        "alert_price": f"{float(alert_price):.2f}",
        "quantity": str(int(quantity)),
        "order_type": side,
        "price": f"{float(price):.2f}",
        **({"product_type": product_type} if product_type else {}),
        **({"remarks": remarks} if remarks else {}),
    }

# try different client method names gracefully
def _try_client_call(method_names, *args, **kwargs):
    for name in method_names:
        fn = getattr(client, name, None)
        if callable(fn):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                if debug:
                    st.warning(f"client.{name} raised: {e}")
                continue
    return None

GTT_PLACE_NAMES = ["gtt_place", "place_gtt", "gtt_create", "create_gtt"]
GTT_LIST_NAMES = ["gtt_list", "get_gtts", "gtt_fetch_all", "list_gtts", "get_gtt_alerts", "gtt_orders"]
GTT_CANCEL_NAMES = ["gtt_cancel", "gtt_delete", "gtt_remove", "cancel_gtt", "delete_gtt"]

def _parse_gtt_list(resp):
    active_ids = set()
    if resp is None:
        return active_ids
    entries = []
    if isinstance(resp, dict):
        for k in ("data", "alerts", "pendingGTTOrderBook", "pendingGTTOrders", "items", "result", "list"):
            if k in resp and isinstance(resp[k], (list, tuple)):
                entries = resp[k]
                break
        if not entries:
            for v in resp.values():
                if isinstance(v, (list, tuple)):
                    entries = v
                    break
    elif isinstance(resp, (list, tuple)):
        entries = resp

    for item in entries:
        if isinstance(item, dict):
            for id_key in ("alert_id", "id", "alertId", "alertID"):
                if id_key in item:
                    try:
                        active_ids.add(str(item[id_key]))
                    except:
                        pass
                    break
    if not active_ids and isinstance(entries, (list, tuple)):
        for item in entries:
            if isinstance(item, (str, int)):
                active_ids.add(str(item))
    return active_ids

def _format_layers_table(layers):
    rows = []
    for i, L in enumerate(layers, start=1):
        rows.append({
            "idx": i,
            "label": L.get("label"),
            "qty": int(L.get("qty", 0)),
            "price": float(L.get("price", 0)),
            "alert_id": _safe_str(L.get("alert_id")),
            "status": L.get("status", "NOT PLACED"),
        })
    return rows

# -------------------- GTT (left column) --------------------
with gtt_col:
    with st.expander("📌 Place GTT Order", expanded=True):
        gtt_side = st.radio("Select Side", ["BUY", "SELL"], horizontal=True, key="gtt_side")
        side_color = "green" if gtt_side == "BUY" else "red"
        st.markdown(f"**Selected: <span style='color:{side_color}'>{gtt_side}</span>**", unsafe_allow_html=True)

        with st.form("gtt_form_main"):
            st.caption("GTT — alert that fires into an order.")
            exchange = st.selectbox("Exchange", ["NSE", "BSE", "NFO", "MCX"], key="gtt_exchange")
            tradingsymbol = st.text_input("Trading Symbol", placeholder="e.g. TCS-EQ", key="gtt_symbol").strip().upper()
            condition = st.selectbox("Condition", ["LTP_ABOVE", "LTP_BELOW"], key="gtt_condition")

            c1, c2 = st.columns(2)
            with c1:
                alert_price = st.number_input("Alert Price", min_value=0.0, step=0.05, format="%.2f", key="gtt_alert_price")
                quantity = st.number_input("Quantity", min_value=1, step=1, value=1, key="gtt_quantity")
            with c2:
                price = st.number_input("Order Price", min_value=0.0, step=0.05, format="%.2f", key="gtt_order_price")

            product_type = st.selectbox("Product Type", ["", "CNC", "INTRADAY", "NORMAL"], key="gtt_product")
            remarks = st.text_input("Remarks (optional)", key="gtt_remarks")

            submit_gtt = st.form_submit_button("Preview GTT Payload")

        if submit_gtt:
            if not tradingsymbol:
                st.error("❌ Trading symbol required.")
            elif alert_price <= 0 or price <= 0:
                st.error("❌ Alert and Order prices must be > 0.")
            else:
                st.session_state["_pending_gtt"] = build_gtt_payload(
                    exchange, tradingsymbol, condition, alert_price, quantity, gtt_side, price, product_type, remarks
                )
                st.success("✅ Preview ready. Confirm below.")

        if "_pending_gtt" in st.session_state:
            st.markdown("---")
            st.subheader("Confirm GTT Order")
            st.json(st.session_state["_pending_gtt"])
            c1, c2 = st.columns(2)
            confirm_label = f"✅ Confirm {gtt_side} GTT"
            if c1.button(confirm_label, key="confirm_gtt_main"):
                try:
                    payload = _payload_clean(st.session_state["_pending_gtt"])
                    if debug:
                        st.json({"raw": st.session_state["_pending_gtt"], "clean": payload})
                    resp = _try_client_call(GTT_PLACE_NAMES, payload)
                    if debug:
                        st.write("GTT place resp:", resp)
                    if isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                        st.success(f"✅ GTT placed. ID: {resp.get('alert_id')}")
                        del st.session_state["_pending_gtt"]
                        st.experimental_rerun()
                    else:
                        st.error(f"❌ Failed: {resp}")
                except Exception as e:
                    st.error(str(e))
                    st.text(traceback.format_exc())
            if c2.button("❌ Cancel GTT", key="cancel_pending_gtt"):
                del st.session_state["_pending_gtt"]
                st.info("Cancelled.")

# -------------------- Advanced Multi-tier OCO (right column) --------------------
with oco_col:
    try:
        with st.expander("🎯 Advanced Multi-tier OCO (Multiple targets + multiple stops)", expanded=True):
            st.markdown("""
            **Behaviour**:
            - Each stop / target is placed as a GTT alert.
            - Manager scans broker GTT list: if an alert disappears we treat it as triggered.
            - After a stop triggers manager recalculates remaining qty and cancels targets that exceed remaining qty.
            """)

            with st.form("advanced_oco_form_main"):
                symbol = st.text_input("Trading Symbol (e.g. TCS-EQ)", value="", max_chars=50, key="adv_symbol").strip().upper()
                exch = st.selectbox("Exchange", ["NSE", "BSE", "NFO", "MCX"], index=0, key="adv_exchange")

                orig_side = st.radio("Original Side (position you have)", ["BUY", "SELL"], horizontal=True, key="adv_side")
                st.caption("If you bought (BUY) then child orders will be SELL; reverse for SELL")

                entry_price = st.number_input("Entry Price", min_value=0.0, step=0.05, format="%.2f", value=0.0, key="adv_entry")
                total_qty = int(st.number_input("Total Qty (position size)", min_value=1, step=1, value=1, key="adv_total_qty"))

                st.markdown("**Stop layers (price + qty)**")
                num_stops = st.number_input("Number of stop layers", min_value=1, max_value=10, value=2, key="adv_nstops")
                stop_layers = []
                for i in range(int(num_stops)):
                    c1, c2 = st.columns([2,1])
                    with c1:
                        sp = st.number_input(f"SL Price #{i+1}", min_value=0.0, step=0.05, format="%.2f", key=f"adv_sl_price_{i}")
                    with c2:
                        sq = int(st.number_input(f"Qty #{i+1}", min_value=0, step=1, value=0, key=f"adv_sl_qty_{i}"))
                    stop_layers.append({"label": f"SL-{i+1}", "price": sp, "qty": sq, "type": "STOP", "status": "NOT PLACED"})

                st.markdown("**Target layers (price + qty)**")
                num_targets = st.number_input("Number of target layers", min_value=1, max_value=10, value=4, key="adv_ntgts")
                target_layers = []
                for i in range(int(num_targets)):
                    c1, c2 = st.columns([2,1])
                    with c1:
                        tp = st.number_input(f"Target Price #{i+1}", min_value=0.0, step=0.05, format="%.2f", key=f"adv_tp_price_{i}")
                    with c2:
                        tq = int(st.number_input(f"Qty #{i+1}", min_value=0, step=1, value=0, key=f"adv_tp_qty_{i}"))
                    target_layers.append({"label": f"T-{i+1}", "price": tp, "qty": tq, "type": "TARGET", "status": "NOT PLACED"})

                product_type = st.selectbox("Product Type", ["", "CNC", "INTRADAY", "NORMAL"], key="adv_product")
                remarks = st.text_input("Remarks (optional)", key="adv_remarks")

                preview_btn = st.form_submit_button("Preview plan")

            if preview_btn:
                sum_stops = sum(int(x["qty"]) for x in stop_layers)
                sum_targets = sum(int(x["qty"]) for x in target_layers)
                st.write(f"Position: {total_qty} | Stops sum: {sum_stops} | Targets sum: {sum_targets}")
                if sum_stops != total_qty:
                    st.warning("Sum of stop layer quantities != total position qty.")
                if sum_targets != total_qty:
                    st.warning("Sum of target layer quantities != total position qty.")

                st.markdown("**Planned stops**")
                st.table(_format_layers_table(stop_layers))
                st.markdown("**Planned targets**")
                st.table(_format_layers_table(target_layers))

                # Save plan to session
                st.session_state["_advanced_oco_plan"] = {
                    "symbol": symbol,
                    "exchange": exch,
                    "side": orig_side,
                    "entry_price": float(entry_price),
                    "total_qty": int(total_qty),
                    "stops": stop_layers,
                    "targets": target_layers,
                    "product_type": product_type,
                    "remarks": remarks,
                    "placed_at": None,
                    "exited_qty": 0,
                }
                st.success("✅ Plan saved in session. Use 'Place All GTTs' to place to broker.")

            # Manager Controls for saved plan
            if "_advanced_oco_plan" in st.session_state:
                plan = st.session_state["_advanced_oco_plan"]
                st.markdown("---")
                st.subheader("Manager Controls")
                c1, c2, c3 = st.columns([1,1,1])

                if c1.button("▶️ Place All GTTs (stops + targets)", key="adv_place_all"):
                    if not plan["symbol"]:
                        st.error("Trading symbol required.")
                    else:
                        placed_stops = []
                        placed_targets = []
                        for s in plan["stops"]:
                            if plan["side"] == "BUY":
                                condition = "LTP_BELOW"
                                child_side = "SELL"
                            else:
                                condition = "LTP_ABOVE"
                                child_side = "BUY"
                            payload = build_gtt_payload(plan["exchange"], plan["symbol"], condition, float(s["price"]), int(s["qty"]), child_side, float(s["price"]), plan["product_type"], plan["remarks"])
                            if debug:
                                st.write("Placing STOP GTT payload:", payload)
                            resp = _try_client_call(GTT_PLACE_NAMES, payload)
                            alert_id = None
                            if isinstance(resp, dict):
                                for k in ("alert_id","alertId","id","alertID"):
                                    if k in resp:
                                        alert_id = str(resp[k])
                                        break
                            if alert_id is None and resp is not None:
                                alert_id = str(resp)
                            s_record = dict(s)
                            s_record.update({"alert_id": alert_id, "placed_resp": resp, "status": "ACTIVE" if alert_id else ("FAILED" if resp else "FAILED")})
                            placed_stops.append(s_record)
                            time.sleep(0.12)

                        for t in plan["targets"]:
                            if plan["side"] == "BUY":
                                condition = "LTP_ABOVE"
                                child_side = "SELL"
                            else:
                                condition = "LTP_BELOW"
                                child_side = "BUY"
                            payload = build_gtt_payload(plan["exchange"], plan["symbol"], condition, float(t["price"]), int(t["qty"]), child_side, float(t["price"]), plan["product_type"], plan["remarks"])
                            if debug:
                                st.write("Placing TARGET GTT payload:", payload)
                            resp = _try_client_call(GTT_PLACE_NAMES, payload)
                            alert_id = None
                            if isinstance(resp, dict):
                                for k in ("alert_id","alertId","id","alertID"):
                                    if k in resp:
                                        alert_id = str(resp[k])
                                        break
                            if alert_id is None and resp is not None:
                                alert_id = str(resp)
                            t_record = dict(t)
                            t_record.update({"alert_id": alert_id, "placed_resp": resp, "status": "ACTIVE" if alert_id else ("FAILED" if resp else "FAILED")})
                            placed_targets.append(t_record)
                            time.sleep(0.12)

                        plan["stops"] = placed_stops
                        plan["targets"] = placed_targets
                        plan["placed_at"] = datetime.utcnow().isoformat()
                        plan["exited_qty"] = 0
                        st.session_state["_advanced_oco_plan"] = plan
                        st.success("✅ Placed GTTs (response saved). Use Scan Now to reconcile.")
                        st.experimental_rerun()

                if c2.button("🔎 Scan Now (check active GTTs and reconcile)", key="adv_scan_now"):
                    plan = st.session_state.get("_advanced_oco_plan")
                    if not plan:
                        st.error("No plan found.")
                    else:
                        resp = _try_client_call(GTT_LIST_NAMES)
                        if debug:
                            st.write("GTT LIST RAW RESP:", resp)
                        active_ids = _parse_gtt_list(resp)

                        newly_triggered = []
                        for L in plan["stops"] + plan["targets"]:
                            aid = _safe_str(L.get("alert_id"))
                            if aid == "":
                                continue
                            if aid not in active_ids and L.get("status") == "ACTIVE":
                                L["status"] = "TRIGGERED"
                                plan["exited_qty"] += int(L.get("qty", 0))
                                newly_triggered.append(L)

                        remaining_qty = plan["total_qty"] - plan["exited_qty"]
                        if remaining_qty < 0:
                            remaining_qty = 0

                        cum = 0
                        sorted_targets = sorted(plan["targets"], key=lambda x: float(x.get("price", 0.0)), reverse=(plan["side"]=="SELL"))
                        for T in sorted_targets:
                            if T.get("status") != "ACTIVE":
                                if T.get("status") in ("TRIGGERED","KEEP"):
                                    cum += int(T.get("qty", 0))
                                continue
                            next_cum = cum + int(T.get("qty", 0))
                            if next_cum <= remaining_qty:
                                T["status"] = "KEEP"
                                cum = next_cum
                            else:
                                aid = _safe_str(T.get("alert_id"))
                                if aid:
                                    cancel_resp = _try_client_call(GTT_CANCEL_NAMES, aid)
                                    T["status"] = "CANCELLED_BY_MANAGER" if cancel_resp is not None else "CANCEL_FAILED"
                                    T["cancel_resp"] = cancel_resp
                                else:
                                    T["status"] = "NOT_PLACED"

                        if remaining_qty == 0:
                            for L in plan["stops"] + plan["targets"]:
                                if L.get("status") == "ACTIVE":
                                    aid = _safe_str(L.get("alert_id"))
                                    if aid:
                                        cancel_resp = _try_client_call(GTT_CANCEL_NAMES, aid)
                                        L["status"] = "CANCELLED_BY_MANAGER" if cancel_resp is not None else "CANCEL_FAILED"
                                        L["cancel_resp"] = cancel_resp
                                    else:
                                        L["status"] = "NOT_PLACED"

                        st.session_state["_advanced_oco_plan"] = plan
                        st.success(f"Scan completed. Remaining qty: {remaining_qty}. Newly triggered: {len(newly_triggered)}.")

                if c3.button("⛔ Cancel All Remaining GTTs (manager)", key="adv_cancel_all"):
                    plan = st.session_state.get("_advanced_oco_plan")
                    if plan:
                        cancelled = 0
                        for L in plan["stops"] + plan["targets"]:
                            if L.get("status") in ("ACTIVE","KEEP"):
                                aid = _safe_str(L.get("alert_id"))
                                if aid:
                                    cancel_resp = _try_client_call(GTT_CANCEL_NAMES, aid)
                                    if cancel_resp is not None:
                                        L["status"] = "CANCELLED_BY_MANAGER"
                                        L["cancel_resp"] = cancel_resp
                                        cancelled += 1
                                    else:
                                        L["status"] = "CANCEL_FAILED"
                        st.session_state["_advanced_oco_plan"] = plan
                        st.success(f"Requested cancel for {cancelled} alerts.")

                # Manual controls panel
                st.markdown("---")
                st.subheader("Manual Controls (mark triggered / cancel)")
                plan = st.session_state.get("_advanced_oco_plan", {})
                if plan:
                    for L in plan["stops"] + plan["targets"]:
                        cols = st.columns([2,1,1,1])
                        cols[0].write(f"**{L.get('label')}** | price: {L.get('price')} | qty: {L.get('qty')}")
                        cols[1].write(f"Status: {L.get('status')}")
                        if cols[2].button("Mark Triggered", key=f"mark_trig_{plan.get('symbol')}_{L.get('label')}"):
                            if L.get("status") not in ("TRIGGERED",):
                                L["status"] = "TRIGGERED"
                                plan["exited_qty"] = plan.get("exited_qty",0) + int(L.get("qty",0))
                                st.session_state["_advanced_oco_plan"] = plan
                                st.experimental_rerun()
                        if cols[3].button("Cancel Alert", key=f"cancel_{plan.get('symbol')}_{L.get('label')}"):
                            aid = _safe_str(L.get("alert_id"))
                            if aid:
                                cancel_resp = _try_client_call(GTT_CANCEL_NAMES, aid)
                                L["status"] = "CANCELLED_BY_USER" if cancel_resp is not None else "CANCEL_FAILED"
                                L["cancel_resp"] = cancel_resp
                            else:
                                L["status"] = "NOT_PLACED"
                            st.session_state["_advanced_oco_plan"] = plan
                            st.experimental_rerun()

                # status display
                if "_advanced_oco_plan" in st.session_state:
                    plan = st.session_state["_advanced_oco_plan"]
                    st.markdown("---")
                    st.write("**Plan summary**")
                    st.write({
                        "symbol": plan.get("symbol"),
                        "side": plan.get("side"),
                        "entry_price": plan.get("entry_price"),
                        "total_qty": plan.get("total_qty"),
                        "placed_at": plan.get("placed_at"),
                        "exited_qty": plan.get("exited_qty"),
                    })
                    st.write("Stops")
                    st.table(_format_layers_table(plan.get("stops", [])))
                    st.write("Targets")
                    st.table(_format_layers_table(plan.get("targets", [])))
                    st.markdown("---")
                    st.info("Notes: 'KEEP' = manager kept that target (fits remaining qty). 'CANCELLED_BY_MANAGER' = manager requested cancellation.")

    except Exception as e:
        st.error(f"Advanced OCO block error: {e}")
        st.text(traceback.format_exc())

# -------------------- End of page --------------------
