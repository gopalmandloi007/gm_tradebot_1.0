import streamlit as st

# --- Page Config ---
st.set_page_config(page_title="📓 My Trading Notes", page_icon="📝", layout="wide")

# --- Custom CSS for Attractive Notes ---
st.markdown("""
<style>
.notes-card {
    background: linear-gradient(90deg, #a7f3d0 0%, #f3e8ff 100%);
    border-radius: 18px;
    padding: 28px 38px;
    margin-top: 30px;
    box-shadow: 2px 2px 10px 0px #00000018;
}
.notes-title {
    font-size: 2em !important;
    font-weight: bold;
    color: #7c3aed !important;
    margin-bottom: 18px !important;
    text-align: left;
}
.notes-list {
    font-size: 1.25em !important;
    line-height: 2em !important;
    color: #222 !important;
    margin-bottom: 8px !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align:center; color:#7c3aed;'>📓 My Trading Notes</h1>", unsafe_allow_html=True)

st.markdown("""
<div class='notes-card'>
    <div class='notes-title'>Trading Setup Checklist</div>
    <ul>
        <li class='notes-list'>✅ <b>Close is greater than 100 EMA and 200 SMA</b></li>
        <li class='notes-list'>✅ <b>Identify the Shakeout</b></li>
        <li class='notes-list'>🟣 <b>More purple dots</b></li>
        <li class='notes-list'>🟢 <b>Less corrected from recent swing high</b></li>
        <li class='notes-list'>🔨 <b>Hammer and before hammer, rejections on big red candles</b></li>
        <li class='notes-list'>💧 <b>Volume dry from at least one or two days, volume below 50-day moving average volume</b></li>
        <li class='notes-list'>📉 <b>Small candles during corrections and making rounding bottom</b></li>
        <li class='notes-list'>📈 <b>More closes above the 9 EMA recently</b></li>
        <li class='notes-list'>🕰️ <b>Higher time frame positions near area for confluence</b></li>
        <li class='notes-list'>📈 <b>9 EMA rising count should be higher or increasing</b></li>
    </ul>
</div>
""", unsafe_allow_html=True)

st.markdown("---")
st.markdown("<p style='text-align:center; color:#7c3aed; font-size:1.1em;'>Organize your edge. Review your checklist before every trade!</p>", unsafe_allow_html=True)
