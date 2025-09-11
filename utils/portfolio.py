# utils/portfolio.py

import pandas as pd

class PortfolioManager:
    def __init__(self, api_client):
        self.api = api_client

    def get_holdings(self):
        """Fetch holdings from Definedge API."""
        try:
            data = self.api.get("/portfolio/holdings")
            return data.get("holdings", [])
        except Exception as e:
            print("Error fetching holdings:", e)
            return []

    def get_orders(self):
        """Fetch orders from Definedge API."""
        try:
            data = self.api.get("/orders")
            return data.get("orders", [])
        except Exception as e:
            print("Error fetching orders:", e)
            return []

    def get_holdings_summary(self):
        """Summarize holdings P&L."""
        holdings = self.get_holdings()
        if not holdings:
            return {}

        df = pd.DataFrame(holdings)
        df["pnl"] = (df["ltp"] - df["avg_price"]) * df["qty"]
        return {
            "Total Investment": (df["avg_price"] * df["qty"]).sum(),
            "Current Value": (df["ltp"] * df["qty"]).sum(),
            "PnL": df["pnl"].sum()
        }
