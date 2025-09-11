# utils/charts.py

import plotly.graph_objects as go

def plot_candlestick(df, symbol="Stock"):
    fig = go.Figure(
        data=[go.Candlestick(
            x=df["date"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"]
        )]
    )
    fig.update_layout(title=f"{symbol} — Candlestick Chart", xaxis_rangeslider_visible=False)
    return fig
