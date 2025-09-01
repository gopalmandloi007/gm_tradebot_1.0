import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, timedelta
import plotly.graph_objects as go

@st.cache_data
def load_master_symbols(master_csv_path="data/master/allmaster.csv"):
    df = pd.read_csv(master_csv_path)
    return df

def select_symbol(df, label="Trading Symbol"):
    symbol = st.selectbox(label, df["TRADINGSYM"].unique())
    row = df[df["TRADINGSYM"] == symbol].iloc[0]
    return row

def select_index_symbol(df, label="Index Symbol"):
    index_candidates = df[
        df["INSTRUMENT"].str.contains("INDEX", case=False, na=False) |
        df["TRADINGSYM"].str.contains("NIFTY|IDX|SENSEX|BANKNIFTY|MIDSMALL|500|100", case=False, na=False)
    ].drop_duplicates("TRADINGSYM")
    if index_candidates.empty:
        index_candidates = df
    index_symbol = st.selectbox(label, index_candidates["TRADINGSYM"].unique())
    row = index_candidates[index_candidates["TRADINGSYM"] == index_symbol].iloc[0]
    return row

def fetch_historical(client, segment, token, days):
    today = datetime.today()
    from_date = (today - timedelta(days=days*2)).strftime("%d%m%Y%H%M")
    to_date = today.strftime("%d%m%Y%H%M")
    hist_csv = client.historical_csv(segment=segment, token=token, timeframe="day", frm=from_date, to=to_date)
    if not hist_csv.strip():
        return pd.DataFrame()
    hist_df = pd.read_csv(io.StringIO(hist_csv), header=None)
    if hist_df.shape[1] == 7:
        hist_df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume", "OI"]
    elif hist_df.shape[1] == 6:
        hist_df.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]
    else:
        return pd.DataFrame()
    # Parse DateTime as per API spec: ddmmyyyyHHMM
    hist_df["DateTime"] = pd.to_datetime(hist_df["DateTime"].astype(str), format="%d%m%Y%H%M", errors="coerce")
    hist_df = hist_df.sort_values("DateTime")
    hist_df = hist_df.drop_duplicates(subset=["DateTime"])
    hist_df = hist_df.reset_index(drop=True)
    return hist_df

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

st.title("📈 Candlestick, EMAs, Relative Strength & Volume Chart")

client = st.session_state.get("client")
if not client:
    st.error("⚠️ Not logged in. Please login first from the Login page.")
    st.stop()

df_master = load_master_symbols()
segment = st.selectbox("Exchange/Segment", sorted(df_master["SEGMENT"].unique()), index=0)
segment_df = df_master[df_master["SEGMENT"] == segment]

# Symbol selection
stock_row = select_symbol(segment_df, label="Stock Trading Symbol")

# Index selection
index_row = select_index_symbol(df_master, label="Index Trading Symbol")

# EMA period selection
st.markdown("#### EMA Periods")
ema_periods = st.text_input("Enter EMA periods (comma separated)", value="10,20,50,100,200")
ema_periods = [int(x.strip()) for x in ema_periods.split(",") if x.strip().isdigit()]

days_back = st.number_input("Number of Days (candles to fetch)", min_value=20, max_value=600, value=250, step=1)
rs_sma_period = st.number_input("RS SMA Period", min_value=2, max_value=55, value=20, step=1)

