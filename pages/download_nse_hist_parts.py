# pages/download_nse_hist_parts.py
import streamlit as st
import pandas as pd
import io, zipfile, requests, time, traceback
from datetime import datetime, timedelta
from typing import List

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks & Indices (Daily, Part-wise)")

MASTER_URL = "https://app.definedgesecurities.com/public/allmaster.zip"
MASTER_FILE_COLS = [
    "SEGMENT","TOKEN","SYMBOL","TRADINGSYM","INSTRUMENT","EXPIRY",
    "TICKSIZE","LOTSIZE","OPTIONTYPE","STRIKE","PRICEPREC","MULTIPLIER",
    "ISIN","PRICEMULT","COMPANY"
]
ALLOWED_SEGMENT = "NSE"
ALLOWED_INSTRUMENTS = {"EQ", "BE", "SM", "IDX"}

if "_hist_cache" not in st.session_state:
    st.session_state["_hist_cache"] = {}
if "_zip_cache" not in st.session_state:
    st.session_state["_zip_cache"] = {}

@st.cache_data(show_spinner=True)
def download_master_df() -> pd.DataFrame:
    r = requests.get(MASTER_URL, timeout=30)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f, header=None, dtype=str)
    if df.shape[1] >= len(MASTER_FILE_COLS):
        df.columns = MASTER_FILE_COLS + [f"EXTRA_{i}" for i in range(df.shape[1]-len(MASTER_FILE_COLS))]
    else:
        df.columns = MASTER_FILE_COLS[:df.shape[1]]
    return df

def clean_hist_df(df: pd.DataFrame) -> pd.DataFrame:
    if "DateTime" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["DateTime"] = pd.to_datetime(df["DateTime"], errors="coerce", dayfirst=True)
    df = df.dropna(subset=["DateTime"])
    for c in ["Open","High","Low","Close","Volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values("DateTime").reset_index(drop=True)
    return df[["DateTime","Open","High","Low","Close","Volume"]]

def sanitize_filename(s: str) -> str:
    if not s: return ""
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        s = s.replace(ch, '_')
    return s.replace(' ', '_')

def chunk_df(df: pd.DataFrame, part_size: int) -> List[pd.DataFrame]:
    return [df.iloc[i:i+part_size].copy() for i in range(0, len(df), part_size)]

def get_api_session_key_from_client(client) -> str:
    if client is None:
        return None
    # 🔑 direct check (Definedge client)
    if hasattr(client, "_api_session_key") and isinstance(client._api_session_key, str):
        return client._api_session_key.strip()
    # generic fallbacks
    for attr in ["api_session_key","api_key","session_key","token","access_token"]:
        if hasattr(client, attr):
            val = getattr(client, attr)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None

def parse_definedge_csv_text(csv_text: str) -> pd.DataFrame:
    if not csv_text or not csv_text.strip():
        return pd.DataFrame()
    try:
        df = pd.read_csv(io.StringIO(csv_text), header=None, dtype=str)
        if df.shape[1] >= 6:
            colmap = {0:"DateTime",1:"Open",2:"High",3:"Low",4:"Close",5:"Volume"}
            df = df.rename(columns=colmap)[list(colmap.values())]
            return clean_hist_df(df)
    except Exception:
        pass
    return pd.DataFrame()

def fetch_hist_from_api(api_key: str, segment: str, token: str, days_back: int,
                        retries: int = 2, timeout: int = 25) -> pd.DataFrame:
    if not api_key or not token: return pd.DataFrame()
    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=days_back)
    from_str = start_dt.strftime("%d%m%Y") + "0000"
    to_str = end_dt.strftime("%d%m%Y") + "1530"
    url = f"https://data.definedgesecurities.com/sds/history/{segment}/{token}/day/{from_str}/{to_str}"
    headers = {"Authorization": api_key}
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code==200 and r.text.strip():
                df = parse_definedge_csv_text(r.text)
                if not df.empty: return df
                return pd.DataFrame()
        except Exception: pass
        time.sleep(0.25*(attempt+1))
    return pd.DataFrame()

def build_zip_for_rows(rows: pd.DataFrame, days_back: int, api_key: str, segment: str,
                       delay_sec: float=0.02, retries: int=2) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        total=len(rows)
        prog=st.progress(0.0)
        for i,(_,row) in enumerate(rows.iterrows(),1):
            token=str(row.get("TOKEN",""))
            trad=row.get("TRADINGSYM") or row.get("SYMBOL") or ""
            fname=sanitize_filename(f"{trad}_{token}")
            cache_key=(token,days_back)
            if cache_key in st.session_state["_hist_cache"]:
                csv_bytes=st.session_state["_hist_cache"][cache_key]
            else:
                df=fetch_hist_from_api(api_key,segment,token,days_back,retries)
                if df.empty:
                    csv_bytes=pd.DataFrame(columns=["DateTime","Open","High","Low","Close","Volume"]).to_csv(index=False).encode()
                else:
                    csv_bytes=df.to_csv(index=False).encode()
                st.session_state["_hist_cache"][cache_key]=csv_bytes
            zf.writestr(f"{fname}.csv",csv_bytes)
            prog.progress(i/total,f"[{i}/{total}] {trad}")
            if delay_sec: time.sleep(delay_sec)
    buf.seek(0)
    return buf

# ------------------ main flow ------------------
with st.spinner("Downloading master file…"):
    master_df=download_master_df()

df_seg=master_df[master_df["SEGMENT"].str.upper()==ALLOWED_SEGMENT]
df_filtered=df_seg[df_seg["INSTRUMENT"].str.upper().isin(ALLOWED_INSTRUMENTS)].drop_duplicates(subset=["TRADINGSYM","TOKEN"]).copy()

st.write(f"Master: {len(master_df)} | After SEGMENT={ALLOWED_SEGMENT}: {len(df_seg)} | After INSTRUMENT filter: {len(df_filtered)}")

c1,c2,c3=st.columns(3)
days_back=c1.number_input("Days back",30,3650,365)
part_size=c2.number_input("Symbols per part",10,2000,300)
delay_sec=c3.number_input("Delay (s)",0.0,5.0,0.02)
retries=st.number_input("Retries",0,5,2)

client=st.session_state.get("client")
api_key=get_api_session_key_from_client(client)
if not api_key:
    api_key=st.text_input("Enter Definedge API Session Key",type="password")

parts=chunk_df(df_filtered.reset_index(drop=True),int(part_size))
st.write(f"Total parts: {len(parts)}")

for idx,p in enumerate(parts,1):
    if st.button(f"Build Part {idx} ({len(p)})"):
        zip_buf=build_zip_for_rows(p,days_back,api_key,ALLOWED_SEGMENT,delay_sec,retries)
        st.download_button(f"⬇️ Download Part {idx}",data=zip_buf,file_name=f"nse_part_{idx:02d}.zip",mime="application/zip")
