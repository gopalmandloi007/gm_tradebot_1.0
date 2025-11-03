import streamlit as st
import random
from datetime import date

# ==========================
# Market Wizards — Tabbed Quotes
# English + Hinglish (Hindi-style) side-by-side
# ==========================

st.set_page_config(page_title="Market Wizards Quotes (Hinglish)", layout="wide")

# --- Quotes grouped by category (Hinglish translations) ---
CATEGORIES = {
    "🧠 Fear (Dar & Risk)": [
        {"en": "The key to making money is to not lose money.", "hi": "Paise kamane ki kunji: paise na khona."},
        {"en": "First rule of trading: Don't blow up. Everything else comes later.", "hi": "Trading ka pehla niyam: kabhi account na udaao. Baaki sab baad mein."},
        {"en": "Protect your capital like your life depends on it — because it does.", "hi": "Apni punji ki suraksha karo jaise zindagi uspar nirbhar ho — kyunki sach mein hoti hai."},
        {"en": "If you take care of the losses, the profits will take care of themselves.", "hi": "Losses ko control karo; profits khud thik ho jaayenge."},
        {"en": "When in doubt, get out.", "hi": "Jab sandeh ho, position chod do."},
        {"en": "You can always re-enter — but you can never recover from total loss.", "hi": "Tum phir se entry le sakte ho, lekin total wipeout se wapas aana mushkil hai."},
        {"en": "Cut losses, cut losses, and cut losses.", "hi": "Nuksan chhota karo, baar-baar yaad dilao — cut losses."},
        {"en": "Fear and greed are constant — your job is to stay neutral.", "hi": "Dar aur lalach hamesha rahte hain — tumhara kaam neutral rehna hai."},
        {"en": "If you can't handle small losses, you'll never see big gains.", "hi": "Agar chhote loss bardasht nahi kar sakte, bade munafe nahi dekhoge."}
    ],

    "💰 Greed (Lalach & Patience)": [
        {"en": "Don't focus on making money; focus on protecting what you have.", "hi": "Sirf paise kamane par mat jaao; jo tumhare paas hai usko bachao."},
        {"en": "The big money is made in the sitting, not in the trading.", "hi": "Bada munafa aksar wait karne se aata hai, baar-baar trading se nahi."},
        {"en": "Wait for the fat pitch — not every move is yours to catch.", "hi": "Fat pitch ka intezaar karo — har move tumhara nahi hota."},
        {"en": "Opportunities are like buses — another one always comes.", "hi": "Mauke buses ki tarah hain — ek aur zaroor aayega."},
        {"en": "Don't chase profits; chase perfection in your process.", "hi": "Profit ke peeche mat bhaago; apne process ko perfect karo."},
        {"en": "One good trade is worth a hundred average ones.", "hi": "Ek achha trade sau average trades ke barabar hota hai."},
        {"en": "Patience is the rarest edge in trading.", "hi": "Dhairy hi trading ka sabse anmol edge hai."},
        {"en": "Good traders wait; great traders wait longer.", "hi": "Acche traders intezaar karte hain; behtareen aur bhi lamba intezaar karte hain."},
        {"en": "Fortune favors the disciplined.", "hi": "Kismet unka saath deti hai jo anushasit hote hain."}
    ],

    "🚀 Overconfidence (Ahankar & Ego)": [
        {"en": "Discipline is more important than genius.", "hi": "Anushasan pratibha se zyada mahatvapurn hai."},
        {"en": "The market rewards consistency, not brilliance.", "hi": "Bazaar consistency ko inaam deta hai, sirf brilliance ko nahi."},
        {"en": "A good system is useless without discipline.", "hi": "Accha system bhi bekaar hai jab tak tumhara anushasan nahi hai."},
        {"en": "No system works forever — your flexibility is your real system.", "hi": "Koi system hamesha kaam nahi karega — tumhari lachilapan hi asli system hai."},
        {"en": "Stay humble before the market, or the market will humble you.", "hi": "Market ke samne vinamra raho, nahi to market tumhe sikhayega."},
        {"en": "The best traders evolve; the worst defend their ego.", "hi": "Saphal traders badalte rehte hain; nakam apne ego ki raksha karte hain."},
        {"en": "Your ego is your most expensive position.", "hi": "Tumhara ego tumhara sabse mehnga position hai."},
        {"en": "If you can’t change your mind, you can’t change your results.", "hi": "Agar tum apna mann nahi badal sakte, to apne parinaam badal nahi paoge."},
        {"en": "Be quick to admit mistakes — slow to celebrate success.", "hi": "Galtiyon ko jaldi maano, safalta ko dheere manao."}
    ],

    "⚡ FOMO (Fear of Missing Out & Patience)": [
        {"en": "You don’t need to catch every wave — just the right ones.", "hi": "Har lehar nahi pakadni — sirf sahi lehar pakdo."},
        {"en": "A single good trade can change your year — but one mistake can end your career.", "hi": "Ek accha trade tumhara saal badal sakta hai — par ek badi galti career khatam kar sakti hai."},
        {"en": "Sometimes the best trade is no trade.", "hi": "Kabhi kabhi sabse achha trade, koi trade na karna hota hai."},
        {"en": "Trade small, think big.", "hi": "Chhote se trade karo, bade socho."},
        {"en": "Be passionate, not emotional.", "hi": "Junooni raho, bhavuk mat raho."},
        {"en": "Consistency is the new intelligence.", "hi": "Nirantar hona nayi buddhi hai."},
        {"en": "Calm mind, clear chart, clean trade.", "hi": "Shaant man, saaf chart, saf trade."},
        {"en": "Stay humble, stay prepared, stay alive.", "hi": "Vinarmra raho, taiyar raho, zinda raho."}
    ]
}

