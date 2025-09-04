import streamlit as st
import pandas as pd
import io
import zipfile
import requests
import base64
from datetime import datetime, timedelta

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks & Indices (Daily, Part-wise)")

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
        df = df[["Date","Open","High","Low","Close","Volume"]]
    except Exception:
        pass
    return df

def fetch_hist_from_api(api_key: str, segment: str, token: str, days_back: int) -> pd.DataFrame:
    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=days_back)
    from_str = start_dt.strftime("%d%m%Y") + "0000"
    to_str = end_dt.strftime("%d%m%Y") + "1530"
    url = f"https://data.definedgesecurities.com/sds/history/{segment}/{token}/day/{from_str}/{to_str}"
    headers = {"Authorization": api_key}
    resp = requests.get(url, headers=headers, timeout=25)
    if resp.status_code == 200 and resp.text.strip():
        return parse_definedge_csv_text(resp.text)
    return pd.DataFrame()

def upload_csv_to_github(file_name, file_bytes, api_key, owner, repo, branch):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_name}"
    b64_content = base64.b64encode(file_bytes).decode()
    payload = {
        "message": f"Update {file_name}",
        "branch": branch,
        "content": b64_content
    }
    headers = {
        "Authorization": f"token {api_key}",
        "Accept": "application/vnd.github.v3+json"
    }
    response = requests.put(url, json=payload, headers=headers)
    if response.status_code in [200, 201]:
        st.success(f"{file_name} uploaded successfully.")
    else:
        st.error(f"Failed to upload {file_name}: {response.status_code}\n{response.text}")

def get_existing_date_range(github_token, owner, repo, file_path):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"token {github_token}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        content = response.json().get("content", "")
        decoded = base64.b64decode(content).decode()
        df = pd.read_csv(io.StringIO(decoded))
        if not df.empty and "Date" in df.columns:
            min_date = pd.to_datetime(df["Date"], dayfirst=True).min()
            max_date = pd.to_datetime(df["Date"], dayfirst=True).max()
            return min_date, max_date
    return None, None

# ----------------------
# Main UI
# ----------------------
with st.spinner("Downloading master…"):
    master_df = download_master_df()

df_seg = master_df[master_df["SEGMENT"].astype(str).str.upper() == ALLOWED_SEGMENT]
df_filtered = df_seg[df_seg["INSTRUMENT"].astype(str).str.upper().isin(ALLOWED_INSTRUMENTS)].copy()
st.write(f"Filtered rows: {len(df_filtered)}")

# User inputs
days_back = st.number_input("Days back", min_value=10, max_value=3650, value=365)
part_size = st.number_input("Part size", min_value=10, max_value=2000, value=300, step=50)

# GitHub details
github_owner = st.text_input("GitHub Username / Organization", value="gopalmandloi007")
github_repo = st.text_input("Repository Name", value="gm_tradebot_1.0")
github_branch = st.text_input("Branch", value="main")
github_token = st.text_input("GitHub Personal Access Token", type="password")

# API session key
client = st.session_state.get("client")
api_key = get_api_session_key_from_client(client)
if not api_key:
    api_key = st.text_input("Definedge API Session Key", type="password")

# Compute target date range
target_start_date = datetime.today() - timedelta(days=days_back)
target_end_date = datetime.today()

