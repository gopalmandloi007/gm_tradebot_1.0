GM Tradebot - Ready repo (backend-heavy)
--------------------------------------
How to run (local):
1. Unzip repository
2. Create .streamlit/secrets.toml with:
   DEFINEDGE_API_TOKEN = "<your token>"
   DEFINEDGE_API_SECRET = "<your secret>"
   DEFINEDGE_TOTP_SECRET = "<optional totp secret>"
3. From project root run:
   pip install -r requirements.txt
   streamlit run frontend/streamlit_app.py

Notes:
- All heavy logic runs in backend package.
- Frontend only shows simple pages for login, holdings and orders.
- GTT payload may need broker-specific field names; adjust in backend.orders.
