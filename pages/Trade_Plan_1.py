import streamlit as st
import random

# ==========================
# PAGE CONFIG
# ==========================
st.set_page_config(
    page_title="📈 Interactive Trading Plan + Quotes",
    page_icon="📊",
    layout="wide"
)

# --------------------------
# CUSTOM BANNER (top)
# --------------------------
st.markdown("""
<div style="background:linear-gradient(90deg, #16a34a 0%, #3b82f6 100%);
            border-radius:18px; margin-bottom:18px; padding:12px;">
    <div style="display:flex; align-items:center; justify-content:center;">
        <img src="https://cdn.pixabay.com/photo/2017/01/10/19/05/chart-1977527_960_720.png" height="60" style="margin-right:18px;">
        <span style="font-size:2.1em; color:white; font-weight:700; letter-spacing:1px;">
            Interactive Trading Plan — Gopal Mandloi
        </span>
        <img src="https://cdn.pixabay.com/photo/2017/01/10/19/05/chart-1977527_960_720.png" height="60" style="margin-left:18px;">
    </div>
    <div style="text-align:center; margin-top:8px;">
        <span style="font-size:1.05em; color:#fbbf24;">Plan • Discipline • Confidence • Growth</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================
# SIDEBAR INPUTS
# ==========================
st.sidebar.header("🔧 Modify Your Plan")
total_capital = st.sidebar.number_input("Total Capital (₹)", min_value=10000, value=1112000, step=10000, format="%d")
win_rate = st.sidebar.slider("Win Rate (%)", min_value=10, max_value=100, value=35, step=1)
holding_win = st.sidebar.number_input("Avg Day Holding (Win)", min_value=1, value=12, step=1)
holding_loss = st.sidebar.number_input("Avg Day Holding (Loss)", min_value=1, value=4, step=1)
st.sidebar.image("https://cdn.pixabay.com/photo/2014/04/03/10/32/business-311353_1280.png", caption="Stay Disciplined!", use_column_width=True)

# ==========================
# CORE CALCULATIONS
# ==========================
win_rate_dec = win_rate / 100
position_size = total_capital * 0.10          # 10% default per trade exposure
risk_per_trade = position_size * 0.02         # 2% of position size
risk_of_total_capital = total_capital * 0.005 # 0.5% of total capital
reward_per_win = risk_per_trade * 5           # R:R 1:5 assumed
target_profit_yearly = total_capital * 0.50   # 50% yearly target
target_time_days = 365
max_drawdown = total_capital * 0.05           # 5% allowed drawdown
ev_per_trade = (win_rate_dec * reward_per_win) - ((1 - win_rate_dec) * risk_per_trade)  # Expected value per trade
trades_needed = target_profit_yearly / ev_per_trade if ev_per_trade > 0 else 0
et_per_trade = (win_rate_dec * holding_win) - ((1 - win_rate_dec) * holding_loss)
time_needed_days = trades_needed * et_per_trade if et_per_trade > 0 else 0
lossing_trades_caution = max_drawdown / risk_per_trade if risk_per_trade > 0 else 0
initial_trade_capital = position_size

# ==========================
# CAPITAL & RISK MANAGEMENT DISPLAY
# ==========================
st.markdown("### 💰 <span style='color:#16a34a;'>Capital & Risk Management</span>", unsafe_allow_html=True)
col1, col2, col3 = st.columns([2,2,2])

col1.metric("Total Capital", f"₹{total_capital:,.0f}", "Trading capital")
col2.metric("Position Size (10%)", f"₹{position_size:,.0f}", "Per trade exposure")
col3.metric("Risk per Trade (2%)", f"₹{risk_per_trade:,.0f}", "Loss per trade")

col1.metric("Risk of Capital (0.5%)", f"₹{risk_of_total_capital:,.0f}", "Max risk per trade")
col2.metric("Reward per Win (R=5)", f"₹{reward_per_win:,.0f}", "Target profit per trade")
col3.metric("Win Rate", f"{win_rate}%", "Input assumption")

col1.metric("Target Profit (50% Yearly)", f"₹{target_profit_yearly:,.0f}", "Goal")
col2.metric("Target Time", f"{target_time_days} Days", "Goal period")
col3.metric("Max Drawdown (5%)", f"₹{max_drawdown:,.0f}", "Allowed max drawdown")

col1.metric("Expected Value/Trade", f"₹{ev_per_trade:,.1f}", f"With {win_rate}% win rate")
col2.metric("Trades Needed for Target", f"{trades_needed:,.0f}", "To gain 50% of capital")
col3.metric("Initial Trade Capital", f"₹{initial_trade_capital:,.0f}", "Stage-I 10% exposure")

# ==========================
# TRADE FREQUENCY & TIMING
# ==========================
st.markdown("### 📊 <span style='color:#f59e42;'>Trade Frequency & Timing</span>", unsafe_allow_html=True)
col4, col5, col6 = st.columns([2,2,2])
col4.metric("Avg Day Holding (Win)", f"{holding_win}", "Winning trades (days)")
col5.metric("Avg Day Holding (Loss)", f"{holding_loss}", "Losing trades (days)")
col6.metric("ET per Trade", f"{et_per_trade:.1f}", "Expected time per trade (days)")

col4.metric("Time Needed for Target", f"{time_needed_days:,.0f} Days", "")
col5.metric("Losing Trades Caution", f"{lossing_trades_caution:,.0f}", "Stop after these stop losses")
col6.image("https://cdn.pixabay.com/photo/2015/03/26/09/39/stop-690073_1280.png", width=90)

st.markdown("---")

# ==========================
# STRATEGY PROGRESSION
# ==========================
st.markdown("### 🚀 <span style='color:#a21caf;'>Strategy Progression & Scaling</span>", unsafe_allow_html=True)
st.markdown("""
- <span style='color:#a21caf; font-weight:bold;'>Stage I:</span> Initial Trade Capital — 10% to 20% for Testing <br>
- <span style='color:#16a34a; font-weight:bold;'>Stage II:</span> Profitable Trades Confidence After 1 Trade — 30% to 50% Risk Financed <br>
- <span style='color:#16a34a; font-weight:bold;'>Stage III:</span> Profitable Trades Confidence After 8-10 Trades — 100% Fully Financed <br>
- <span style='color:#f59e42; font-weight:bold;'>Stage IV:</span> Profitable Trades Confidence After 10+ Trades — Increase Position Size (Compounding)
""", unsafe_allow_html=True)

st.markdown("---")

# ==========================
# RISK MANAGEMENT RULES
# ==========================
st.markdown("### ⚠️ <span style='color:#f43f5e;'>Risk Management Rules</span>", unsafe_allow_html=True)
st.markdown("""
- <span style='color:#f59e42;'>⏸️ <b>Slow Down:</b></span> After 5 consecutive stop losses <br>
- <span style='color:#ef4444;'>🛑 <b>Stop Trading for a Week:</b></span> After 10 consecutive stop losses <br>
- <span style='color:#ef4444;'>🛑 <b>Stop Trading for a Month:</b></span> After 15 consecutive stop losses <br>
- <span style='color:#22d3ee;'>🍵 <b>Break Taken:</b></span> After 25 consecutive stop losses <br>
- <span style='color:#16a34a;'>🚀 <b>Increase Position Size:</b></span> After 5 consecutive targets hit <br>
- <span style='color:#ef4444;'>❗ <b>Losing Trades Caution:</b></span> Stop Trading after 25 back-to-back stop losses <br>
""", unsafe_allow_html=True)
st.image("https://cdn.pixabay.com/photo/2017/01/10/19/05/chart-1977527_960_720.png", width=120)

st.markdown("---")

# ==========================
# TRADER MINDSET PUNCHLINES (Tabs)
# ==========================
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
        st.markdown(f"<span style='color:#ef4444; font-size:1.05em;'>• {line}</span>", unsafe_allow_html=True)
    st.image("https://cdn.pixabay.com/photo/2015/10/31/12/08/fear-1012592_1280.jpg", width=120)

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
        st.markdown(f"<span style='color:#22c55e; font-size:1.05em;'>• {line}</span>", unsafe_allow_html=True)
    st.image("https://cdn.pixabay.com/photo/2014/04/03/10/32/business-311353_1280.png", width=120)

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
        st.markdown(f"<span style='color:#6366f1; font-size:1.05em;'>• {line}</span>", unsafe_allow_html=True)
    st.image("https://cdn.pixabay.com/photo/2017/01/10/19/05/chart-1977527_960_720.png", width=120)

st.markdown("---")

# ==========================
# QUOTES WALL — All categories, tabbed, English + Hinglish
# ==========================
st.markdown("<h2 style='text-align:center; color:#f97316;'>📚 Trader Quotes Wall — English + Hinglish</h2>", unsafe_allow_html=True)

# Quotes data (full list from your request)
quotes_wall = {
    "Fear": [
        ("Cut your losses quickly.", "Apne losses ko jaldi cut karo, hope me mat raho — 'shayad wapas aayega' yeh trap hai."),
        ("Hope is not a strategy.", "Umeed strategy nahi hoti bhai — plan banao, dua nahi."),
        ("Define your risk before you enter.", "Trade lene se pehle apna risk fix karo, baad me mat sochna."),
        ("Don’t fight the market.", "Market ke against mat ladho, uske flow ke sath chalo."),
        ("Fear will make you exit too early.", "Dar tumhe profit wale trade se bhi bahar nikal dega."),
        ("Protect your capital first.", "Pehle apna capital bacha, profit baad me kama lena."),
        ("No trade is also a decision.", "Kabhi kabhi trade na lena bhi ek smart decision hoti hai.")
    ],
    "Greed": [
        ("Pigs get slaughtered. Take profits when you have them.", "Lalach me mat padho — profit mile to secure karo."),
        ("You don't have to catch every move.", "Har move ko pakadne ki zarurat nahi hoti."),
        ("Trade the plan, not your emotions.", "Plan pe chalo, emotions pe nahi."),
        ("Money is made by sitting, not trading too much.", "Paise patience se bante hain, overtrading se nahi."),
        ("A greedy trader never survives long.", "Lalach wala trader zyada din market me nahi tikta."),
        ("Small consistent profits beat big random wins.", "Chhote stable profits badi lucky jeet se behtar hote hain."),
        ("Book profit, don’t marry your stocks.", "Stock se pyar nahi, timing se paisa banta hai.")
    ],
    "Overconfidence": [
        ("The market can remain irrational longer than you can remain solvent.", "Market tumse zyada time tak galat reh sakta hai — overconfident mat ho."),
        ("Never risk more than you can afford to lose.", "Utna hi risk lo jitna lose karne ki capacity ho."),
        ("One good trade doesn’t make you a genius.", "Ek accha trade tumhe genius nahi banata."),
        ("Stay humble or the market will make you humble.", "Namrata se raho, warna market namrata sikha dega."),
        ("When you think you can’t lose, that’s when you do.", "Jab lagta hai ab kabhi loss nahi hoga — wahi galti hoti hai."),
        ("Confidence comes from process, not results.", "Real confidence process se aata hai, result se nahi."),
        ("Market rewards discipline, not ego.", "Market discipline ko reward karta hai, ego ko punish.")
    ],
    "FOMO": [
        ("Missing one trade won’t make you poor.", "Ek trade miss hone se koi gareeb nahi hota."),
        ("Wait for your pitch, not every pitch.", "Har opportunity par mat koodo, apna setup ka wait karo."),
        ("Patience is also a position.", "Sabr bhi ek position hoti hai."),
        ("If you chase trades, you’ll lose focus.", "Agar har trade ke peeche bhagoge, focus kho doge."),
        ("Market will always give another chance.", "Market hamesha doosra mauka deta hai, panic mat karo."),
        ("Entry late se better hai galat entry.", "Late entry sahi hai, galat entry nahi."),
        ("Let the trade come to you.", "Trade tumhare paas aane do, zabardasti mat karo.")
    ],
    "Bonus": [
        ("Trade what you see, not what you think.", "Jo chart dikhata hai wahi trade karo, apna guess nahi."),
        ("Losing is part of learning.", "Har loss ek lesson hai, fail nahi."),
        ("Discipline beats intelligence.", "Smart hone se zyada important hai discipline."),
        ("Market rewards patience and punishes impulsiveness.", "Market patience ko reward karta hai, impulsiveness ko punish."),
        ("Fear + Greed control = Freedom.", "Jab fear aur greed dono control me ho jaayein, tab milta hai financial freedom.")
    ]
}

# Tabs for quotes
qtab1, qtab2, qtab3, qtab4, qtab5, qtab6 = st.tabs(["😨 Fear", "💰 Greed", "😎 Overconfidence", "⚡ FOMO", "🌈 Bonus", "📚 All Quotes"])

# Helper to display quote card
def show_card(en, hi, color="#0b1220"):
    st.markdown(f"""
        <div style="background:{color}; padding:16px; border-radius:12px; margin-bottom:12px; border:1px solid rgba(255,255,255,0.03)">
            <div style="font-weight:700; font-size:18px; color:#fff;">💬 {en}</div>
            <div style="font-style:italic; color:#cde7ff; margin-top:6px;">📝 {hi}</div>
        </div>
    """, unsafe_allow_html=True)

# Colors per category
colors = {
    "Fear": "#421a1a",
    "Greed": "#173d2f",
    "Overconfidence": "#2a1f3b",
    "FOMO": "#3a1a2a",
    "Bonus": "#15324a",
    "All": "#0b1220"
}

# Fear tab
with qtab1:
    st.subheader("Fear Quotes — Read when you feel uncertain")
    if st.button("🎲 Random Fear Quote"):
        en, hi = random.choice(quotes_wall["Fear"])
        show_card(en, hi, colors["Fear"])
    for en, hi in quotes_wall["Fear"]:
        show_card(en, hi, colors["Fear"])

# Greed tab
with qtab2:
    st.subheader("Greed Quotes — Read when you feel greedy")
    if st.button("🎲 Random Greed Quote"):
        en, hi = random.choice(quotes_wall["Greed"])
        show_card(en, hi, colors["Greed"])
    for en, hi in quotes_wall["Greed"]:
        show_card(en, hi, colors["Greed"])

# Overconfidence tab
with qtab3:
    st.subheader("Overconfidence Quotes — For humility check")
    if st.button("🎲 Random Overconfidence Quote"):
        en, hi = random.choice(quotes_wall["Overconfidence"])
        show_card(en, hi, colors["Overconfidence"])
    for en, hi in quotes_wall["Overconfidence"]:
        show_card(en, hi, colors["Overconfidence"])

# FOMO tab
with qtab4:
    st.subheader("FOMO Quotes — Read to slow down")
    if st.button("🎲 Random FOMO Quote"):
        en, hi = random.choice(quotes_wall["FOMO"])
        show_card(en, hi, colors["FOMO"])
    for en, hi in quotes_wall["FOMO"]:
        show_card(en, hi, colors["FOMO"])

# Bonus tab
with qtab5:
    st.subheader("Bonus — Universal mindset lines")
    if st.button("🎲 Random Bonus Quote"):
        en, hi = random.choice(quotes_wall["Bonus"])
        show_card(en, hi, colors["Bonus"])
    for en, hi in quotes_wall["Bonus"]:
        show_card(en, hi, colors["Bonus"])

# All quotes tab
with qtab6:
    st.subheader("All Quotes — Full list (for wallpaper / print ready reading)")
    if st.button("🎲 Random All-Quotes"):
        cat = random.choice(list(quotes_wall.keys()))
        en, hi = random.choice(quotes_wall[cat])
        show_card(f"[{cat}] {en}", hi, colors["All"])
    # show all grouped
    for cat, lst in quotes_wall.items():
        st.markdown(f"### {cat}")
        for en, hi in lst:
            show_card(f"[{cat}] {en}", hi, colors["All"])

st.markdown("---")
st.markdown("<p style='text-align:center; color:#A3A3A3; font-size:1.0em;'>Made with ❤️ for disciplined traders — Gopal Mandloi</p>", unsafe_allow_html=True)
