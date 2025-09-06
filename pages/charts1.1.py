# historical_chart.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import io

st.set_page_config(layout="wide")
st.title("📊 Historical Charts & Relative Strength (Enhanced)")

# -----------------------
# Load CSV from GitHub
# -----------------------
def load_csv_from_github(github_owner, github_repo, file_path, github_token=None, branch="main"):
    url = f"https://raw.githubusercontent.com/{github_owner}/{github_repo}/{branch}/{file_path}"
    headers = {}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code == 200:
        return pd.read_csv(io.StringIO(resp.text))
    else:
        st.error(f"❌ Failed to load {file_path} ({resp.status_code})")
        return pd.DataFrame()

# -----------------------
# Plot candlestick + volume
# -----------------------
def plot_candlestick(df, title="Price Chart"):
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df["Date"],
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Price"
    ))

    fig.add_trace(go.Bar(
        x=df["Date"],
        y=df["Volume"],
        name="Volume",
        yaxis="y2",
        opacity=0.3
    ))

    fig.update_layout(
        title=title,
        xaxis=dict(rangeslider=dict(visible=False)),
        yaxis=dict(title="Price"),
        yaxis2=dict(title="Volume", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h")
    )
    st.plotly_chart(fig, use_container_width=True)

# -----------------------
# Relative Strength
# -----------------------
def calculate_relative_strength(stock_df, benchmark_df):
    merged = pd.merge(stock_df[["Date", "Close"]], benchmark_df[["Date", "Close"]], on="Date", suffixes=("_stock", "_bench"))
    merged["RS"] = merged["Close_stock"] / merged["Close_bench"]
    return merged

# -----------------------
# Inputs
# -----------------------
github_owner = st.text_input("GitHub Username / Organization", value="gopalmandloi007")
github_repo = st.text_input("Repository Name", value="gm_tradebot_1.0")
branch = st.text_input("Branch", value="main")
github_token = st.text_input("GitHub Token (optional)", type="password")

symbol = st.text_input("Enter Stock Symbol (e.g., RELIANCE)")
token = st.text_input("Enter Stock Token (e.g., 2885)")
benchmark_choice = st.selectbox("Benchmark Index", ["NIFTY50", "NIFTY500", "NIFTY_MIDSMALL400"])

# -----------------------
# Load and Plot
# -----------------------
if st.button("Show Chart"):
    if not symbol or not token:
        st.error("⚠️ Please enter symbol and token.")
    else:
        stock_path = f"data/historical/{symbol}_{token}.csv"
        bench_path = f"data/historical/{benchmark_choice}.csv"  # Assuming you saved indices with these names

        stock_df = load_csv_from_github(github_owner, github_repo, stock_path, github_token, branch)
        bench_df = load_csv_from_github(github_owner, github_repo, bench_path, github_token, branch)

        if not stock_df.empty and not bench_df.empty:
            stock_df["Date"] = pd.to_datetime(stock_df["Date"], dayfirst=True)
            bench_df["Date"] = pd.to_datetime(bench_df["Date"], dayfirst=True)

            st.subheader(f"📈 {symbol} Candlestick Chart")
            plot_candlestick(stock_df, title=f"{symbol} Price")

            st.subheader(f"📊 Relative Strength vs {benchmark_choice}")
            rs_df = calculate_relative_strength(stock_df, bench_df)
            fig_rs = go.Figure(go.Scatter(x=rs_df["Date"], y=rs_df["RS"], mode="lines", name="RS"))
            fig_rs.update_layout(title=f"Relative Strength ({symbol} / {benchmark_choice})")
            st.plotly_chart(fig_rs, use_container_width=True)
        else:
            st.warning("⚠️ Could not load data for stock or benchmark.")
