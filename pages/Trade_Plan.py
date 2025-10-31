import streamlit as st
import json
import random
from fpdf import FPDF
from datetime import date

# --- THEME & COLOR ---
theme_colors = {
    "Blue-Green": {"primary": "#3B82F6", "secondary": "#16A34A", "accent": "#F59E42", "bg": "#E0F2FE"},
    "Purple-Orange": {"primary": "#A21CAF", "secondary": "#F59E42", "accent": "#F43F5E", "bg": "#FFF7ED"},
    "Classic": {"primary": "#374151", "secondary": "#FBBF24", "accent": "#6366F1", "bg": "#F3F4F6"}
}

if "theme" not in st.session_state:
    st.session_state["theme"] = "Blue-Green"
if "dark_mode" not in st.session_state:
    st.session_state["dark_mode"] = False

st.sidebar.header("🎨 Theme & Appearance")
theme_choice = st.sidebar.selectbox("Color Theme", list(theme_colors.keys()), index=list(theme_colors.keys()).index(st.session_state["theme"]))
st.session_state["theme"] = theme_choice
dark_mode = st.sidebar.toggle("🌑 Dark Mode", value=st.session_state["dark_mode"])
st.session_state["dark_mode"] = dark_mode

primary = theme_colors[theme_choice]['primary']
secondary = theme_colors[theme_choice]['secondary']
accent = theme_colors[theme_choice]['accent']
bg = theme_colors[theme_choice]['bg']

# ---- MOTIVATION WIDGET ----
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
    "Trading ka asli hero wo nahi jo profit kare, wo hai jo calm rahe."
]
quote_of_the_day = random.choice(punchlines)
st.markdown(f"""
<div style='background:{accent}; border-radius:18px; padding:10px; text-align:center; margin-bottom:12px;'>
    <span style='font-size:1.3em;color:white;'>🗣️ <b>Motivation Today:</b> "{quote_of_the_day}"</span>
</div>
""", unsafe_allow_html=True)

# ---- UPLOAD / DOWNLOAD ----
st.sidebar.header("📥 Upload / 📤 Download Plan")
uploaded_file = st.sidebar.file_uploader("Upload Trading Plan (JSON)", type=["json"])
if uploaded_file:
    data = json.load(uploaded_file)
    st.session_state.update(data)
    st.sidebar.success("Plan loaded!")

def download_pdf():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 18)
    pdf.cell(0, 10, "Trading Plan", ln=1, align='C')
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Date: {date.today().isoformat()}", ln=1, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", "B", 14)
    pdf.set_text_color(0, 102, 204)
    pdf.cell(0, 10, "Capital & Risk", ln=1)
    pdf.set_font("Arial", size=12)
    for k, v in st.session_state["plan"].items():
        pdf.cell(0, 8, f"{k}: {v}", ln=1)
    pdf.ln(5)
    pdf.set_font("Arial", "B", 14)
    pdf.set_text_color(255, 85, 85)
    pdf.cell(0, 10, "Punchlines", ln=1)
    pdf.set_font("Arial", size=12)
    for line in punchlines:
        pdf.cell(0, 8, f"- {line}", ln=1)
    return pdf.output(dest='S').encode('latin1')

if st.sidebar.button("Download as PDF"):
    if "plan" in st.session_state:
        pdf_bytes = download_pdf()
        st.sidebar.download_button(label="📄 Download PDF", data=pdf_bytes, file_name="TradingPlan.pdf", mime="application/pdf")
    else:
        st.sidebar.warning("Please fill out your plan first.")

st.sidebar.header("💾 Save/Load Settings")
def default_plan():
    return {
        "Total Capital": 1112000,
        "Win Rate (%)": 35,
        "Avg Day Holding (Win)": 12,
        "Avg Day Holding (Loss)": 4
    }
if "plan" not in st.session_state:
    st.session_state["plan"] = default_plan()

