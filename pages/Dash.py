# final_holdings_dashboard_full.py
import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta, date
import plotly.graph_objects as go
import requests

st.set_page_config(layout="wide")
st.title("📊 Trading Dashboard — Definedge (Full Version)")

# ------------------ Defaults ------------------
DEFAULT_TOTAL_CAPITAL = 1400000
DEFAULT_INITIAL_SL_PCT = 2.0
DEFAULT_TARGETS = [10, 20, 30, 40]

# ------------------ Helpers ------------------
def safe_float(x):
    try:
        if x is None: return None
        s = str(x).replace(",", "").strip()
        return float(s) if s else None
    except: return None


def find_in_nested(obj, keys):
    if obj is None: return None
    if isinstance(obj, dict):
        klower = {kk.lower() for kk in keys}
        for k, v in obj.items():
            if k is None: continue
            if str(k).lower() in klower: return v
            res = find_in_nested(v, keys)
            if res is not None: return res
    elif isinstance(obj, (list, tuple)):
        for it in obj:
            res = find_in_nested(it, keys)
            if res is not None: return res
    return None


def parse_definedge_csv_text(csv_text: str) -> pd.DataFrame:
    try:
        df_raw = pd.read_csv(io.StringIO(csv_text), header=None, dtype=str)
        if df_raw.shape[1] < 6: return pd.DataFrame(columns=["DateTime","Close"])
        df = df_raw.rename(columns={0:"DateTime",1:"Open",2:"High",3:"Low",4:"Close",5:"Volume"})
        df['DateTime_parsed'] = pd.to_datetime(df['DateTime'], format="%d%m%Y%H%M", errors='coerce')
        if df['DateTime_parsed'].isna().all():
            df['DateTime_parsed'] = pd.to_datetime(df['DateTime'], format="%d%m%Y", errors='coerce')
        df['Close'] = pd.to_numeric(df['Close'].str.replace(',', ''), errors='coerce')
        return df[['DateTime_parsed','Close']].dropna(subset=['DateTime_parsed']).rename(columns={'DateTime_parsed':'DateTime'}).sort_values('DateTime').reset_index(drop=True)
    except:
        return pd.DataFrame(columns=["DateTime","Close"])


