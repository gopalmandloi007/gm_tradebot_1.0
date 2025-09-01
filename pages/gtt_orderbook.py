# pages/gtt_orderbook.py
import streamlit as st
import pandas as pd
import traceback

st.header("⏰ GTT & OCO Order Book — Definedge")

client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

debug = st.checkbox("Show debug info", value=False)

# ---- Helpers ----
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

def _is_oco_row(row: pd.Series) -> bool:
    # Treat as OCO if any OCO-specific fields have non-null values
    for key in ["target_price", "stoploss_price", "target_quantity", "stoploss_quantity",
                "target_trigger", "stoploss_trigger"]:
        if key in row and pd.notna(row[key]) and str(row[key]).strip() != "":
            return True
    return False

def _safe_str(x, default=""):
    return default if x is None else str(x)

try:
    resp = client.gtt_orders()  # GTT + OCO orders API

    if debug:
        st.write("🔎 Raw API response:", resp)

    if not isinstance(resp, dict) or resp.get("status") != "SUCCESS":
        st.error(f"❌ API returned non-success status. Full response: {resp}")
        st.stop()

    rows = resp.get("pendingGTTOrderBook") or []

    if not rows:
        st.info("✅ No pending GTT / OCO orders found.")
        st.stop()

    # Build DataFrame
    df = pd.DataFrame(rows)

    # Detect order kind
    df["order_kind"] = df.apply(_is_oco_row, axis=1).map(lambda v: "OCO" if v else "GTT")

    # Preferred column order (union of common, GTT, OCO)
    preferred_cols = [
        # Common
        "alert_id", "order_time", "tradingsymbol", "exchange", "token",
        "order_type", "product_type", "quantity", "lotsize", "remarks",
        # GTT specific
        "condition", "price_type", "trigger_price", "alert_price", "price",
        # OCO specific
        "target_quantity", "stoploss_quantity",
        "target_price", "stoploss_price",
        "target_trigger", "stoploss_trigger",
        # Kind
        "order_kind"
    ]
    cols = [c for c in preferred_cols if c in df.columns] + \
           [c for c in df.columns if c not in preferred_cols]
    df = df[cols]

    # Top-level search / filter
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

    # Download CSV
    csv = filt.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download (CSV)", csv, "gtt_oco_orders.csv", "text/csv")

    st.markdown("---")
    st.subheader("⚡ Quick Actions (Modify / Cancel)")

    # Tabs for GTT vs OCO for a cleaner UX
    gtt_tab, oco_tab = st.tabs(["📌 GTT Orders", "🎯 OCO Orders"])

    # --------- GTT TAB ----------
    with gtt_tab:
        gtt_df = filt[filt["order_kind"] == "GTT"]
        if gtt_df.empty:
            st.info("No GTT orders in current filter.")
        else:
            # Collect distinct options for selects
            conditions_in_data = sorted(
                list({c for c in gtt_df.get("condition", pd.Series(dtype=str)).dropna().unique()})
            )
            # Provide sane defaults if missing in data
            common_condition_options = sorted(list(set(conditions_in_data + ["LTP_ABOVE", "LTP_BELOW"])))
            product_options = ["CNC", "INTRADAY", "NORMAL"]

            for idx, row in gtt_df.reset_index(drop=True).iterrows():
                st.markdown("---")
                with st.container():
                    st.write(
                        f"**{row.get('tradingsymbol','')}** | `{row.get('exchange','')}` | "
                        f"Alert ID: `{row.get('alert_id','')}` | "
                        f"Order Type: **{row.get('order_type','')}** | Qty: **{row.get('quantity','')}** | "
                        f"Price: **{row.get('price','')}** | Alert/Trigger: **{row.get('alert_price', row.get('trigger_price',''))}** | "
                        f"Condition: **{row.get('condition','')}** | Time: {row.get('order_time','')}"
                    )
                    c1, c2 = st.columns([3, 1])

                    # MODIFY
                    with c1:
                        with st.form(key=f"gtt_modify_{row['alert_id']}"):
                            mc1, mc2, mc3 = st.columns(3)
                            with mc1:
                                m_order_type = st.selectbox(
                                    "Order Type", ["BUY", "SELL"],
                                    index=(0 if str(row.get("order_type","")).upper() != "SELL" else 1),
                                    key=f"gtt_ordertype_{row['alert_id']}"
                                )
                            with mc2:
                                m_product = st.selectbox(
                                    "Product Type", product_options,
                                    index=(product_options.index(str(row.get("product_type","NORMAL"))) 
                                           if str(row.get("product_type","NORMAL")) in product_options else 2),
                                    key=f"gtt_product_{row['alert_id']}"
                                )
                            with mc3:
                                m_condition = st.selectbox(
                                    "Condition", common_condition_options,
                                    index=(common_condition_options.index(str(row.get("condition","LTP_ABOVE")))
                                           if str(row.get("condition","LTP_ABOVE")) in common_condition_options else 0),
                                    key=f"gtt_condition_{row['alert_id']}"
                                )

                            q1, q2, q3 = st.columns(3)
                            with q1:
                                m_qty = st.number_input(
                                    "Quantity", min_value=1, step=1,
                                    value=_to_int(row.get("quantity"), 1),
                                    key=f"gtt_qty_{row['alert_id']}"
                                )
                            with q2:
                                m_alert_price = st.number_input(
                                    "Alert / Trigger Price", min_value=0.0, step=0.05,
                                    value=_to_float(row.get("alert_price", row.get("trigger_price", row.get("price"))), 0.0),
                                    key=f"gtt_alert_{row['alert_id']}"
                                )
                            with q3:
                                m_price = st.number_input(
                                    "Order Price", min_value=0.0, step=0.05,
                                    value=_to_float(row.get("price"), 0.0),
                                    key=f"gtt_price_{row['alert_id']}"
                                )

                            submitted = st.form_submit_button("🚀 Modify GTT")
                            if submitted:
                                try:
                                    payload = {
                                        "exchange": _safe_str(row.get("exchange")),
                                        "alert_id": _safe_str(row.get("alert_id")),
                                        "tradingsymbol": _safe_str(row.get("tradingsymbol")),
                                        "condition": _safe_str(m_condition),
                                        "alert_price": _safe_str(m_alert_price),
                                        "order_type": _safe_str(m_order_type),
                                        "quantity": _safe_str(m_qty),
                                        "price": _safe_str(m_price),
                                        "product_type": _safe_str(m_product or "NORMAL"),
                                    }
                                    if debug:
                                        st.write("🔧 GTT Modify Payload:", payload)
                                    resp_modify = client.gtt_modify(payload)
                                    st.write(resp_modify)
                                    if resp_modify.get("status") == "SUCCESS":
                                        st.success(f"✅ Modified — Alert ID: {row['alert_id']}")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Modify failed: {resp_modify.get('message', resp_modify)}")
                                except Exception as e:
                                    st.error(f"🚨 Exception while modifying GTT: {e}")
                                    st.text(traceback.format_exc())

                    # CANCEL
                    with c2:
                        if st.button("🛑 Cancel", key=f"gtt_cancel_btn_{row['alert_id']}"):
                            try:
                                resp_cancel = client.gtt_cancel(_safe_str(row.get("alert_id")))
                                st.write(resp_cancel)
                                if resp_cancel.get("status") == "SUCCESS":
                                    st.success(f"✅ Cancelled — Alert ID: {row['alert_id']}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Cancel failed: {resp_cancel.get('message', resp_cancel)}")
                            except Exception as e:
                                st.error(f"🚨 Exception while cancelling GTT: {e}")
                                st.text(traceback.format_exc())

    # --------- OCO TAB ----------
    with oco_tab:
        oco_df = filt[filt["order_kind"] == "OCO"]
        if oco_df.empty:
            st.info("No OCO orders in current filter.")
        else:
            product_options = ["CNC", "INTRADAY", "NORMAL"]

            for idx, row in oco_df.reset_index(drop=True).iterrows():
                st.markdown("---")
                with st.container():
                    st.write(
                        f"**{row.get('tradingsymbol','')}** | `{row.get('exchange','')}` | "
                        f"Alert ID: `{row.get('alert_id','')}` | "
                        f"Order Type: **{row.get('order_type','')}** | "
                        f"Tgt: **{row.get('target_price','')}** ({row.get('target_quantity','')}) | "
                        f"SL: **{row.get('stoploss_price','')}** ({row.get('stoploss_quantity','')}) | "
                        f"Time: {row.get('order_time','')}"
                    )
                    c1, c2 = st.columns([3, 1])

                    # MODIFY
                    with c1:
                        with st.form(key=f"oco_modify_{row['alert_id']}"):
                            mc1, mc2, mc3 = st.columns(3)
                            with mc1:
                                m_order_type = st.selectbox(
                                    "Order Type", ["BUY", "SELL"],
                                    index=(0 if str(row.get("order_type","")).upper() != "SELL" else 1),
                                    key=f"oco_ordertype_{row['alert_id']}"
                                )
                            with mc2:
                                m_product = st.selectbox(
                                    "Product Type", product_options,
                                    index=(product_options.index(str(row.get("product_type","NORMAL")))
                                           if str(row.get("product_type","NORMAL")) in product_options else 2),
                                    key=f"oco_product_{row['alert_id']}"
                                )
                            with mc3:
                                m_remarks = st.text_input(
                                    "Remarks (optional)",
                                    _safe_str(row.get("remarks","")),
                                    key=f"oco_remarks_{row['alert_id']}"
                                )

                            q1, q2, q3, q4 = st.columns(4)
                            with q1:
                                m_tgt_qty = st.number_input(
                                    "Target Qty", min_value=1, step=1,
                                    value=_to_int(row.get("target_quantity"), max(1, _to_int(row.get("quantity"), 1))),
                                    key=f"oco_tqty_{row['alert_id']}"
                                )
                            with q2:
                                m_sl_qty = st.number_input(
                                    "Stoploss Qty", min_value=1, step=1,
                                    value=_to_int(row.get("stoploss_quantity"), max(1, _to_int(row.get("quantity"), 1))),
                                    key=f"oco_sqty_{row['alert_id']}"
                                )
                            with q3:
                                m_tgt_price = st.number_input(
                                    "Target Price", min_value=0.0, step=0.05,
                                    value=_to_float(row.get("target_price"), 0.0),
                                    key=f"oco_tprice_{row['alert_id']}"
                                )
                            with q4:
                                m_sl_price = st.number_input(
                                    "Stoploss Price", min_value=0.0, step=0.05,
                                    value=_to_float(row.get("stoploss_price"), 0.0),
                                    key=f"oco_slprice_{row['alert_id']}"
                                )

                            submitted = st.form_submit_button("🚀 Modify OCO")
                            if submitted:
                                try:
                                    payload = {
                                        "remarks": _safe_str(m_remarks),
                                        "tradingsymbol": _safe_str(row.get("tradingsymbol")),
                                        "exchange": _safe_str(row.get("exchange")),
                                        "order_type": _safe_str(m_order_type),
                                        "target_quantity": _safe_str(m_tgt_qty),
                                        "stoploss_quantity": _safe_str(m_sl_qty),
                                        "target_price": _safe_str(m_tgt_price),
                                        "stoploss_price": _safe_str(m_sl_price),
                                        "alert_id": _safe_str(row.get("alert_id")),
                                        "product_type": _safe_str(m_product or "NORMAL"),
                                    }
                                    if debug:
                                        st.write("🔧 OCO Modify Payload:", payload)

                                    # Requires client.oco_modify() in your client wrapper
                                    resp_modify = client.oco_modify(payload)
                                    st.write(resp_modify)
                                    if resp_modify.get("status") == "SUCCESS":
                                        st.success(f"✅ Modified — Alert ID: {row['alert_id']}")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Modify failed: {resp_modify.get('message', resp_modify)}")
                                except Exception as e:
                                    st.error(f"🚨 Exception while modifying OCO: {e}")
                                    st.text(traceback.format_exc())

                    # CANCEL
                    with c2:
                        if st.button("🛑 Cancel", key=f"ococancel_btn_{row['alert_id']}"):
                            try:
                                # Requires client.oco_cancel() in your client wrapper
                                resp_cancel = client.oco_cancel(_safe_str(row.get("alert_id")))
                                st.write(resp_cancel)
                                if resp_cancel.get("status") == "SUCCESS":
                                    st.success(f"✅ Cancelled — Alert ID: {row['alert_id']}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Cancel failed: {resp_cancel.get('message', resp_cancel)}")
                            except Exception as e:
                                st.error(f"🚨 Exception while cancelling OCO: {e}")
                                st.text(traceback.format_exc())

    # ---- Manual Action Section (optional) ----
    st.markdown("---")
    st.subheader("🛠️ Manual Action (by Alert ID)")

    tab_mgtt, tab_moco = st.tabs(["✏️ Modify/Cancel GTT", "✏️ Modify/Cancel OCO"])

    with tab_mgtt:
        with st.form("manual_gtt"):
            mg_alert = st.text_input("Alert ID").strip()
            mg_action = st.radio("Action", ["Modify", "Cancel"], horizontal=True)
            c1, c2, c3 = st.columns(3)
            with c1:
                mg_ordertype = st.selectbox("Order Type", ["BUY", "SELL"])
            with c2:
                mg_product = st.selectbox("Product Type", ["CNC", "INTRADAY", "NORMAL"], index=2)
            with c3:
                # Pull distinct conditions from df for convenience
                cond_opts = sorted(list({c for c in df.get("condition", pd.Series(dtype=str)).dropna().unique()} | {"LTP_ABOVE", "LTP_BELOW"}))
                mg_cond = st.selectbox("Condition", cond_opts, index=cond_opts.index("LTP_ABOVE") if "LTP_ABOVE" in cond_opts else 0)
            q1, q2, q3, q4 = st.columns(4)
            with q1:
                mg_symbol = st.text_input("Trading Symbol (e.g., TCS-EQ)")
            with q2:
                mg_exch = st.text_input("Exchange", value="NSE")
            with q3:
                mg_qty = st.number_input("Quantity", min_value=1, step=1, value=1)
            with q4:
                mg_alert_price = st.number_input("Alert / Trigger Price", min_value=0.0, step=0.05, value=0.0)
            p1 = st.number_input("Order Price", min_value=0.0, step=0.05, value=0.0)

            submitted = st.form_submit_button("Submit")
            if submitted and mg_alert:
                try:
                    if mg_action == "Cancel":
                        resp_cancel = client.gtt_cancel(mg_alert)
                        st.write(resp_cancel)
                        if resp_cancel.get("status") == "SUCCESS":
                            st.success(f"✅ Cancelled — Alert ID: {mg_alert}")
                        else:
                            st.error(f"❌ Cancel failed: {resp_cancel.get('message', resp_cancel)}")
                    else:
                        payload = {
                            "exchange": mg_exch,
                            "alert_id": mg_alert,
                            "tradingsymbol": mg_symbol,
                            "condition": mg_cond,
                            "alert_price": str(mg_alert_price),
                            "order_type": mg_ordertype,
                            "quantity": str(int(mg_qty)),
                            "price": str(p1),
                            "product_type": mg_product
                        }
                        if debug:
                            st.write("🔧 Manual GTT Modify Payload:", payload)
                        resp_modify = client.gtt_modify(payload)
                        st.write(resp_modify)
                        if resp_modify.get("status") == "SUCCESS":
                            st.success(f"✅ Modified — Alert ID: {mg_alert}")
                        else:
                            st.error(f"❌ Modify failed: {resp_modify.get('message', resp_modify)}")
                except Exception as e:
                    st.error(f"🚨 Manual GTT action failed: {e}")
                    st.text(traceback.format_exc())

    with tab_moco:
        with st.form("manual_oco"):
            mo_alert = st.text_input("Alert ID ").strip()
            mo_action = st.radio("Action", ["Modify", "Cancel"], horizontal=True)
            c1, c2, c3 = st.columns(3)
            with c1:
                mo_ordertype = st.selectbox("Order Type", ["BUY", "SELL"])
            with c2:
                mo_product = st.selectbox("Product Type", ["CNC", "INTRADAY", "NORMAL"], index=2)
            with c3:
                mo_remarks = st.text_input("Remarks (optional)", value="")
            q1, q2, q3, q4 = st.columns(4)
            with q1:
                mo_symbol = st.text_input("Trading Symbol (e.g., NIFTY29MAR23F)")
            with q2:
                mo_exch = st.text_input("Exchange", value="NFO")
            with q3:
                mo_tqty = st.number_input("Target Qty", min_value=1, step=1, value=1)
            with q4:
                mo_sqty = st.number_input("Stoploss Qty", min_value=1, step=1, value=1)
            p1, p2 = st.columns(2)
            with p1:
                mo_tprice = st.number_input("Target Price", min_value=0.0, step=0.05, value=0.0)
            with p2:
                mo_slprice = st.number_input("Stoploss Price", min_value=0.0, step=0.05, value=0.0)

            submitted = st.form_submit_button("Submit")
            if submitted and mo_alert:
                try:
                    if mo_action == "Cancel":
                        resp_cancel = client.oco_cancel(mo_alert)  # Ensure this exists in your client
                        st.write(resp_cancel)
                        if resp_cancel.get("status") == "SUCCESS":
                            st.success(f"✅ Cancelled — Alert ID: {mo_alert}")
                        else:
                            st.error(f"❌ Cancel failed: {resp_cancel.get('message', resp_cancel)}")
                    else:
                        payload = {
                            "remarks": mo_remarks,
                            "tradingsymbol": mo_symbol,
                            "exchange": mo_exch,
                            "order_type": mo_ordertype,
                            "target_quantity": str(int(mo_tqty)),
                            "stoploss_quantity": str(int(mo_sqty)),
                            "target_price": str(mo_tprice),
                            "stoploss_price": str(mo_slprice),
                            "alert_id": mo_alert,
                            "product_type": mo_product
                        }
                        if debug:
                            st.write("🔧 Manual OCO Modify Payload:", payload)
                        resp_modify = client.oco_modify(payload)  # Ensure this exists in your client
                        st.write(resp_modify)
                        if resp_modify.get("status") == "SUCCESS":
                            st.success(f"✅ Modified — Alert ID: {mo_alert}")
                        else:
                            st.error(f"❌ Modify failed: {resp_modify.get('message', resp_modify)}")
                except Exception as e:
                    st.error(f"🚨 Manual OCO action failed: {e}")
                    st.text(traceback.format_exc())

except Exception as e:
    st.error(f"⚠️ GTT/OCO order fetch failed: {e}")
    st.text(traceback.format_exc())
