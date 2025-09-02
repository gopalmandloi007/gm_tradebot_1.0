import os
import pandas as pd
from datetime import datetime, timedelta
from fyers_apiv3 import fyersModel

# -----------------------------
# CONFIGURATION
# -----------------------------
MASTER_FILE = "/content/Stock_List_1.xlsx"   # master excel file
OUTPUT_DIR = "/content/historical_data"      # folder for saving csv
DEFAULT_TIMEFRAME = "5D"                     # can be "1D","5D","15","30","60","D","W","M"
DAYS_BACK = 365                              # kitne din ka data chahiye

# -----------------------------
# FYERS LOGIN HELPER
# -----------------------------
def get_fyers_client():
    from config1 import client_id, access_token  # credentials stored in config1.py
    return fyersModel.FyersModel(client_id=client_id, token=access_token, log_path="fyers_log")

# -----------------------------
# MASTER FILE LOADER
# -----------------------------
def load_master_symbols(master_file):
    if not os.path.exists(master_file):
        raise FileNotFoundError(f"❌ Master file not found: {master_file}")

    df = pd.read_excel(master_file)

    # Clean & Filter NSE symbols
    if "Symbol" not in df.columns:
        raise ValueError("❌ Master file must contain 'Symbol' column")

    df = df[df["Symbol"].astype(str).str.endswith(".NSE")]

    if df.empty:
        raise ValueError("⚠️ No NSE rows found in master. Please check your master file.")

    return df["Symbol"].tolist()

# -----------------------------
# HISTORICAL DATA FETCH
# -----------------------------
def fetch_historical(fyers, symbol, timeframe=DEFAULT_TIMEFRAME, days_back=DAYS_BACK):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)

    data_req = {
        "symbol": symbol,
        "resolution": timeframe,
        "date_format": "1",
        "range_from": start_date.strftime("%Y-%m-%d"),
        "range_to": end_date.strftime("%Y-%m-%d"),
        "cont_flag": "1"
    }

    response = fyers.history(data_req)

    if not response.get("candles"):
        print(f"⚠️ No data for {symbol}")
        return pd.DataFrame()

    # Convert candles to DataFrame
    df = pd.DataFrame(response["candles"], columns=["timestamp","open","high","low","close","volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")
    df.drop(columns=["timestamp"], inplace=True)

    return df

# -----------------------------
# MAIN FUNCTION
# -----------------------------
def run_fetcher():
    fyers = get_fyers_client()

    # Load master symbols
    symbols = load_master_symbols(MASTER_FILE)
    print(f"✅ Loaded {len(symbols)} NSE symbols from master.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_data = []

    for sym in symbols:
        print(f"⏳ Fetching: {sym}")
        df = fetch_historical(fyers, sym, timeframe=DEFAULT_TIMEFRAME, days_back=DAYS_BACK)

        if not df.empty:
            # Save per-symbol CSV
            out_path = os.path.join(OUTPUT_DIR, f"{sym.replace(':','_')}.csv")
            df.to_csv(out_path, index=False)
            print(f"   ✅ Saved {sym} → {out_path}")

            df["symbol"] = sym
            all_data.append(df)

    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        combined_out = os.path.join(OUTPUT_DIR, "ALL_SYMBOLS_COMBINED.csv")
        combined.to_csv(combined_out, index=False)
        print(f"\n📊 Combined file saved → {combined_out}")
    else:
        print("⚠️ No data fetched for any symbol.")

# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    run_fetcher()