# Flatten all quotes for 'All Quotes' tab
ALL_QUOTES = []
for cat, arr in CATEGORIES.items():
    for q in arr:
        ALL_QUOTES.append({"cat": cat, "en": q["en"], "hi": q["hi"]})

# --- Styling ---
st.markdown("<style>
body {background-color: #0f1724; color: #e6eef8}
div.block-container {padding-top: 1rem;}
.card {background: linear-gradient(145deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); border-radius: 8px; padding: 16px; margin-bottom: 12px;}
.en {font-weight: 700; font-size: 18px; color: #ffffff}
.hi {font-style: italic; color: #cde7ff}
.tab-header {font-size:20px; font-weight:700; color:#fff}
</style>", unsafe_allow_html=True)

# --- Header ---
col1, col2 = st.columns([3,1])
with col1:
    st.title("Market Wizards — Daily Mindset (Hinglish)")
    st.markdown("_Tabs: Fear | Greed | Overconfidence | FOMO | All Quotes — English + Hinglish side-by-side_")
with col2:
    if st.button("🎯 Random Inspirational Quote"):
        r = random.choice(ALL_QUOTES)
        st.success(f"{r['en']} — {r['hi']}")

# --- Tabs ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🧠 Fear", "💰 Greed", "🚀 Overconfidence", "⚡ FOMO", "🌟 All Quotes"])

with tab1:
    st.markdown("<div class='tab-header'>Fear & Risk Control</div>", unsafe_allow_html=True)
    for q in CATEGORIES["🧠 Fear (Dar & Risk)"]:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        c1, c2 = st.columns([6,6])
        with c1:
            st.markdown(f"<div class='en'>🔊 {q['en']}</div>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<div class='hi'>✍️ {q['hi']}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

with tab2:
    st.markdown("<div class='tab-header'>Greed & Patience</div>", unsafe_allow_html=True)
    for q in CATEGORIES["💰 Greed (Lalach & Patience)"]:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        c1, c2 = st.columns([6,6])
        with c1:
            st.markdown(f"<div class='en'>🔊 {q['en']}</div>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<div class='hi'>✍️ {q['hi']}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

with tab3:
    st.markdown("<div class='tab-header'>Overconfidence & Ego</div>", unsafe_allow_html=True)
    for q in CATEGORIES["🚀 Overconfidence (Ahankar & Ego)"]:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        c1, c2 = st.columns([6,6])
        with c1:
            st.markdown(f"<div class='en'>🔊 {q['en']}</div>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<div class='hi'>✍️ {q['hi']}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

with tab4:
    st.markdown("<div class='tab-header'>FOMO & Patience</div>", unsafe_allow_html=True)
    for q in CATEGORIES["⚡ FOMO (Fear of Missing Out & Patience)"]:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        c1, c2 = st.columns([6,6])
        with c1:
            st.markdown(f"<div class='en'>🔊 {q['en']}</div>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<div class='hi'>✍️ {q['hi']}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

with tab5:
    st.markdown("<div class='tab-header'>All Quotes — English + Hinglish</div>", unsafe_allow_html=True)
    for i, q in enumerate(ALL_QUOTES, 1):
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        c1, c2 = st.columns([1,4])
        with c1:
            st.markdown(f"**{i}.**")
        with c2:
            st.markdown(f"<div class='en'>🔊 {q['en']}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='hi'>✍️ {q['hi']}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# Footer
st.markdown("---")
st.caption("Developed for daily mindset practice — Quotes adapted into Hinglish for easy daily reading. Not financial advice.")

# End of file