total_capital = st.sidebar.number_input("Total Capital (₹)", min_value=10000, value=st.session_state["plan"]["Total Capital"], step=10000)
win_rate = st.sidebar.slider("Win Rate (%)", min_value=10, max_value=100, value=st.session_state["plan"]["Win Rate (%)"], step=1)
holding_win = st.sidebar.number_input("Avg Day Holding (Win)", min_value=1, value=st.session_state["plan"]["Avg Day Holding (Win)"], step=1)
holding_loss = st.sidebar.number_input("Avg Day Holding (Loss)", min_value=1, value=st.session_state["plan"]["Avg Day Holding (Loss)"], step=1)
st.session_state["plan"] = {
    "Total Capital": total_capital,
    "Win Rate (%)": win_rate,
    "Avg Day Holding (Win)": holding_win,
    "Avg Day Holding (Loss)": holding_loss
}
settings_json = json.dumps(st.session_state["plan"], indent=2)
st.sidebar.download_button("Save Settings as JSON", data=settings_json, file_name="TradingPlanSettings.json", mime="application/json")

# ---- CALCULATIONS ----
win_rate_dec = win_rate / 100
position_size = total_capital * 0.1
risk_per_trade = position_size * 0.02
risk_of_total_capital = total_capital * 0.005
reward_per_win = risk_per_trade * 5
target_profit_yearly = total_capital * 0.5
target_time_days = 365
max_drawdown = total_capital * 0.05
ev_per_trade = (win_rate_dec * reward_per_win) - ((1 - win_rate_dec) * risk_per_trade)
trades_needed = target_profit_yearly / ev_per_trade if ev_per_trade > 0 else 0
et_per_trade = (win_rate_dec * holding_win) - ((1 - win_rate_dec) * holding_loss)
time_needed_days = trades_needed * et_per_trade if et_per_trade > 0 else 0
lossing_trades_caution = max_drawdown / risk_per_trade if risk_per_trade > 0 else 0
initial_trade_capital = position_size

# ---- FIT TO WINDOW & ATTRACTIVE INFO ----
st.markdown(f"""
<style>
    .stApp {{
        background-color: {bg} !important;
    }}
    .info-card {{
        background: linear-gradient(90deg, {primary}20 0%, {secondary}30 100%);
        border-radius: 18px;
        padding: 16px 24px 16px 24px;
        margin-bottom: 18px;
        box-shadow: 2px 2px 10px 0px #00000018;
    }}
    .risk-card {{
        background: linear-gradient(90deg, {accent}40 0%, #fff 100%);
        border-radius: 18px;
        padding: 16px 24px 16px 24px;
        margin-bottom: 18px;
        box-shadow: 2px 2px 10px 0px #00000018;
    }}
    .stage-card {{
        background: linear-gradient(90deg, {primary}20 0%, {accent}20 100%);
        border-radius: 18px;
        padding: 16px 24px;
        margin-bottom: 18px;
        box-shadow: 2px 2px 10px 0px #00000018;
    }}
</style>
""", unsafe_allow_html=True)

# ---- MAIN PAGE ----
st.markdown(f"<h1 style='text-align:center; color:{primary};'>📈 Trading Plan</h1>", unsafe_allow_html=True)
st.markdown("---")

