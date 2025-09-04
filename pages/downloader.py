import streamlit as st
import pandas as pd
import io
import zipfile
import requests
import base64
from datetime import datetime, timedelta

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks & Indices (Daily, Full History)")

# ----------------------
# Config
# ----------------------
MASTER_URL = "https://app.definedgesecurities.com/public/allmaster.zip"
MASTER_FILE_COLS = [
    "SEGMENT","TOKEN","SYMBOL","TRADINGSYM","INSTRUMENT","EXPIRY",
    "TICKSIZE","LOTSIZE","OPTIONTYPE","STRIKE","PRICEPREC","MULTIPLIER",
    "ISIN","PRICEMULT","COMPANY"
]
ALLOWED_SEGMENT = "NSE"
ALLOWED_INSTRUMENTS = {"EQ", "BE", "SM", "IDX"}

# ----------------------
# Helper functions
# ----------------------

@st.cache_data(show_spinner=True)
def download_master_df() -> pd.DataFrame:
    r = requests.get(MASTER_URL, timeout=30)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = [n for n in z.namelist() if n.lower().endswith('.csv')][0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f, header=None, dtype=str)
    if df.shape[1] >= len(MASTER_FILE_COLS):
        df.columns = MASTER_FILE_COLS + [f"EXTRA_{i}" for i in range(df.shape[1]-len(MASTER_FILE_COLS))]
    else:
        df.columns = MASTER_FILE_COLS[:df.shape[1]]
    return df

def parse_definedge_csv_text(csv_text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(csv_text), header=None, dtype=str)
    if df.shape[1] < 6:
        return pd.DataFrame()
    df = df.rename(columns={0: "DateTime", 1: "Open", 2: "High", 3: "Low", 4: "Close", 5: "Volume"})
    df = df[["DateTime","Open","High","Low","Close","Volume"]].copy()
    try:
        df["Date"] = pd.to_datetime(df["DateTime"], format="%d%m%Y%H%M").dt.strftime("%d/%m/%Y")
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)
    except Exception:
        # fallback if format fails
        df["Date"] = pd.to_datetime(df["DateTime"], errors='coerce')
    return df

def fetch_hist_for_date_range(api_key: str, segment: str, token: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    from_str = start_date.strftime("%d%m%Y") + "0000"
    to_str = end_date.strftime("%d%m%Y") + "1530"
    url = f"https://data.definedgesecurities.com/sds/history/{segment}/{token}/day/{from_str}/{to_str}"
    headers = {"Authorization": api_key}
    try:
        resp = requests.get(url, headers=headers, timeout=25)
        if resp.status_code == 200 and resp.text.strip():
            return parse_definedge_csv_text(resp.text)
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

def get_github_file_sha(github_token, owner, repo, file_path):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"token {github_token}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("sha")
    return None

def get_existing_data_range(github_token, owner, repo, file_path):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"token {github_token}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        content_b64 = response.json()["content"]
        decoded_bytes = base64.b64decode(content_b64)
        decoded_str = decoded_bytes.decode()
        df = pd.read_csv(io.StringIO(decoded_str))
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)
            min_date = df["Date"].min()
            max_date = df["Date"].max()
            return min_date, max_date, df
    return None, None, pd.DataFrame()

def upload_csv_to_github(file_name, file_bytes, github_token, owner, repo, branch):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_name}"
    sha = get_github_file_sha(github_token, owner, repo, file_name)
    b64_content = base64.b64encode(file_bytes).decode()
    payload = {
        "message": f"Update {file_name}",
        "branch": branch,
        "content": b64_content,
    }
    if sha:
        payload["sha"] = sha
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    response = requests.put(url, json=payload, headers=headers)
    if response.status_code in [200, 201]:
        st.success(f"{file_name} uploaded successfully.")
    else:
        st.error(f"Failed to upload {file_name}: {response.status_code}\n{response.text}")

# ----------------------
# Main UI
# ----------------------

with st.spinner("Downloading master…"):
    master_df = download_master_df()

# Filter master data
df_seg = master_df[master_df["SEGMENT"].astype(str).str.upper() == ALLOWED_SEGMENT]
df_filtered = df_seg[df_seg["INSTRUMENT"].astype(str).str.upper().isin(ALLOWED_INSTRUMENTS)].copy()
st.write(f"Filtered symbols: {len(df_filtered)}")

# User inputs
github_owner = st.text_input("GitHub Username / Organization", value="gopalmandloi007")
github_repo = st.text_input("Repository Name", value="gm_tradebot_1.0")
github_branch = st.text_input("Branch", value="main")
github_token = st.text_input("GitHub Personal Access Token", type="password")

