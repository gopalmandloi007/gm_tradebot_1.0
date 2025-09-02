import streamlit as st
import pandas as pd
import io, zipfile
from datetime import datetime, timedelta
import traceback

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks (Daily)")

# ------------------ Utilities ------------------
def read_hist_csv_to_df(hist_csv: str) -> pd.DataFrame:
    if not hist_csv or not hist_csv.strip():
        return pd.DataFrame()
    lines = hist_csv.strip().splitlines()
    if not lines:
        return pd.DataFrame()
    try:
        df = pd.read_csv(io.StringIO(hist_csv), header=None)
    except Exception:
        try:
            df = pd.read_csv(io.StringIO(hist_csv), header=None, delim_whitespace=True)
        except:
            return pd.DataFrame()
    # Assign columns
    if df.shape[1] >= 6:
        if df.shape[1] == 7:
            df.columns = ["DateTime","Open","High","Low","Close","Volume","OI"]
        else:
            df.columns = ["DateTime","Open","High","Low","Close","Volume"]
    else:
        return pd.DataFrame()
    # Clean DateTime strings
    df["DateTime"] = pd.to_datetime(df["DateTime"].astype(str).str.strip(), format="%d%m%Y%H%M", errors="coerce")
    df = df.dropna(subset=["DateTime"])
    for col in ["Open","High","Low","Close","Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # Keep last row per day
    df["Date"] = df["DateTime"].dt.normalize()
    df = df.sort_values("DateTime").drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)
    df["DateStr"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df[["DateTime","Date","DateStr","Open","High","Low","Close","Volume"]]

def fetch_historical(client, segment, token, days):
    today = datetime.today()
    frm = (today - timedelta(days=days+30)).strftime("%d%m%Y%H%M")
    to = today.strftime("%d%m%Y%H%M")
    try:
        raw = client.historical_csv(segment=segment, token=token, timeframe="day", frm=frm, to=to)
    except Exception as e:
        st.warning(f"Failed API for token {token}: {e}")
        return pd.DataFrame()
    return read_hist_csv_to_df(str(raw))

# ------------------ Master File ------------------
@st.cache_data
def load_master(path="data/master/allmaster.csv"):
    return pd.read_csv(path)

df_master = load_master()
nse_df = df_master[df_master["SEGMENT"]=="NSE"]

# ------------------ User Inputs ------------------
days_back = st.number_input("Number of days to fetch", min_value=30, max_value=2000, value=365)
symbols_list = st.multiselect("Select symbols (or leave empty for all NSE EQ+IDX)", nse_df["TRADINGSYM"].tolist())

if st.button("Fetch & Download Historical CSVs"):
    client = st.session_state.get("client")
    if not client:
        st.error("Not logged in (client missing).")
        st.stop()

    if not symbols_list:
        symbols_list = nse_df["TRADINGSYM"].tolist()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for sym in symbols_list:
            try:
                token = int(nse_df[nse_df["TRADINGSYM"]==sym]["TOKEN"].values[0])
                df = fetch_historical(client, "NSE", token, days_back)
                if df.empty:
                    st.warning(f"No data for {sym}")
                    continue
                csv_bytes = df.to_csv(index=False).encode("utf-8")
                zf.writestr(f"{sym}.csv", csv_bytes)
                st.success(f"{sym} fetched: {len(df)} rows")
            except Exception as e:
                st.warning(f"{sym} error: {e}\n{traceback.format_exc()}")
    st.download_button("📥 Download ZIP of CSVs", data=zip_buffer.getvalue(), file_name="nse_ohlcv.zip", mime="application/zip")
