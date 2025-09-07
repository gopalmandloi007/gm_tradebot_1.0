# -------------------- Advanced Multi-tier OCO --------------------
import time
from datetime import datetime
import json

# Helper to try calling different client method names
def _try_client_call(method_names, *args, **kwargs):
    for name in method_names:
        fn = getattr(client, name, None)
        if callable(fn):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                # try next candidate if method present but failing
                if debug:
                    st.warning(f"client.{name} failed: {e}")
                continue
    return None

# Candidates (extend if your client uses other names)
GTT_PLACE_NAMES = ["gtt_place", "place_gtt", "gtt_create", "create_gtt"]
GTT_LIST_NAMES = ["gtt_list", "get_gtts", "gtt_fetch_all", "list_gtts", "get_gtt_alerts"]
GTT_CANCEL_NAMES = ["gtt_cancel", "gtt_delete", "gtt_remove", "cancel_gtt", "delete_gtt"]

# Parses a returned GTT list into a set of active alert ids
def _parse_gtt_list(resp):
    active_ids = set()
    if resp is None:
        return active_ids
    # many clients return dict with 'data' or 'alerts' or just a list
    entries = []
    if isinstance(resp, dict):
        # try common keys
        for k in ("data", "alerts", "alerts_list", "gtts", "items", "result"):
            if k in resp and isinstance(resp[k], (list, tuple)):
                entries = resp[k]
                break
        if not entries:
            # maybe dict directly maps to list-like
            # sometimes response is {"status":"success","list":[{...}]}
            for v in resp.values():
                if isinstance(v, (list, tuple)):
                    entries = v
                    break
    elif isinstance(resp, (list, tuple)):
        entries = resp

    # now extract ids
    for item in entries:
        if not isinstance(item, dict):
            continue
        for id_key in ("alert_id", "id", "alertId", "alertID"):
            if id_key in item:
                try:
                    active_ids.add(str(item[id_key]))
                except:
                    pass
                break
    # fallback: sometimes entries are simple strings/ints
    if not active_ids and isinstance(entries, (list, tuple)):
        for item in entries:
            if isinstance(item, (str, int)):
                active_ids.add(str(item))
    return active_ids

# small util to format layers to nice table rows
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