# API key input
client = st.session_state.get("client", None)
def get_api_session_key_from_client(client_obj):
    if client_obj is None:
        return None
    for a in ["api_session_key", "api_key", "session_key", "token"]:
        if hasattr(client_obj, a):
            val = getattr(client_obj, a)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None

api_key = get_api_session_key_from_client(client)

if not api_key:
    api_key_input = st.text_input("Definedge API Session Key", type="password")
    if api_key_input:
        class ClientObj:
            def __init__(self, key):
                self.api_session_key = key
        st.session_state["client"] = ClientObj(api_key_input)
        api_key = api_key_input

# Set full date range (last 5 years)
start_date_full = datetime.today() - timedelta(days=365*5)
end_date_full = datetime.today()

# Part size input
if len(df_filtered) > 0:
    part_size = st.number_input("Part size", min_value=10, max_value=2000, value=300, step=50)
    def chunk_df(df, size):
        return [df.iloc[i:i + size] for i in range(0, len(df), size)]
    parts = chunk_df(df_filtered.reset_index(drop=True), int(part_size))
    st.subheader(f"Parts: {len(parts)} (≈ {part_size} symbols each)")

    # Loop through parts
    for idx, part_df in enumerate(parts):
        if st.button(f"Download Part {idx+1} ({len(part_df)} symbols)"):
            if not api_key:
                st.error("❌ Please enter API Session Key first.")
            elif not github_token or not github_owner or not github_repo:
                st.error("❌ Please fill in GitHub repo details and token.")
            else:
                for _, row in part_df.iterrows():
                    token = str(row["TOKEN"])
                    sym = str(row.get("TRADINGSYM") or row["SYMBOL"])
                    folder_path = "data/historical/"
                    file_path = f"{folder_path}{sym}_{token}.csv"

                    # Check existing data range
                    existing_min, existing_max, existing_df = get_existing_data_range(github_token, github_owner, github_repo, file_path)

                    # Fetch latest data (full 5 years)
                    df_full = fetch_hist_for_date_range(api_key, ALLOWED_SEGMENT, token, start_date_full, end_date_full)

                    if not df_full.empty:
                        df_full["Date"] = pd.to_datetime(df_full["Date"], errors='coerce')
                        if existing_df.empty:
                            # No existing file, upload full data
                            final_df = df_full
                        else:
                            # Existing file present
                            # Check if new data available
                            if df_full["Date"].max() > existing_max:
                                # Append only new data
                                final_df = pd.concat([existing_df, df_full[df_full["Date"] > existing_max]], ignore_index=True)
                                final_df = final_df.drop_duplicates(subset=["Date"])
                            else:
                                # No new data
                                final_df = existing_df
                        # Save to github
                        csv_bytes = final_df.to_csv(index=False).encode("utf-8")
                        upload_csv_to_github(file_path, csv_bytes, github_token, github_owner, github_repo, github_branch)
                    else:
                        st.warning(f"No data fetched for {sym} from API.")
                st.success("Selected parts uploaded successfully.")

# Upload all at once button
if st.button("⬇️ Upload ALL to GitHub"):
    if not api_key:
        st.error("❌ Please enter API Session Key first.")
    elif not github_token or not github_owner or not github_repo:
        st.error("❌ Please fill in GitHub repo details and token.")
    else:
        for _, row in df_filtered.iterrows():
            token = str(row["TOKEN"])
            sym = str(row.get("TRADINGSYM") or row["SYMBOL"])
            folder_path = "data/historical/"
            file_path = f"{folder_path}{sym}_{token}.csv"

            # Check existing data
            existing_min, existing_max, existing_df = get_existing_data_range(github_token, github_owner, github_repo, file_path)

            # Fetch full data
            df_full = fetch_hist_for_date_range(api_key, ALLOWED_SEGMENT, token, start_date_full, end_date_full)

            if not df_full.empty:
                df_full["Date"] = pd.to_datetime(df_full["Date"], errors='coerce')
                if existing_df.empty:
                    # No file, upload full data
                    final_df = df_full
                else:
                    # File exists, check if update needed
                    if df_full["Date"].max() > existing_max:
                        final_df = pd.concat([existing_df, df_full[df_full["Date"] > existing_max]], ignore_index=True)
                        final_df = final_df.drop_duplicates(subset=["Date"])
                    else:
                        final_df = existing_df
                # Save to github
                csv_bytes = final_df.to_csv(index=False).encode("utf-8")
                upload_csv_to_github(file_path, csv_bytes, github_token, github_owner, github_repo, github_branch)
            else:
                st.warning(f"No data fetched for {sym} from API.")
        st.success("All files processed and uploaded.")
