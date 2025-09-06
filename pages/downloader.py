import streamlit as st
import pandas as pd
import io
import zipfile
import requests
import base64
from datetime import datetime, timedelta, date

st.set_page_config(layout="wide")
st.title("📥 Historical OHLCV Download — NSE Stocks & Indices (Incremental & Fast)")

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
    """Parse Definedge history CSV and return DataFrame with Date (datetime.date) and OHLCV numeric columns.
    This is tolerant to several common timestamp formats.
    """
    if not csv_text or not isinstance(csv_text, str):
        return pd.DataFrame()

    try:
        df = pd.read_csv(io.StringIO(csv_text), header=None, dtype=str)
    except Exception:
        return pd.DataFrame()

    if df.shape[1] < 6:
        return pd.DataFrame()

    df = df.rename(columns={0: "DateTime", 1: "Open", 2: "High", 3: "Low", 4: "Close", 5: "Volume"})
    df = df[["DateTime", "Open", "High", "Low", "Close", "Volume"]].copy()

    # Try parsing DateTime
    dt = pd.to_datetime(df["DateTime"], format="%d%m%Y%H%M", errors='coerce')
    if dt.isna().all():
        dt = pd.to_datetime(df["DateTime"], format="%d%m%Y", errors='coerce')
    if dt.isna().all():
        dt = pd.to_datetime(df["DateTime"], errors='coerce')

    df["Date"] = dt.dt.date

    # Numeric conversion
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', ''), errors='coerce')

    res = df[["Date", "Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Date"]).reset_index(drop=True)
    return res