# Split data into parts
if not df_filtered.empty:
    parts = chunk_df(df_filtered.reset_index(drop=True), int(part_size))
    st.subheader(f"Parts: {len(parts)} (≈ {part_size} symbols each)")

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
                    existing_min_date, existing_max_date = get_existing_date_range(github_token, github_owner, github_repo, file_path)

                    # Decide fetch logic based on existing data
                    fetch_earlier = False
                    fetch_later = False

                    if existing_min_date is None or existing_max_date is None:
                        # No existing data, fetch all
                        fetch_earlier = True
                        fetch_later = True
                    else:
                        # Check coverage
                        if existing_min_date > target_start_date:
                            fetch_earlier = True
                        if existing_max_date < target_end_date:
                            fetch_later = True

                    # Fetch missing earlier data
                    if fetch_earlier:
                        days_back_earlier = (existing_min_date - target_start_date).days if existing_min_date else (target_end_date - target_start_date).days
                        df_earlier = fetch_hist_from_api(api_key, ALLOWED_SEGMENT, token, days_back=days_back_earlier)
                        if not df_earlier.empty:
                            df_earlier["Date"] = pd.to_datetime(df_earlier["Date"], dayfirst=True)
                            # Keep only data before current min date
                            df_earlier = df_earlier[df_earlier["Date"] < existing_min_date]
                        else:
                            df_earlier = pd.DataFrame()

                    # Fetch missing later data
                    if fetch_later:
                        days_back_later = (target_end_date - existing_max_date).days if existing_max_date else (target_end_date - target_start_date).days
                        df_later = fetch_hist_from_api(api_key, ALLOWED_SEGMENT, token, days_back=days_back_later)
                        if not df_later.empty:
                            df_later["Date"] = pd.to_datetime(df_later["Date"], dayfirst=True)
                            # Keep only data after current max date
                            df_later = df_later[df_later["Date"] > existing_max_date]
                        else:
                            df_later = pd.DataFrame()

                    # Fetch current data (full range) as fallback
                    df_full = fetch_hist_from_api(api_key, ALLOWED_SEGMENT, token, days_back=days_back_later)
                    if not df_full.empty:
                        df_full["Date"] = pd.to_datetime(df_full["Date"], dayfirst=True)

                    # Merge data
                    dfs_to_concat = []
                    if not df_earlier.empty:
                        dfs_to_concat.append(df_earlier)
                    if not df_full.empty:
                        # Use full data to ensure completeness
                        # But if earlier data exists, retain only the needed parts
                        if fetch_earlier:
                            # Keep only data >= target_start_date
                            df_full = df_full[df_full["Date"] >= target_start_date]
                        if fetch_later:
                            # Keep only data <= target_end_date
                            df_full = df_full[df_full["Date"] <= target_end_date]
                        dfs_to_concat.append(df_full)
                    if not df_later.empty:
                        dfs_to_concat.append(df_later)

                    # Combine all parts
                    if dfs_to_concat:
                        combined_df = pd.concat(dfs_to_concat).drop_duplicates(subset=["Date"]).sort_values("Date")
                        # Save to CSV
                        csv_bytes = combined_df.to_csv(index=False).encode("utf-8")
                        upload_csv_to_github(file_path, csv_bytes, github_token, github_owner, github_repo, github_branch)
                    else:
                        st.warning(f"No new data to update for {sym}.")

                st.success("All CSV files uploaded to GitHub for this part.")

# Option to upload all at once
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

            existing_min_date, existing_max_date = get_existing_date_range(github_token, github_owner, github_repo, file_path)

            # Decide fetch range
            days_back_full = days_back
            df_full = fetch_hist_from_api(api_key, ALLOWED_SEGMENT, token, days_back=days_back_full)
            if not df_full.empty:
                df_full["Date"] = pd.to_datetime(df_full["Date"], dayfirst=True)
                if existing_min_date is None or existing_max_date is None:
                    # No existing data: upload full
                    csv_bytes = df_full.to_csv(index=False).encode("utf-8")
                    upload_csv_to_github(file_path, csv_bytes, github_token, github_owner, github_repo, github_branch)
                else:
                    # Check if data is outdated
                    if existing_min_date > (datetime.today() - timedelta(days=days_back)):
                        # Data is outdated, update
                        # Keep only relevant parts
                        df_full = df_full[(df_full["Date"] >= target_start_date) & (df_full["Date"] <= target_end_date)]
                        csv_bytes = df_full.to_csv(index=False).encode("utf-8")
                        upload_csv_to_github(file_path, csv_bytes, github_token, github_owner, github_repo, github_branch)
                    else:
                        st.info(f"Data for {sym} already up-to-date.")
            else:
                st.warning(f"No data fetched for {sym}.")
        st.success("All CSV files uploaded to GitHub.")