st.markdown(f"""
<div class='info-card'>
    <h3 style='color:{secondary};'><span style='font-size:1.3em;'>💰 Capital & Risk Management</span></h3>
    <b>Total Capital:</b> <span style='color:{primary};'>₹{total_capital:,.0f}</span> &nbsp;|&nbsp;
    <b>Position Size:</b> <span style='color:{secondary};'>₹{position_size:,.0f}</span> &nbsp;|&nbsp;
    <b>Risk per Trade (2%):</b> <span style='color:#F43F5E;'>₹{risk_per_trade:,.0f}</span> &nbsp;|&nbsp;
    <b>Reward per Win:</b> <span style='color:{secondary};'>₹{reward_per_win:,.0f}</span> &nbsp;|&nbsp;
    <b>Win Rate:</b> <span style='color:{primary};'>{win_rate}%</span>
    <br>
    <b>Target Profit (50% Yearly):</b> ₹{target_profit_yearly:,.0f} &nbsp;|&nbsp;
    <b>Trades Needed for Target:</b> {trades_needed:,.0f} &nbsp;|&nbsp;
    <b>Expected Value/Trade:</b> ₹{ev_per_trade:,.1f}
    <br>
    <b>Drawdown Allowed (5%):</b> ₹{max_drawdown:,.0f} &nbsp;|&nbsp;
    <b>Lossing Trades Caution:</b> {lossing_trades_caution:,.0f}
</div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class='info-card'>
    <h3 style='color:{accent};'><span style='font-size:1.3em;'>📊 Trade Frequency & Timing</span></h3>
    <b>Avg Day Holding (Win):</b> <span style='color:{secondary};'>{holding_win}</span> days &nbsp;|&nbsp;
    <b>Avg Day Holding (Loss):</b> <span style='color:#F43F5E;'>{holding_loss}</span> days &nbsp;|&nbsp;
    <b>ET per Trade:</b> <span style='color:{primary};'>{et_per_trade:.1f}</span> days
    <br>
    <b>Time Needed for Target:</b> <span style='color:{accent};'>{time_needed_days:,.0f}</span> days
</div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class='stage-card'>
    <h3 style='color:{primary};'><span style='font-size:1.2em;'>🚀 Strategy Progression & Scaling</span></h3>
    <ul>
        <li><b>Stage I:</b> Initial Trade Capital — 10% to 20% for Testing</li>
        <li><b>Stage II:</b> Profitable Trades Confidence After 1 Trade — 30% to 50% Risk Financed</li>
        <li><b>Stage III:</b> Profitable Trades Confidence After 8-10 Trades — 100% Fully Financed</li>
        <li><b>Stage IV:</b> Profitable Trades Confidence After 10 Trades — 100% + Increased Position Size (Compounding)</li>
    </ul>
</div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class='risk-card'>
    <h3 style='color:{accent};'><span style='font-size:1.2em;'>⚠️ Risk Management Rules</span></h3>
    <ul>
        <li><b>⏸️ Slow Down:</b> After 5 consecutive stop losses</li>
        <li><b>🛑 Stop Trading for a Week:</b> After 10 consecutive stop losses</li>
        <li><b>🛑 Stop Trading for a Month:</b> After 15 consecutive stop losses</li>
        <li><b>🍵 Break Taken:</b> After 25 consecutive stop losses</li>
        <li><b>🚀 Increase Position Size:</b> After 5 consecutive targets hit</li>
        <li><b>❗ Losing Trades Caution:</b> Stop Trading after 25 back-to-back stop losses</li>
    </ul>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ---- MOTIVATIONAL LINES ----
st.markdown(f"<h2 style='color:{accent}; text-align:center;'>🧠 Trader Mindset Punchlines</h2>", unsafe_allow_html=True)
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
        st.markdown(f"<span style='color:{secondary}; font-size:1.1em;'>• {line}</span>", unsafe_allow_html=True)

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
        st.markdown(f"<span style='color:{primary}; font-size:1.1em;'>• {line}</span>", unsafe_allow_html=True)

st.markdown("---")

# ---- BONUS LINES ----
st.markdown(f"<h2 style='color:{accent}; text-align:center;'>🚀 Bonus Power Lines (Wallpaper ke liye)</h2>", unsafe_allow_html=True)
bonus_lines = [
    "Market me entry sab lete hain, par exit sirf disciplined log karte hain.",
    "Trading me ego nahi, logic chalta hai.",
    "Trading ka asli hero wo nahi jo profit kare, wo hai jo calm rahe.",
    "Market har kisi ko mauka deta hai, par sirf disciplined ko reward milta hai.",
    "Profit fix nahi hai, process fix karo.",
]
st.markdown(f"<div style='background-color: #fee2e2; padding: 14px; border-radius: 12px; border: 2px solid {accent};'>", unsafe_allow_html=True)
for line in bonus_lines:
    st.markdown(f"<span style='font-size:1.1em;'>• {line}</span>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("---")
st.markdown(f"<p style='text-align:center; color:{primary}; font-size:1.1em;'>Made with ❤️ for disciplined traders</p>", unsafe_allow_html=True)

# ---- DARK MODE CSS ----
if dark_mode:
    st.markdown("""
        <style>
        .stApp { background-color: #23272f !important; }
        h1, h2, h3, h4, h5, h6, p, span, div { color: #e0e7ef !important; }
        .info-card, .risk-card, .stage-card { background: #23272f !important; color: #e0e7ef !important;}
        .stMetric { background-color: #2d3748 !important; border-radius:10px; }
        </style>
    """, unsafe_allow_html=True)