def fetch_hist_for_date_range(api_key: str, segment: str, token: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    from_str = start_date.strftime("%d%m%Y") + "0000"
    to_str = end_date.strftime("%d%m%Y") + "1530"
    url = f"https://data.definedgesecurities.com/sds/history/{segment}/{token}/day/{from_str}/{to_str}"
    headers = {"Authorization": api_key}
    try:
        resp = requests.get(url, headers=headers, timeout=25)
        if resp.status_code == 200 and resp.text.strip():
            return parse_definedge_csv_text(resp.text)
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()


# GitHub helpers

def get_github_file_sha(github_token, owner, repo, file_path, branch='main'):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={branch}"
    headers = {"Authorization": f"token {github_token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("sha")
    return None


def get_existing_csv_df(github_token, owner, repo, file_path, branch='main'):
    """Return (df, sha) for existing CSV in the repo, or (None, None) if not found.
    The returned df will have a Date column parsed to datetime.date if possible.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={branch}"
    headers = {"Authorization": f"token {github_token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        content_b64 = data.get('content', '')
        try:
            decoded = base64.b64decode(content_b64).decode()
            df = pd.read_csv(io.StringIO(decoded))
            if 'Date' in df.columns:
                try:
                    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce').dt.date
                except Exception:
                    df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
            return df, data.get('sha')
        except Exception:
            return None, data.get('sha')
    return None, None


def upload_csv_to_github(file_name, file_bytes, github_token, owner, repo, branch='main'):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_name}"
    # get sha if exists
    sha = get_github_file_sha(github_token, owner, repo, file_name)
    b64_content = base64.b64encode(file_bytes).decode()
    payload = {
        "message": f"Update {file_name} — {datetime.utcnow().isoformat()}",
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
        return True, response.json()
    else:
        return False, response.text


# ----------------------
# Main UI & Logic
# ----------------------

with st.spinner("Downloading master…"):
    master_df = download_master_df()

# filter
df_seg = master_df[master_df["SEGMENT"].astype(str).str.upper() == ALLOWED_SEGMENT]
df_filtered = df_seg[df_seg["INSTRUMENT"].astype(str).str.upper().isin(ALLOWED_INSTRUMENTS)].copy()
st.write(f"Filtered rows: {len(df_filtered)}")

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

# Set full date range (user-adjustable)
start_date_full = st.date_input("Start date (full history)", value=(datetime.today() - timedelta(days=365*5)).date())
end_date_full = st.date_input("End date", value=datetime.today().date())

use_incremental = st.checkbox("Only fetch missing days / incremental updates (recommended)", value=True)
part_size = st.number_input("Part size (symbols per chunk)", min_value=10, max_value=2000, value=300, step=50)

# chunking helper
def chunk_df(df, size):
    return [df.iloc[i:i + size] for i in range(0, len(df), size)]

parts = chunk_df(df_filtered.reset_index(drop=True), int(part_size))
st.subheader(f"Parts: {len(parts)} (≈ {part_size} symbols each)")

# Action buttons for parts
for idx, part_df in enumerate(parts):
    if st.button(f"Download Part {idx+1} ({len(part_df)} symbols)"):
        if not api_key:
            st.error("❌ Please enter API Session Key first.")
            break
        if not github_token or not github_owner or not github_repo:
            st.error("❌ Please fill in GitHub repo details and token.")
            break

        progress = st.progress(0)
        total = len(part_df)
        done = 0

        for _, row in part_df.iterrows():
            token = str(row["TOKEN"]).strip()
            sym = str(row.get("TRADINGSYM") or row["SYMBOL"]).strip()
            folder_path = "data/historical/"
            file_path = f"{folder_path}{sym}_{token}.csv"

            try:
                # Check existing file
                existing_df, existing_sha = get_existing_csv_df(github_token, github_owner, github_repo, file_path, branch=github_branch)

                # Determine fetch window
                if use_incremental and existing_df is not None and not existing_df.empty:
                    existing_max = pd.to_datetime(existing_df['Date'], dayfirst=True, errors='coerce').dt.date.max()
                    if pd.isna(existing_max):
                        existing_max = None
                else:
                    existing_max = None

                if existing_max is not None and existing_max >= end_date_full:
                    st.info(f"{sym} ({token}) — up-to-date (last: {existing_max}). Skipping.")
                    done += 1
                    progress.progress(int(done/total*100))
                    continue

                fetch_start = (existing_max + timedelta(days=1)) if existing_max is not None else pd.to_datetime(start_date_full).to_pydatetime()
                fetch_end = pd.to_datetime(end_date_full).to_pydatetime()

                # fetch only needed range
                df_new = fetch_hist_for_date_range(api_key, ALLOWED_SEGMENT, token, fetch_start, fetch_end)

                if df_new is None or df_new.empty:
                    st.warning(f"No data fetched for {sym} ({token}) in the requested range.")
                    done += 1
                    progress.progress(int(done/total*100))
                    continue

                # normalize Date to date type
                df_new['Date'] = pd.to_datetime(df_new['Date'], dayfirst=True, errors='coerce').dt.date
                df_new = df_new.dropna(subset=['Date']).reset_index(drop=True)

                # Merge with existing if present
                if existing_df is not None and not existing_df.empty:
                    # ensure existing Date is date type
                    try:
                        existing_df['Date'] = pd.to_datetime(existing_df['Date'], dayfirst=True, errors='coerce').dt.date
                    except Exception:
                        pass
                    combined = pd.concat([existing_df, df_new], ignore_index=True)
                    combined = combined.drop_duplicates(subset=['Date'], keep='last')
                    combined = combined.sort_values('Date').reset_index(drop=True)
                else:
                    combined = df_new.copy()

                # If nothing new to add, skip upload
                if existing_df is not None and not existing_df.empty:
                    # compare last dates
                    existing_last = pd.to_datetime(existing_df['Date'], dayfirst=True, errors='coerce').dt.date.max()
                    combined_last = pd.to_datetime(combined['Date'], dayfirst=True, errors='coerce').dt.date.max()
                    if combined_last == existing_last:
                        st.info(f"{sym} ({token}) — no new rows to append. Skipping upload.")
                        done += 1
                        progress.progress(int(done/total*100))
                        continue

                # Prepare CSV bytes and upload
                # Convert Date column to ISO format for consistency
                combined_to_upload = combined.copy()
                combined_to_upload['Date'] = pd.to_datetime(combined_to_upload['Date']).dt.strftime('%d/%m/%Y')
                csv_bytes = combined_to_upload.to_csv(index=False).encode('utf-8')

                success, resp = upload_csv_to_github(file_path, csv_bytes, github_token, github_owner, github_repo, branch=github_branch)
                if success:
                    st.success(f"Uploaded/Updated {file_path} — rows: {len(combined_to_upload)}")
                else:
                    st.error(f"Failed to upload {file_path}: {resp}")

            except Exception as exc:
                st.error(f"Error processing {sym} ({token}): {exc}")

            done += 1
            progress.progress(int(done/total*100))

        st.success("Part complete.")

# Upload ALL button (iterates full list but uses same incremental logic)
if st.button("⬇️ Upload ALL to GitHub (uses incremental logic)"):
    if not api_key:
        st.error("❌ Please enter API Session Key first.")
    elif not github_token or not github_owner or not github_repo:
        st.error("❌ Please fill in GitHub repo details and token.")
    else:
        total = len(df_filtered)
        progress = st.progress(0)
        done = 0
        for _, row in df_filtered.iterrows():
            token = str(row["TOKEN"]).strip()
            sym = str(row.get("TRADINGSYM") or row["SYMBOL"]).strip()
            folder_path = "data/historical/"
            file_path = f"{folder_path}{sym}_{token}.csv"

            try:
                existing_df, existing_sha = get_existing_csv_df(github_token, github_owner, github_repo, file_path, branch=github_branch)
                if use_incremental and existing_df is not None and not existing_df.empty:
                    existing_max = pd.to_datetime(existing_df['Date'], dayfirst=True, errors='coerce').dt.date.max()
                    if pd.isna(existing_max):
                        existing_max = None
                else:
                    existing_max = None

                if existing_max is not None and existing_max >= end_date_full:
                    done += 1
                    progress.progress(int(done/total*100))
                    continue

                fetch_start = (existing_max + timedelta(days=1)) if existing_max is not None else pd.to_datetime(start_date_full).to_pydatetime()
                fetch_end = pd.to_datetime(end_date_full).to_pydatetime()

                df_new = fetch_hist_for_date_range(api_key, ALLOWED_SEGMENT, token, fetch_start, fetch_end)
                if df_new is None or df_new.empty:
                    done += 1
                    progress.progress(int(done/total*100))
                    continue

                df_new['Date'] = pd.to_datetime(df_new['Date'], dayfirst=True, errors='coerce').dt.date
                df_new = df_new.dropna(subset=['Date']).reset_index(drop=True)

                if existing_df is not None and not existing_df.empty:
                    existing_df['Date'] = pd.to_datetime(existing_df['Date'], dayfirst=True, errors='coerce').dt.date
                    combined = pd.concat([existing_df, df_new], ignore_index=True)
                    combined = combined.drop_duplicates(subset=['Date'], keep='last').sort_values('Date').reset_index(drop=True)
                else:
                    combined = df_new.copy()

                # check if there is new data
                if existing_df is not None and not existing_df.empty:
                    existing_last = pd.to_datetime(existing_df['Date'], dayfirst=True, errors='coerce').dt.date.max()
                    combined_last = pd.to_datetime(combined['Date'], dayfirst=True, errors='coerce').dt.date.max()
                    if combined_last == existing_last:
                        done += 1
                        progress.progress(int(done/total*100))
                        continue

                combined_to_upload = combined.copy()
                combined_to_upload['Date'] = pd.to_datetime(combined_to_upload['Date']).dt.strftime('%d/%m/%Y')
                csv_bytes = combined_to_upload.to_csv(index=False).encode('utf-8')

                success, resp = upload_csv_to_github(file_path, csv_bytes, github_token, github_owner, github_repo, branch=github_branch)
                if not success:
                    st.error(f"Failed to upload {file_path}: {resp}")

            except Exception as exc:
                st.error(f"Error processing {sym} ({token}): {exc}")

            done += 1
            progress.progress(int(done/total*100))

        st.success("All CSV incremental uploads complete.")

