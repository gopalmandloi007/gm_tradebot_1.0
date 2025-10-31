import streamlit as st

# Title
st.markdown("<h1 style='text-align: center; color: #3B82F6;'>📈 My Trading Plan</h1>", unsafe_allow_html=True)
st.markdown("---")

# Capital and Risk Section
st.markdown("""
### 💰 **Capital & Risk Management**

| Parameter                        | Value     | Notes                         |
|:----------------------------------|:---------:|:------------------------------|
| **Total Capital**                 | `1,112,000`  | Trading capital               |
| **Position Size**                 | `111,200`    | Per trade exposure            |
| **Risk per Trade (2%)**           | `2,224`      | Loss per trade                |
| **Risk of Total Capital (0.5%)**  | `5,560`      | Max loss per trade            |
| **Reward per Win**                | `11,120`     | Target profit per trade       |
| **Win Rate (Accuracy)**           | `35%`        | Based on system performance   |
| **Target Profit (50%) Yearly**    | `556,000`    | Expected return goal          |
| **Target Time (One Year)**        | `365 Days`   | Expected return goal time     |
| **Max Drawdown (5%)**             | `55,600`     | Max draw down allowed         |
| **Expected Value per Trade**      | `2,446.4`    | With 35% win rate             |

""")

# Strategy Progression Section
st.markdown("""
### 🚀 **Strategy Progression & Scaling**

| Stage            | Criteria                                   | Capital Usage                      |
|:-----------------|:-------------------------------------------|:-----------------------------------|
| **Stage I**      | Initial Trade Capital                      | 10% to 20% for Testing             |
| **Stage II**     | Profitable Trades Confidence After 1 Trade | 30% to 50% Risk Financed           |
| **Stage III**    | Profitable Trades Confidence After 8-10 Trades | 100% Fully Financed             |
| **Stage IV**     | Profitable Trades Confidence After 10 Trades | 100% + Increased Position Size (Compounding) |

""")

# Trading Frequency Section
st.markdown("""
### 📊 **Trade Frequency & Timing**

| Parameter                     | Value      | Notes                                |
|:------------------------------|:----------:|:-------------------------------------|
| **Trades Needed for Target**  | `227`      | Required trades to gain 50% of capital |
| **Avg Day Holding (Win)**     | `12`       | Average holding for winning trades     |
| **Avg Day Holding (Loss)**    | `4`        | Average holding for losing trades      |
| **Expected Time per Trade**   | `2`        | ET                                    |
| **Time Needed for Target**    | `364 Days` |                                      |
""")

# Risk Management Rules Section
st.markdown("""
### ⚠️ **Risk Management Rules**

- **Slow Down**: ⏸️ After 5 consecutive stop losses
- **Stop Trading for a Week**: 🛑 After 10 consecutive stop losses
- **Stop Trading for a Month**: 🛑 After 15 consecutive stop losses
- **Break Taken**: 🍵 After 25 consecutive stop losses
- **Increase Position Size**: 🚀 After 5 consecutive targets hit
- **Losing Trades Caution**: ❗ Stop Trading after 25 back-to-back stop losses
""")

# Divider
st.markdown("---")

# Motivational Punchlines Section
st.markdown("<h2 style='color: #F59E42; text-align:center;'>⚔️ Trader Discipline Punchlines</h2>", unsafe_allow_html=True)

punchlines = [
    "Market ko nahi, apne mind ko master karo.",
    "Fear aur Greed dono ka sirf ek ilaaj hai — Systematic Discipline. ⚖️",
    "Trading me sabse bada profit — Emotional Control.",
    "Loss temporary hota hai, Discipline permanent. ⏳",
    "Dar gaya to har gaya, par bina plan ke lada to barbaad. ⚔️",
    "Consistency beats intensity — har din ek step sahi direction me.",
    "Profit follow karta hai process ko, not emotions ko.",
    "Aaj control kiya emotion, kal control karega market.",
    "Risk manage karo, reward khud line me lag jayega.",
    "Trading ka asli hero wo nahi jo profit kare, wo hai jo calm rahe.",
    "Charts ki language samjho, market ki awaaz suno.",
    "Trade karne se pehle, loss accept karne ki himmat rakho.",
    "Strategy bina, trading sirf speculation hai.",
    "Patience rakhne wale hi market ke king bante hain.",
    "Profit fix nahi hai, process fix karo.",
    "Stop loss lagana weakness nahi, wisdom hai.",
    "Market har kisi ko mauka deta hai, par sirf disciplined ko reward milta hai.",
    "Sab kuch seekh lo, par greed ko kabhi sikhne mat do.",
    "Trading me ego nahi, logic chalta hai.",
    "Jitna bada plan, utni choti position — risk manage karo.",
    "Jab market volatile ho, tab apni discipline double karo.",
    "Analysis ke bina action mat lo, action ke baad regret mat karo.",
    "Trading me patience aur persistence hi asli edge hai.",
    "Profit chase mat karo, opportunity create karo.",
    "Market respect karo, apni strategy pe trust rakho.",
]

st.markdown("<div style='background-color: #FFFBEA; padding: 14px; border-radius: 12px; border: 2px solid #F59E42;'>", unsafe_allow_html=True)
for line in punchlines:
    st.markdown(f"<span style='font-size:1.2em;'>• {line}</span>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# Bonus Power Lines
st.markdown("<h2 style='color: #F43F5E; text-align:center; margin-top:30px;'>🚀 Bonus Power Lines (Wallpaper ke liye)</h2>", unsafe_allow_html=True)

bonus_lines = [
    "Dara hua paisa kabhi paisa nahi banata, par bina rule ka paisa kabhi tikta nahi.",
    "Market me entry sab lete hain, par exit sirf disciplined log karte hain.",
    "Win ya Loss — dono me ek hi feeling rakho, gratitude aur calmness.",
    "Trading tab tak safe hai jab tak tumhara ego trade nahi kar raha.",
    "Emotions chhodo, Execution pe focus karo. ⚡",
    "Loss ko blame mat karo, apne habit ko change karo.",
    "Best trade wo hoti hai jisme rules break nahi hote.",
    "FOMO se bachna, wisdom ki nayi shuruaat hai.",
    "Jo trade miss ho gaya, uska regret nahi, learning lo.",
    "Market aaj bhi hai, kal bhi hoga — discipline har din zaroori hai.",
]

st.markdown("<div style='background-color: #FEE2E2; padding: 14px; border-radius: 12px; border: 2px solid #F43F5E;'>", unsafe_allow_html=True)
for line in bonus_lines:
    st.markdown(f"<span style='font-size:1.1em;'>• {line}</span>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# Footer
st.markdown("---")
st.markdown("<p style='text-align:center; color:#A3A3A3;'>Made with ❤️ for disciplined traders</p>", unsafe_allow_html=True)