def fetch_hist_for_date_range(api_key: str, segment: str, token: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    url = f"https://data.definedgesecurities.com/sds/history/{segment}/{token}/day/{start_date.strftime('%d%m%Y')}0000/{end_date.strftime('%d%m%Y')}1530"
    headers = {"Authorization": api_key}
    try:
        resp = requests.get(url, headers=headers, timeout=25)
        if resp.status_code == 200 and resp.text.strip():
            return parse_definedge_csv_text(resp.text)
    except:
        pass
    return pd.DataFrame()


def get_robust_prev_close_from_hist(hist_df: pd.DataFrame, today_date: date):
    try:
        if hist_df.empty: return None,'no_data'
        df = hist_df.dropna(subset=['DateTime','Close']).copy()
        df['date_only'] = df['DateTime'].dt.date
        prev_dates = sorted([d for d in df['date_only'].unique() if d < today_date])
        if prev_dates:
            prev_rows = df[df['date_only']==prev_dates[-1]].sort_values('DateTime')
            return float(prev_rows['Close'].iloc[-1]), f'prev_trading_date:{prev_dates[-1]}'
        closes = df['Close'].dropna().tolist()
        return float(closes[-1]), 'last_available' if closes else (None,'no_closes')
    except Exception as e:
        return None,f'error:{str(e)[:120]}'

# ------------------ MAIN ------------------
client = st.session_state.get('client')
if not client:
    st.error('⚠️ Not logged in. Please login first from the Login page.')
    st.stop()

debug = st.sidebar.checkbox('Show debug', value=False)
use_definedge_api_key = st.sidebar.checkbox('Use Definedge API key for history fetch', value=False)
if use_definedge_api_key:
    st.sidebar.text_input('Definedge API key (session_state)', key='definedge_api_key_input')

capital = st.sidebar.number_input('Total Capital (₹)', value=DEFAULT_TOTAL_CAPITAL, step=10000)
initial_sl_pct = st.sidebar.number_input('Initial Stop Loss (%)', value=DEFAULT_INITIAL_SL_PCT, min_value=0.1, max_value=50.0, step=0.1)/100
targets_input = st.sidebar.text_input('Targets % (comma separated)', ','.join(map(str, DEFAULT_TARGETS)))
try:
    target_pcts = sorted([max(0.0,float(t.strip())/100.0) for t in targets_input.split(',') if t.strip()])
    if not target_pcts: target_pcts=[t/100.0 for t in DEFAULT_TARGETS]
except: target_pcts=[t/100.0 for t in DEFAULT_TARGETS]
trailing_thresholds = target_pcts

# ------------------ Fetch Holdings ------------------
try:
    holdings_resp = client.get_holdings()
    if debug: st.write("Raw holdings:", holdings_resp if isinstance(holdings_resp,dict) else str(holdings_resp)[:1000])
    if not holdings_resp or holdings_resp.get('status') != 'SUCCESS': st.warning('No holdings'); st.stop()
    raw_holdings = holdings_resp.get('data',[])
    if not raw_holdings: st.info('No holdings'); st.stop()

    rows=[]
    for item in raw_holdings:
        dp_qty = safe_float(item.get('dp_qty')) or 0
        t1_qty = safe_float(item.get('t1_qty')) or 0
        trade_qty = safe_float(item.get('trade_qty')) or safe_float(item.get('holding_used')) or 0
        sell_amt = safe_float(item.get('sell_amt') or item.get('sell_amount') or item.get('sellAmt')) or 0
        avg_buy_price = safe_float(item.get('avg_buy_price') or item.get('average_price')) or 0
        ts_field = item.get('tradingsymbol')
        nse_entry = None
        if isinstance(ts_field,list):
            for ts in ts_field:
                if isinstance(ts,dict) and ts.get('exchange')=='NSE': nse_entry=ts; break
        elif isinstance(ts_field,dict) and ts_field.get('exchange')=='NSE': nse_entry=ts_field
        elif isinstance(ts_field,str): nse_entry={'tradingsymbol':ts_field,'exchange':'NSE','token':item.get('token')}
        if not nse_entry: continue
        rows.append({'symbol':nse_entry.get('tradingsymbol'),'token':nse_entry.get('token') or item.get('token'),'dp_qty':dp_qty,'t1_qty':t1_qty,'trade_qty':int(trade_qty),'sell_amt':sell_amt,'avg_buy_price':avg_buy_price,'raw':item})

    if not rows: st.warning('No NSE holdings'); st.stop()
    df=pd.DataFrame(rows)

    # Aggregate by symbol
    df = df.groupby('symbol',as_index=False).agg({
        'dp_qty':'sum','t1_qty':'sum','trade_qty':'sum','sell_amt':'sum','avg_buy_price':'mean','token':'first'
    })

    df['buy_qty'] = (df['dp_qty']+df['t1_qty']).astype(int)
    df['open_qty'] = (df['buy_qty']-df['trade_qty']).clip(lower=0)
    df['sold_qty'] = df['trade_qty']
    df['quantity'] = df['open_qty']

    # ------------------ Fetch Prices ------------------
    ltp_list=[]
    prev_close_list=[]
    prev_source_list=[]
    today_dt = datetime.now()
    today_date = today_dt.date()
    LTP_KEYS=['ltp','last_price','lastTradedPrice','lastPrice','ltpPrice','last']
    POSSIBLE_PREV_KEYS=['prev_close','previous_close','previousClose','previousClosePrice','prevClose']

    last_hist_df=None
    for idx,row in df.iterrows():
        token = row['token']
        ltp_val=None
        prev_close_val=None
        prev_source=None
        try:
            quote_resp=client.get_quotes(exchange='NSE', token=token)
            found_ltp=find_in_nested(quote_resp,LTP_KEYS)
            ltp_val=safe_float(found_ltp) if found_ltp is not None else 0.0
            found_prev=find_in_nested(quote_resp,POSSIBLE_PREV_KEYS)
            prev_close_val=safe_float(found_prev) if found_prev is not None else None
            prev_source='quote' if prev_close_val is not None else None
        except: ltp_val=0.0; prev_close_val=None

        if prev_close_val is None:
            hist_df=pd.DataFrame()
            if use_definedge_api_key:
                api_key=st.session_state.get('definedge_api_key') or st.session_state.get('definedge_api_key_input')
                if api_key: hist_df=fetch_hist_for_date_range(api_key,'NSE',token,today_dt-timedelta(days=30),today_dt)
            if not hist_df.empty:
                last_hist_df=hist_df.copy()
                prev_close_val,_=get_robust_prev_close_from_hist(hist_df,today_date)
                prev_source='historical'

        ltp_list.append(safe_float(ltp_val) or 0.0)
        prev_close_list.append(prev_close_val)
        prev_source_list.append(prev_source or 'unknown')

    df['ltp']=pd.Series(ltp_list)
    df['prev_close']=pd.Series(prev_close_list)
    df['prev_close_source']=prev_source_list

    # ------------------ PnL ------------------
    df['realized_pnl']=(df['sell_amt']-(df['trade_qty']*df['avg_buy_price']))
    df['unrealized_pnl']=(df['ltp']-df['avg_buy_price'])*df['open_qty']
    df['today_pnL']=(df['ltp']-df['prev_close'])*df['open_qty']
    df['pct_change']=(df['ltp']-df['prev_close'])/df['prev_close']*100
    df['total_pnl']=df['realized_pnl']+df['unrealized_pnl']
    df['invested_value']=df['avg_buy_price']*df['quantity']
    df['current_value']=df['ltp']*df['quantity']
    df['overall_pnl']=df['current_value']-df['invested_value']
    df['capital_allocation_%']=df['invested_value']/capital*100

    # ------------------ Stops/Targets ------------------
    def calc_stops_targets(r):
        avg=r['avg_buy_price']; qty=r['quantity']; ltp=r['ltp']
        if qty==0 or avg==0: return pd.Series({'side':'FLAT','initial_sl_price':0,'tsl_price':0,'targets':[0]*len(target_pcts),'initial_risk':0,'open_risk':0,'realized_if_tsl_hit':0})
        side='LONG' if qty>0 else 'SHORT'
        if side=='LONG':
            initial_sl_price=round(avg*(1-initial_sl_pct),4)
            targets=[round(avg*(1+t),4) for t in target_pcts]
            perc=(ltp/avg-1) if avg>0 else 0
            crossed=[i for i,th in enumerate(trailing_thresholds) if perc>=th]
            tsl_price=round(avg*(1+trailing_thresholds[max(crossed)-1] if crossed else 0),4)
            tsl_price=max(tsl_price,initial_sl_price)
            open_risk=round(max(0,(avg-tsl_price)*qty),2)
            initial_risk=round(max(0,(avg-initial_sl_price)*qty),2)
            realized_if_tsl_hit=round((tsl_price-avg)*qty,2)
        else:
            initial_sl_price=round(avg*(1+initial_sl_pct),4)
            targets=[round(avg*(1-t),4) for t in target_pcts]
            tsl_price=round(avg*(1-0),4); open_risk=0; initial_risk=0; realized_if_tsl_hit=0
        return pd.Series({'side':side,'initial_sl_price':initial_sl_price,'tsl_price':tsl_price,'targets':targets,'initial_risk':initial_risk,'open_risk':open_risk,'realized_if_tsl_hit':realized_if_tsl_hit})

    stops=df.apply(calc_stops_targets,axis=1)
    df=pd.concat([df,stops],axis=1)

    for i,tp in enumerate(target_pcts,start=1):
        df[f'target_{i}_pct']=tp*100
        df[f'target_{i}_price']=df['targets'].apply(lambda lst: lst[i-1] if isinstance(lst,list) and len(lst)>=i else 0)

    # ------------------ Overall KPIs ------------------
    total_invested=df['invested_value'].sum()
    total_current=df['current_value'].sum()
    total_overall_pnl=df['overall_pnl'].sum()
    total_today_pnl=df['today_pnL'].fillna(0).sum()
    total_open_risk=df['open_risk'].sum()

    st.subheader('💰 Overall Summary')
    k1,k2,k3,k4,k5=st.columns(5)
    k1.metric('Total Invested',f'₹{total_invested:,.2f}')
    k2.metric('Total Current',f'₹{total_current:,.2f}')
    k3.metric('Unrealized PnL',f'₹{total_overall_pnl:,.2f}')
    k4.metric('Today PnL',f'₹{total_today_pnl:,.2f}')
    k5.metric('Open Risk (TSL)',f'₹{total_open_risk:,.2f}')

    # ------------------ Charts ------------------
    st.subheader('📊 Capital Allocation & Risk Charts')
    col1,col2=st.columns(2)
    with col1:
        fig=go.Figure(go.Pie(labels=df['symbol'],values=df['invested_value'],hole=0.4))
        fig.update_layout(title='Capital Allocation')
        st.plotly_chart(fig,use_container_width=True)
    with col2:
        fig2=go.Figure(go.Bar(x=df['symbol'],y=df['open_risk'],marker_color='red'))
        fig2.update_layout(title='Open Risk (TSL)')
        st.plotly_chart(fig2,use_container_width=True)

    # ------------------ Positions Table ------------------
    st.subheader('📋 Positions & Risk Table')
    display_cols=['symbol','quantity','open_qty','buy_qty','sold_qty','avg_buy_price','ltp','prev_close','pct_change','today_pnL','realized_pnl','unrealized_pnl','total_pnl','capital_allocation_%','initial_sl_price','tsl_price','initial_risk','open_risk']
    st.dataframe(df[display_cols].sort_values(by='capital_allocation_%',ascending=False).reset_index(drop=True),use_container_width=True)

    # ------------------ Export ------------------
    st.subheader('📥 Export')
    csv_bytes=df.to_csv(index=False).encode('utf-8')
    st.download_button('Download positions with PnL (CSV)',csv_bytes,file_name='positions_pnl.csv',mime='text/csv')

except Exception as e:
    st.error(f'Error: {e}')
    st.text(traceback.format_exc())
