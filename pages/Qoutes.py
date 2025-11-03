import streamlit as st
import random

# ============================
# 🌟 APP CONFIG
# ============================
st.set_page_config(
    page_title="Market Wizard Quotes Wall",
    page_icon="💹",
    layout="wide"
)

st.title("💬 Market Wizard Daily Quote Wall")
st.markdown("### Read, Reflect & Repeat — Fear | Greed | Overconfidence | FOMO")

# ----------------------------
# 🧠 QUOTES DATA
# ----------------------------
quotes = {
    "Fear": [
        ("Cut your losses quickly.", "Apne loss ko jaldi cut karo, market ke against mat ladho."),
        ("Hope is not a strategy.", "Umeed strategy nahi hoti — plan banao, dua nahi."),
        ("Define your risk before you enter.", "Trade lene se pehle apna risk define karo."),
        ("Don’t fight the market.", "Market ke against mat ladho, uske sath flow karo.")
    ],
    "Greed": [
        ("Pigs get slaughtered. Take profits when you have them.",
         "Lalach me mat padho — profit milta hai to secure karo."),
        ("You don't have to catch every move.", "Market ke har move ko pakadna zaroori nahi."),
        ("Trade the plan, not your emotions.", "Apne plan par chalo, emotions par nahi."),
        ("Money is made by sitting, not trading too much.",
         "Paise kamane me patience chahiye — zyada trading se nahi.")
    ],
    "Overconfidence": [
        ("The market can remain irrational longer than you can remain solvent.",
         "Market tumse zyada time tak galat reh sakta hai, isliye overconfident mat ho."),
        ("Never risk more than you can afford to lose.",
         "Utna hi risk lo jitna lose karne ki capacity ho."),
        ("One good trade doesn’t make you a genius.",
         "Ek accha trade tumhe genius nahi banata."),
        ("Stay humble or the market will make you humble.",
         "Namrata se raho, warna market namrata sikha dega.")
    ],
    "FOMO": [
        ("Missing one trade won’t make you poor.",
         "Ek trade miss hone se tum gareeb nahi ban jaoge."),
        ("Wait for your pitch, not every pitch.",
         "Har trade nahi lena, apna perfect setup ka wait karo."),
        ("Patience is also a position.", "Sabr bhi ek position hoti hai."),
        ("If you chase trades, you’ll lose focus.",
         "Agar trade ke peeche bhagoge, focus kho doge.")
    ]
}

# Merge all for “All Quotes” tab
all_quotes = []
for cat, lst in quotes.items():
    for q in lst:
        all_quotes.append((cat, q[0], q[1]))

# ----------------------------
# 🎨 CUSTOM CARD FUNCTION
# ----------------------------
def quote_card(eng, hin, color):
    st.markdown(
        f"""
        <div style="background-color:{color};padding:15px;border-radius:15px;margin-bottom:10px;
        box-shadow:0 2px 5px rgba(0,0,0,0.2)">
        <h4 style="color:white;">💬 {eng}</h4>
        <p style="color:#f8f9fa;font-size:17px;">📝 {hin}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

# ----------------------------
# 🗂️ TAB LAYOUT
# ----------------------------
tabs = st.tabs(["😨 Fear", "💰 Greed", "😎 Overconfidence", "⚡ FOMO", "🌈 All Quotes"])

tab_colors = ["#2b4c7e", "#146356", "#7a3e65", "#8b2635", "#374045"]

for idx, (tab, (cat, color)) in enumerate(zip(tabs, zip(quotes.keys(), tab_colors))):
    with tab:
        st.markdown(f"### {cat} Quotes — Read and Reflect ✨")
        for eng, hin in quotes[cat]:
            quote_card(eng, hin, color)

# ----------------------------
# 🌟 ALL QUOTES TAB
# ----------------------------
with tabs[4]:
    st.markdown("### All Quotes (Fear + Greed + Overconfidence + FOMO)")
    for cat, eng, hin in all_quotes:
        quote_card(f"[{cat}] {eng}", hin, "#222831")

# ----------------------------
# 🎯 RANDOM QUOTE GENERATOR
# ----------------------------
st.markdown("---")
st.subheader("💡 Random Inspirational Quote for Today")

if st.button("✨ Show Random Quote"):
    cat, eng, hin = random.choice(all_quotes)
    quote_card(f"[{cat}] {eng}", hin, "#4a47a3")
else:
    st.info("Click above to get your daily trading wisdom 💭")

# ----------------------------
# ✍️ FOOTER
# ----------------------------
st.markdown(
    """
    <hr>
    <center>
    <p style='color:gray;'>Made with ❤️ by Gopal Mandloi for Daily Mind Discipline 📈</p>
    </center>
    """,
    unsafe_allow_html=True
)
