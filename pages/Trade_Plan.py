import streamlit as st

st.set_page_config(page_title="📈 Interactive Trading Plan", page_icon="💡", layout="wide")

# ---- SIDEBAR FOR USER INPUTS ----
st.sidebar.header("🔧 Modify Your Plan")

total_capital = st.sidebar.number_input("Total Capital (₹)", min_value=10000, value=1112000, step=10000, help="Total trading capital")
win_rate = st.sidebar.slider("Win Rate (Accuracy %)", min_value=10, max_value=100, value=35, step=1, help="Expected win rate as %")
holding_win = st.sidebar.number_input("Avg Day Holding for Winning Trade", min_value=1, value=12, step=1)
holding_loss = st.sidebar.number_input("Avg Day Holding for Losing Trade", min_value=1, value=4, step=1)

# ---- CALCULATIONS ----
win_rate_decimal = win_rate / 100
position_size = total_capital * 0.1
risk_per_trade = position_size * 0.02
risk_of_total_capital = total_capital * 0.005
reward_per_win = risk_per_trade * 5
target_profit_yearly = total_capital * 0.5
target_time_days = 365
max_drawdown = total_capital * 0.05
ev_per_trade = (win_rate_decimal * reward_per_win) - ((1 - win_rate_decimal) * risk_per_trade)
trades_needed = target_profit_yearly / ev_per_trade if ev_per_trade != 0 else 0
et_per_trade = (win_rate_decimal * holding_win) - ((1 - win_rate_decimal) * holding_loss)
time_needed_days = trades_needed * et_per_trade if et_per_trade != 0 else 0
lossing_trades_caution = max_drawdown / risk_per_trade if risk_per_trade != 0 else 0
initial_trade_capital = position_size

# ---- HEADER & IMAGE ----
st.markdown("<h1 style='text-align:center; color:#1e3a8a;'>📈 Interactive Trading Plan</h1>", unsafe_allow_html=True)
st.markdown("<div style='text-align:center;'><img src='https://cdn.pixabay.com/photo/2016/04/01/09/28/chart-1296046_1280.png' width='120'></div>", unsafe_allow_html=True)
st.markdown("---")

# ---- CAPITAL & RISK ----
st.markdown("### 💰 <span style='color:#16a34a;'>Capital & Risk Management</span>", unsafe_allow_html=True)
col1, col2, col3 = st.columns([2,2,2])
col1.metric("Total Capital", f"₹{total_capital:,.0f}", "Trading capital")
col2.metric("Position Size", f"₹{position_size:,.0f}", "Per trade exposure")
col3.metric("Risk per Trade (2%)", f"₹{risk_per_trade:,.0f}", "Loss per trade")
col1.metric("Risk of Capital (0.5%)", f"₹{risk_of_total_capital:,.0f}", "Max loss per trade")
col2.metric("Reward per Win", f"₹{reward_per_win:,.0f}", "Target profit per trade")
col3.metric("Win Rate (Accuracy)", f"{win_rate}%", "Based on system")
col1.metric("Target Profit (50%) Yearly", f"₹{target_profit_yearly:,.0f}", "Expected return goal")
col2.metric("Target Time", f"{target_time_days} Days", "Goal time")
col3.metric("Max Drawdown (5%)", f"₹{max_drawdown:,.0f}", "Allowed")
col1.metric("Expected Value/Trade", f"₹{ev_per_trade:,.1f}", f"With {win_rate}% win rate")
col2.metric("Trades Needed for Target", f"{trades_needed:,.0f}", "To gain 50% of capital")
col3.metric("Initial Trade Capital", f"₹{initial_trade_capital:,.0f}", "Stage-I 10%-20% for testing")

# ---- TRADE FREQUENCY ----
st.markdown("### 📊 <span style='color:#f59e42;'>Trade Frequency & Timing</span>", unsafe_allow_html=True)
col4, col5, col6 = st.columns([2,2,2])
col4.metric("Avg Day Holding (Win)", f"{holding_win}", "Winning trades")
col5.metric("Avg Day Holding (Loss)", f"{holding_loss}", "Losing trades")
col6.metric("ET per Trade", f"{et_per_trade:.1f}", "Expected Time/Trade")
col4.metric("Time Needed for Target", f"{time_needed_days:,.0f} Days", "")
col5.metric("Lossing Trades Caution", f"{lossing_trades_caution:,.0f}", "Stop after these back-to-back stop losses")
col6.metric("Max Drawdown", f"₹{max_drawdown:,.0f}", "Max allowed")

st.markdown("---")

# ---- STRATEGY PROGRESSION ----
st.markdown("### 🚀 <span style='color:#a21caf;'>Strategy Progression & Scaling</span>", unsafe_allow_html=True)
st.info("**Stage I:** Initial Trade Capital — 10% to 20% for Testing")
st.success("**Stage II:** Profitable Trades Confidence After 1 Trade — 30% to 50% Risk Financed")
st.success("**Stage III:** Profitable Trades Confidence After 8-10 Trades — 100% Fully Financed")
st.success("**Stage IV:** Profitable Trades Confidence After 10 Trades — 100% + Increased Position Size (Compounding)")
st.markdown("---")