# UI: Advanced OCO form
with oco_col:
    with st.expander("🎯 Advanced Multi-tier OCO (Multiple targets + multiple stops)", expanded=True):
        st.markdown("""
        **Behaviour**:
        - Each stop / target is placed as a GTT alert.
        - Manager will **scan broker GTT list** and when an alert disappears we assume it *triggered*.
        - After a stop triggers manager recalculates remaining qty and **cancels target alerts that exceed remaining qty**.
        - You can also manually mark alerts triggered / cancelled if your broker API doesn't list active GTTs.
        """)

        with st.form("advanced_oco_form"):
            tradingsymbol = st.text_input("Trading Symbol (e.g. TCS-EQ)", value="", max_chars=50).strip().upper()
            exchange = st.selectbox("Exchange", ["NSE", "BSE", "NFO", "MCX"], index=0)

            side_choice = st.radio("Original Side (position you have)", ["BUY", "SELL"], horizontal=True)
            st.caption("If you bought (BUY) then targets & stops will place SELL child orders; reverse for SELL.")

            entry_price = st.number_input("Entry Price", min_value=0.0, step=0.05, format="%.2f", value=0.0)
            total_qty = int(st.number_input("Total Qty (position size)", min_value=1, step=1, value=1))

            st.markdown("**Stop layers (price & qty)** — these are protective GTTs (stoploss).")
            num_stops = st.number_input("Number of stop layers", min_value=1, max_value=10, value=2)
            stop_layers = []
            for i in range(int(num_stops)):
                c1, c2 = st.columns([2,1])
                with c1:
                    sp = st.number_input(f"SL Price #{i+1}", min_value=0.0, step=0.05, format="%.2f", key=f"sl_price_{i}")
                with c2:
                    sq = int(st.number_input(f"Qty #{i+1}", min_value=0, step=1, value=0, key=f"sl_qty_{i}"))
                stop_layers.append({"label": f"SL-{i+1}", "price": sp, "qty": sq, "type": "STOP", "status": "NOT PLACED"})

            st.markdown("**Target layers (price & qty)** — these are GTTs that place LIMIT child orders to exit at profit.")
            num_targets = st.number_input("Number of target layers", min_value=1, max_value=10, value=4)
            target_layers = []
            for i in range(int(num_targets)):
                c1, c2 = st.columns([2,1])
                with c1:
                    tp = st.number_input(f"Target Price #{i+1}", min_value=0.0, step=0.05, format="%.2f", key=f"tp_price_{i}")
                with c2:
                    tq = int(st.number_input(f"Qty #{i+1}", min_value=0, step=1, value=0, key=f"tp_qty_{i}"))
                target_layers.append({"label": f"T-{i+1}", "price": tp, "qty": tq, "type": "TARGET", "status": "NOT PLACED"})

            product_type = st.selectbox("Product Type", ["", "CNC", "INTRADAY", "NORMAL"])
            remarks = st.text_input("Remarks (optional)")

            preview_btn = st.form_submit_button("Preview plan")

        if preview_btn:
            # Validation
            sum_stops = sum(int(x["qty"]) for x in stop_layers)
            sum_targets = sum(int(x["qty"]) for x in target_layers)
            st.write(f"Position: {total_qty} | Stops sum: {sum_stops} | Targets sum: {sum_targets}")
            if sum_stops != total_qty:
                st.warning("Sum of stop layer quantities != total position qty. You should ensure stop qtys match total qty.")
            if sum_targets != total_qty:
                st.warning("Sum of target layer quantities != total position qty. You should ensure target qtys match total qty.")
            st.markdown("**Planned stops**")
            st.table(_format_layers_table(stop_layers))
            st.markdown("**Planned targets**")
            st.table(_format_layers_table(target_layers))

            # Save plan to session for placement
            st.session_state["_advanced_oco_plan"] = {
                "symbol": tradingsymbol,
                "exchange": exchange,
                "side": side_choice,
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

        # Place / Manage buttons
        if "_advanced_oco_plan" in st.session_state:
            plan = st.session_state["_advanced_oco_plan"]
            st.markdown("---")
            st.subheader("Manager Controls")
            c1, c2, c3 = st.columns([1,1,1])
            if c1.button("▶️ Place All GTTs (stops + targets)"):
                if not plan["symbol"]:
                    st.error("Trading symbol required.")
                else:
                    # Build and place GTTs for stops and targets
                    placed_stops = []
                    placed_targets = []
                    for s in plan["stops"]:
                        # For BUY original side, stop is SELL when LTP_BELOW; for SELL original side, condition invert
                        if plan["side"] == "BUY":
                            condition = "LTP_BELOW"
                            child_side = "SELL"
                        else:
                            condition = "LTP_ABOVE"
                            child_side = "BUY"
                        # use alert_price = stop price, price (child order limit) = same as price (or use market)
                        payload = build_gtt_payload(plan["exchange"], plan["symbol"], condition, float(s["price"]), int(s["qty"]), child_side, float(s["price"]), plan["product_type"], plan["remarks"])
                        if debug:
                            st.write("Placing STOP GTT payload:", payload)
                        resp = _try_client_call(GTT_PLACE_NAMES, payload)
                        # try to get alert id from resp
                        alert_id = None
                        if isinstance(resp, dict):
                            for k in ("alert_id", "alertId", "id", "alertID"):
                                if k in resp:
                                    alert_id = str(resp[k])
                                    break
                        # fallback: sometimes resp is string/int
                        if alert_id is None and resp is not None:
                            alert_id = str(resp)
                        s_record = dict(s)
                        s_record.update({"alert_id": alert_id, "placed_resp": resp, "status": "ACTIVE" if alert_id else ("FAILED" if resp else "FAILED")})
                        placed_stops.append(s_record)
                        time.sleep(0.15)  # small pause to be nicer to broker

                    for t in plan["targets"]:
                        # For BUY originally, target = SELL when LTP_ABOVE; vice versa for SELL
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
                            for k in ("alert_id", "alertId", "id", "alertID"):
                                if k in resp:
                                    alert_id = str(resp[k])
                                    break
                        if alert_id is None and resp is not None:
                            alert_id = str(resp)
                        t_record = dict(t)
                        t_record.update({"alert_id": alert_id, "placed_resp": resp, "status": "ACTIVE" if alert_id else ("FAILED" if resp else "FAILED")})
                        placed_targets.append(t_record)
                        time.sleep(0.15)

                    # Save details
                    plan["stops"] = placed_stops
                    plan["targets"] = placed_targets
                    plan["placed_at"] = datetime.utcnow().isoformat()
                    plan["exited_qty"] = 0
                    st.session_state["_advanced_oco_plan"] = plan
                    st.success("✅ Placed GTTs (response saved). Use Scan Now to reconcile triggers.")
                    st.experimental_rerun()

            if c2.button("🔎 Scan Now (check active GTTs and reconcile)"):
                if "_advanced_oco_plan" not in st.session_state:
                    st.error("No plan found.")
                else:
                    plan = st.session_state["_advanced_oco_plan"]
                    # get active gtt ids from broker
                    resp = _try_client_call(GTT_LIST_NAMES)
                    if debug:
                        st.write("GTT LIST RAW RESP:", resp)
                    active_ids = _parse_gtt_list(resp)

                    # iterate stored stops + targets and find which disappeared (=> triggered)
                    newly_triggered = []
                    for L in plan["stops"] + plan["targets"]:
                        aid = _safe_str(L.get("alert_id"))
                        if aid == "":
                            continue
                        if aid not in active_ids and L.get("status") == "ACTIVE":
                            # missing => triggered (assumption)
                            L["status"] = "TRIGGERED"
                            plan["exited_qty"] += int(L.get("qty", 0))
                            newly_triggered.append(L)
                    # compute remaining qty
                    remaining_qty = plan["total_qty"] - plan["exited_qty"]
                    if remaining_qty < 0:
                        remaining_qty = 0
                    # cancel targets that exceed remaining_qty
                    cum = 0
                    # order targets in price order depending on side (lowest first for BUY)
                    sorted_targets = sorted(plan["targets"], key=lambda x: float(x["price"]) if x.get("price") else 0.0, reverse=(plan["side"]=="SELL"))
                    for T in sorted_targets:
                        if T.get("status") != "ACTIVE":
                            cum += int(T.get("qty", 0)) if T.get("status") in ("TRIGGERED","KEEP") else 0
                            continue
                        next_cum = cum + int(T.get("qty", 0))
                        if next_cum <= remaining_qty:
                            # keep it
                            T["status"] = "KEEP"
                            cum = next_cum
                        else:
                            # cancel it
                            aid = _safe_str(T.get("alert_id"))
                            if aid:
                                cancel_resp = _try_client_call(GTT_CANCEL_NAMES, aid)
                                T["status"] = "CANCELLED_BY_MANAGER" if cancel_resp is not None else "CANCEL_FAILED"
                                T["cancel_resp"] = cancel_resp
                            else:
                                T["status"] = "NOT_PLACED"
                    # also if remaining_qty == 0 cancel all remaining active stops/targets
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

                    # save back
                    st.session_state["_advanced_oco_plan"] = plan
                    st.success(f"Scan completed. Remaining qty: {remaining_qty}. Newly triggered: {len(newly_triggered)}.")

            if c3.button("⛔ Cancel All Remaining GTTs (manager)"):
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

            # manual control panel for marking triggered/cancelled (useful if client doesn't list GTTs)
            st.markdown("---")
            st.subheader("Manual Controls (if auto-scan doesn't work for your broker)")
            plan = st.session_state.get("_advanced_oco_plan", {})
            if plan:
                for L in plan["stops"] + plan["targets"]:
                    cols = st.columns([2,1,1,1])
                    cols[0].write(f"**{L.get('label')}** | price: {L.get('price')} | qty: {L.get('qty')}")
                    cols[1].write(f"Status: {L.get('status')}")
                    if cols[2].button("Mark Triggered", key=f"mark_trig_{L.get('label')}"):
                        if L.get("status") not in ("TRIGGERED",):
                            L["status"] = "TRIGGERED"
                            plan["exited_qty"] = plan.get("exited_qty",0) + int(L.get("qty",0))
                            st.session_state["_advanced_oco_plan"] = plan
                            st.experimental_rerun()
                    if cols[3].button("Cancel Alert", key=f"cancel_{L.get('label')}"):
                        aid = _safe_str(L.get("alert_id"))
                        if aid:
                            cancel_resp = _try_client_call(GTT_CANCEL_NAMES, aid)
                            L["status"] = "CANCELLED_BY_USER" if cancel_resp is not None else "CANCEL_FAILED"
                            L["cancel_resp"] = cancel_resp
                        else:
                            L["status"] = "NOT_PLACED"
                        st.session_state["_advanced_oco_plan"] = plan
                        st.experimental_rerun()

            # display status tables
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
                st.info("Notes: 'KEEP' status means manager decided to keep that target (fits in remaining qty). 'CANCELLED_BY_MANAGER' means manager requested cancellation to the broker.")

# -------------------- End Advanced Multi-tier OCO --------------------
