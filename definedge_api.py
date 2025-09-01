# definedge_api.py
import requests
import logging
import io
import pandas as pd
from typing import Optional, Dict, Any

log = logging.getLogger("definedge_api")
log.setLevel(logging.INFO)

BASE_AUTH = "https://signin.definedgesecurities.com/auth/realms/debroking/dsbpkc"
BASE_API  = "https://integrate.definedgesecurities.com/dart/v1"
BASE_DATA = "https://data.definedgesecurities.com/sds"
BASE_FILES = "https://app.definedgesecurities.com/public"

class DefinedgeAPIError(Exception):
    pass

class DefinedgeClient:
    def __init__(self, api_token: Optional[str] = None, api_secret: Optional[str] = None, api_session_key: Optional[str] = None, susertoken: Optional[str] = None):
        self.api_token = api_token
        self.api_secret = api_secret
        self.api_session_key = api_session_key
        self.susertoken = susertoken
        self._session = requests.Session()
        self.timeout = 25

    # ---- Auth flow ----
    def auth_step1(self) -> Dict[str, Any]:
        if not self.api_token:
            raise DefinedgeAPIError("api_token required for auth_step1")
        url = f"{BASE_AUTH}/login/{self.api_token}"
        headers = {}
        if self.api_secret:
            headers["api_secret"] = self.api_secret
        r = self._session.get(url, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def auth_step2(self, otp_token: str, otp_code: str) -> Dict[str, Any]:
        url = f"{BASE_AUTH}/token"
        payload = {"otp_token": otp_token or "", "otp": str(otp_code)}
        r = self._session.post(url, json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ---- convenience to set session key ----
    def set_session_key(self, key: str):
        self.api_session_key = key

    def _auth_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_session_key:
            headers["Authorization"] = self.api_session_key  # per docs, not "Bearer ..."
        return headers

    # ---- generic GET/POST (trading API base) ----
    def api_get(self, rel_path: str) -> Any:
        url = rel_path if rel_path.startswith("http") else f"{BASE_API}{rel_path}"
        r = self._session.get(url, headers=self._auth_headers(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def api_post(self, rel_path: str, payload: Optional[Dict]=None) -> Any:
        url = rel_path if rel_path.startswith("http") else f"{BASE_API}{rel_path}"
        r = self._session.post(url, headers=self._auth_headers(), json=payload or {}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ---- endpoints (common ones) ----
    def get_holdings(self):
        return self.api_get("/holdings")

    def get_positions(self):
        return self.api_get("/positions")

    def get_orders(self):
        return self.api_get("/orders")

    def get_order(self, orderid: str):
        return self.api_get(f"/order/{orderid}")

    def get_trades(self):
        return self.api_get("/trades")

    def place_order(self, payload: Dict[str, Any]):
        return self.api_post("/placeorder", payload)

    def modify_order(self, payload: Dict[str, Any]):
        return self.api_post("/modify", payload)

    def cancel_order(self, orderid: str):
        return self.api_get(f"/cancel/{orderid}")

    def get_quotes(self, exchange: str, token: str):
        return self.api_get(f"/quotes/{exchange}/{token}")

    def gtt_orders(self):
        return self.api_get("/gttorders")

    def gtt_place(self, payload: Dict[str, Any]):
        return self.api_post("/gttplaceorder", payload)

    def oco_place(self, payload: Dict[str, Any]):
        return self.api_post("/ocoplaceorder", payload)

    def gtt_modify(self, payload: Dict[str, Any]):
        return self.api_post("/gttmodify", payload)

    def gtt_cancel(self, alert_id: str):
        return self.api_get(f"/gttcancel/{alert_id}")

    def historical_csv(self, segment: str, token: str, timeframe: str, frm: str, to: str) -> str:
        url = f"{BASE_DATA}/history/{segment}/{token}/{timeframe}/{frm}/{to}"
        r = self._session.get(url, headers=self._auth_headers(), timeout=self.timeout)
        r.raise_for_status()
        return r.text

    def download_master_zip(self, zip_name: str, dest_path: str):
        url = f"{BASE_FILES}/{zip_name}"
        with self._session.get(url, stream=True, timeout=self.timeout) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(1024*32):
                    f.write(chunk)
        return dest_path

    # helper to parse csv string into pandas dataframe
    @staticmethod
    def csv_to_df(csv_text: str) -> pd.DataFrame:
        if not csv_text or not csv_text.strip():
            return pd.DataFrame()
        return pd.read_csv(io.StringIO(csv_text), header=None)