# ---- RISK MANAGEMENT ----
st.markdown("### ⚠️ <span style='color:#f43f5e;'>Risk Management Rules</span>", unsafe_allow_html=True)
st.warning("⏸️ **Slow Down:** After 5 consecutive stop losses")
st.error("🛑 **Stop Trading for a Week:** After 10 consecutive stop losses")
st.error("🛑 **Stop Trading for a Month:** After 15 consecutive stop losses")
st.info("🍵 **Break Taken:** After 25 consecutive stop losses")
st.success("🚀 **Increase Position Size:** After 5 consecutive targets hit")
st.error("❗ **Losing Trades Caution:** Stop Trading after 25 back-to-back stop losses")
st.markdown("---")

# ---- MOTIVATIONAL LINES - SEGREGATED ----
st.markdown("<h2 style='color:#f59e42; text-align:center;'>🧠 Trader Mindset Punchlines</h2>", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["😨 Fear", "🤑 Greed", "💪 Confidence"])

with tab1:
    st.markdown("#### 😨 **Fear - Read When You Feel Fear!**")
    fear_lines = [
        "Dar gaya to har gaya, par bina plan ke lada to barbaad. ⚔️",
        "Loss temporary hota hai, Discipline permanent. ⏳",
        "Stop loss lagana weakness nahi, wisdom hai.",
        "Patience rakhne wale hi market ke king bante hain.",
        "Trading tab tak safe hai jab tak tumhara ego trade nahi kar raha.",
        "Sab kuch seekh lo, par greed ko kabhi sikhne mat do.",
        "Analysis ke bina action mat lo, action ke baad regret mat karo.",
        "Trading me patience aur persistence hi asli edge hai.",
        "Loss ko blame mat karo, apne habit ko change karo.",
        "Jo trade miss ho gaya, uska regret nahi, learning lo.",
        "Market aaj bhi hai, kal bhi hoga — discipline har din zaroori hai."
    ]
    for line in fear_lines:
        st.markdown(f"<span style='color:#ef4444; font-size:1.1em;'>• {line}</span>", unsafe_allow_html=True)

with tab2:
    st.markdown("#### 🤑 **Greed - Read When You Feel Greed!**")
    greed_lines = [
        "Profit chase mat karo, opportunity create karo.",
        "Profit follow karta hai process ko, not emotions ko.",
        "Win ya Loss — dono me ek hi feeling rakho, gratitude aur calmness.",
        "Consistency beats intensity — har din ek step sahi direction me.",
        "FOMO se bachna, wisdom ki nayi shuruaat hai.",
        "Emotions chhodo, Execution pe focus karo. ⚡",
        "Market respect karo, apni strategy pe trust rakho.",
        "Best trade wo hoti hai jisme rules break nahi hote.",
        "Aaj control kiya emotion, kal control karega market.",
        "Dara hua paisa kabhi paisa nahi banata, par bina rule ka paisa kabhi tikta nahi."
    ]
    for line in greed_lines:
        st.markdown(f"<span style='color:#22c55e; font-size:1.1em;'>• {line}</span>", unsafe_allow_html=True)

with tab3:
    st.markdown("#### 💪 **Confidence - Read to Build Confidence!**")
    confidence_lines = [
        "Market ko nahi, apne mind ko master karo.",
        "Fear aur Greed dono ka sirf ek ilaaj hai — Systematic Discipline. ⚖️",
        "Trading me sabse bada profit — Emotional Control.",
        "Risk manage karo, reward khud line me lag jayega.",
        "Trading ka asli hero wo nahi jo profit kare, wo hai jo calm rahe.",
        "Charts ki language samjho, market ki awaaz suno.",
        "Trade karne se pehle, loss accept karne ki himmat rakho.",
        "Strategy bina, trading sirf speculation hai.",
        "Jitna bada plan, utni choti position — risk manage karo.",
        "Jab market volatile ho, tab apni discipline double karo.",
        "Increase Position size — Back to Back 05 Targets hits"
    ]
    for line in confidence_lines:
        st.markdown(f"<span style='color:#6366f1; font-size:1.1em;'>• {line}</span>", unsafe_allow_html=True)

st.markdown("---")

# ---- BONUS LINES ----
st.markdown("<h2 style='color:#f43f5e; text-align:center;'>🚀 Bonus Power Lines (Wallpaper ke liye)</h2>", unsafe_allow_html=True)
bonus_lines = [
    "Market me entry sab lete hain, par exit sirf disciplined log karte hain.",
    "Trading me ego nahi, logic chalta hai.",
    "Trading ka asli hero wo nahi jo profit kare, wo hai jo calm rahe.",
    "Market har kisi ko mauka deta hai, par sirf disciplined ko reward milta hai.",
    "Profit fix nahi hai, process fix karo.",
]
st.markdown("<div style='background-color: #fee2e2; padding: 14px; border-radius: 12px; border: 2px solid #f43f5e;'>", unsafe_allow_html=True)
for line in bonus_lines:
    st.markdown(f"<span style='font-size:1.1em;'>• {line}</span>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("---")
st.markdown("<p style='text-align:center; color:#A3A3A3;'>Made with ❤️ for disciplined traders</p>", unsafe_allow_html=True)