if st.button("Show Chart"):
    try:
        df_stock = fetch_historical(client, stock_row["SEGMENT"], stock_row["TOKEN"], days_back)
        if df_stock.empty:
            st.warning(f"No data for: {stock_row['TRADINGSYM']} ({stock_row['TOKEN']}, {stock_row['SEGMENT']})")
            st.stop()

        df_index = fetch_historical(client, index_row["SEGMENT"], index_row["TOKEN"], days_back)
        if df_index.empty:
            st.warning(f"No data for index: {index_row['TRADINGSYM']} ({index_row['TOKEN']}, {index_row['SEGMENT']})")
            st.stop()

        # Sort and deduplicate just in case
        df_stock = df_stock.sort_values("DateTime").drop_duplicates(subset=["DateTime"]).reset_index(drop=True)
        df_index = df_index.sort_values("DateTime").drop_duplicates(subset=["DateTime"]).reset_index(drop=True)

        # Calculate EMAs
        for period in ema_periods:
            df_stock[f"EMA_{period}"] = ema(df_stock["Close"], period)

        # --- Candlestick Chart with EMAs ---
        fig1 = go.Figure()
        fig1.add_trace(go.Candlestick(
            x=df_stock["DateTime"].dt.date,
            open=df_stock["Open"],
            high=df_stock["High"],
            low=df_stock["Low"],
            close=df_stock["Close"],
            name="OHLC",
            increasing_line_color='green',
            decreasing_line_color='red'
        ))
        for period in ema_periods:
            fig1.add_trace(go.Scatter(
                x=df_stock["DateTime"].dt.date, 
                y=df_stock[f"EMA_{period}"],
                mode="lines", name=f"EMA {period}",
                line=dict(width=1.5)
            ))
        fig1.update_layout(
            title=f"{stock_row['TRADINGSYM']} Candlestick Chart with EMAs",
            xaxis=dict(
                title="Date",
                type="category",  # Remove gaps for missing dates
                rangeslider=dict(visible=False)
            ),
            yaxis=dict(title="Price"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=600,
            template="plotly_white",
            margin=dict(l=10, r=10, t=40, b=10)
        )
        st.plotly_chart(fig1, use_container_width=True)

        # --- Volume Chart (separate) ---
        fig_vol = go.Figure()
        fig_vol.add_trace(go.Bar(
            x=df_stock["DateTime"].dt.date,
            y=df_stock["Volume"],
            name="Volume",
            marker=dict(color="#636EFA"),
            opacity=0.7,
        ))
        fig_vol.update_layout(
            title=f"{stock_row['TRADINGSYM']} Volume Chart",
            xaxis=dict(
                title="Date",
                type="category"  # Remove gaps for missing dates
            ),
            yaxis=dict(title="Volume"),
            height=300,
            template="plotly_white",
            margin=dict(l=10, r=10, t=40, b=10)
        )
        st.plotly_chart(fig_vol, use_container_width=True)

        # --- Relative Strength Section ---
        df_stock_rs = df_stock[["DateTime", "Close"]].rename(columns={"Close": "StockClose"})
        df_index_rs = df_index[["DateTime", "Close"]].rename(columns={"Close": "IndexClose"})
        df_rs = pd.merge(df_stock_rs, df_index_rs, on="DateTime", how="inner")
        df_rs = df_rs.sort_values("DateTime").reset_index(drop=True)
        if df_rs.empty:
            st.warning("No overlapping dates between stock and index data for RS chart.")
        else:
            df_rs["RS"] = (df_rs["StockClose"] / df_rs["IndexClose"]) * 100
            df_rs["RS_SMA"] = df_rs["RS"].rolling(window=rs_sma_period).mean()

            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=df_rs["DateTime"].dt.date, 
                y=df_rs["RS"],
                mode="lines", name="Relative Strength",
                line=dict(color="#1976d2", width=2)
            ))
            fig2.add_trace(go.Scatter(
                x=df_rs["DateTime"].dt.date, 
                y=df_rs["RS_SMA"],
                mode="lines", name=f"RS SMA {rs_sma_period}",
                line=dict(color="#d32f2f", width=2, dash='dash')
            ))
            fig2.update_layout(
                title=f"Relative Strength: {stock_row['TRADINGSYM']} vs {index_row['TRADINGSYM']}",
                xaxis=dict(
                    title="Date",
                    type="category"  # Remove gaps for missing dates
                ),
                yaxis_title="Relative Strength",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                height=400,
                template="plotly_white",
                margin=dict(l=10, r=10, t=40, b=10)
            )
            st.plotly_chart(fig2, use_container_width=True)

            st.markdown("#### Download Relative Strength Data")
            rs_display_cols = ["DateTime", "StockClose", "IndexClose", "RS", "RS_SMA"]
            st.dataframe(df_rs[rs_display_cols], use_container_width=True)
            csv_rs = df_rs[rs_display_cols].to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download RS data as CSV",
                data=csv_rs,
                file_name=f'relative_strength_{stock_row["TRADINGSYM"]}_vs_{index_row["TRADINGSYM"]}.csv',
                mime='text/csv'
            )
            st.info(
                f"Relative Strength = Stock Close / Index Close × 100\n\n"
                f"Blue: Raw RS, Red Dashed: SMA({rs_sma_period}) of RS"
            )

        # --- Download full OHLCV+EMA data ---
        st.markdown("#### Download OHLCV+EMAs Data")
        st.dataframe(df_stock, use_container_width=True)
        csv = df_stock.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download OHLCV+EMA data as CSV",
            data=csv,
            file_name=f'candlestick_ema_{stock_row["TRADINGSYM"]}.csv',
            mime='text/csv'
        )
        st.info(
            f"EMAs shown for periods: {', '.join([str(p) for p in ema_periods])}. "
            "You can adjust the periods and days as needed."
        )
    except Exception as e:
        st.error(f"Error fetching/calculating chart: {e}")
