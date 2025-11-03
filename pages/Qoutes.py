import streamlit as st
import random
from datetime import date

# --- Categorized Market Wizards Quotes with Hindi Translations ---
CATEGORIES = {
    "🧠 Fear": [
        {"en": "The key to making money is to not lose money.", "hi": "Paise kamane ki kunji hai: paise na khona."},
        {"en": "First rule of trading: Don't blow up. Everything else comes later.", "hi": "Trading ka pehla niyam: khata-mukht na ho. Baaki sab baad mein."},
        {"en": "Protect your capital like your life depends on it — because it does.", "hi": "Apne punji ki raksha karo jaise tumhari zindagi uspar nirbhar ho — kyunki sach mein hoti hai."},
        {"en": "If you take care of the losses, the profits will take care of themselves.", "hi": "Agar tum losses ka dhyan rakho, profits apne aap sambhal lenge."},
        {"en": "When in doubt, get out.", "hi": "Sandeh ho to nikal jao."},
        {"en": "You can always re-enter — but you can never recover from total loss.", "hi": "Tum hamesha phir se enter kar sakte ho — lekin total loss se wapas paana mushkil hai."},
        {"en": "Cut losses, cut losses, and cut losses.", "hi": "Nuksan chhota karo, nuksan chhota karo, aur nuksan chhota karo."},
        {"en": "Fear and greed are constant — your job is to stay neutral.", "hi": "Dar aur lobh sadaiv hote hain — tumhara kaam neutral rehna hai."},
        {"en": "If you can't handle small losses, you'll never see big gains.", "hi": "Agar tum chhote nuksan bardasht nahi kar sakte, to bade munafe nahi dekhoge."}
    ],

    "💰 Greed": [
        {"en": "Don't focus on making money; focus on protecting what you have.", "hi": "Sirf paise kamane par dhyan mat do; jo tumhare paas hai, uski raksha par dhyan do."},
        {"en": "The big money is made in the sitting, not in the trading.", "hi": "Bade paise wait karke bante hain, baar-baar trading se nahi."},
        {"en": "Wait for the fat pitch — not every move is yours to catch.", "hi": "Behtareen mauke ka intezaar karo — har move tumhara nahi hota."},
        {"en": "Opportunities are like buses — another one always comes.", "hi": "Mauke buses jaise hain — ek aur zaroor aayega."},
        {"en": "Don't chase profits; chase perfection in your process.", "hi": "Munafa ke peeche mat bhaago; apne process mein perfection ka peecha karo."},
        {"en": "One good trade is worth a hundred average ones.", "hi": "Ek achha trade sau average trades ke barabar hota hai."},
        {"en": "Patience is the rarest edge in trading.", "hi": "Dharya trading mein sabse rare advantage hai."},
        {"en": "Good traders wait; great traders wait longer.", "hi": "Acche traders intezaar karte hain; mahan traders aur lamba intezaar karte hain."},
        {"en": "Fortune favors the disciplined.", "hi": "Kismet anushasit logon ka saath deti hai."}
    ],

    "🚀 Overconfidence": [
        {"en": "Discipline is more important than genius.", "hi": "Anushasan pratibha se adhik mahatvapurn hai."},
        {"en": "The market rewards consistency, not brilliance.", "hi": "Bazaar consistency ko inaam deta hai, brilliance ko nahi."},
        {"en": "A good system is useless without discipline.", "hi": "Acche system ka koi fayda nahi jab tak anushasan na ho."},
        {"en": "No system works forever — your flexibility is your real system.", "hi": "Koi system hamesha kaam nahi karta — tumhari lachilapan tumhara asal system hai."},
        {"en": "Stay humble before the market, or the market will humble you.", "hi": "Market ke saamne vinamra raho, nahi to market tumhe vinamra karega."},
        {"en": "The best traders evolve; the worst defend their ego.", "hi": "Behtareen traders badalte hain; kharab traders apne ego ki raksha karte hain."},
        {"en": "Your ego is your most expensive position.", "hi": "Tumhara ego tumhara sabse mehnga position hai."},
        {"en": "If you can’t change your mind, you can’t change your results.", "hi": "Agar tum apna man nahi badal sakte, to apne parinaam nahi badal sakte."},
        {"en": "Be quick to admit mistakes — slow to celebrate success.", "hi": "Galati kabool karne mein tezi rakho — safalta celebrate karne mein dhairya rakho."}
    ],

    "⚡ FOMO": [
        {"en": "You don’t need to catch every wave — just the right ones.", "hi": "Har dhar ka pakad zaroori nahi - sirf sahi dhar pakdo."},
        {"en": "A single good trade can change your year — but one mistake can end your career.", "hi": "Ek achha trade tumhara saal badal sakta hai - par ek galti tumhari career khatam kar sakti hai."},
        {"en": "Sometimes the best trade is no trade.", "hi": "Kabhi-kabhi sabse achha trade, koi trade na karna hota hai."},
        {"en": "Trade small, think big.", "hi": "Chhote trades karo, bade socho."},
        {"en": "Be passionate, not emotional.", "hi": "Junooni raho, bhavuk mat raho."},
        {"en": "Consistency is the new intelligence.", "hi": "Lagataar hona nayi buddhimatta hai."},
        {"en": "Calm mind, clear chart, clean trade.", "hi": "Shaant man, saaf chart, saf trade."},
        {"en": "Stay humble, stay prepared, stay alive.", "hi": "Vinamra raho, taiyar raho, zinda raho."}
    ]
}

# --- Streamlit UI ---
st.set_page_config(page_title="Market Wizards Mindset Quotes", layout="centered")
st.title("💡 Market Wizards Mindset Quotes")
st.caption("Read daily. Control Fear, Defeat Greed, Kill Overconfidence, and Master FOMO.")

st.sidebar.header("⚙️ Options")
category = st.sidebar.selectbox("Select Emotion Category", list(CATEGORIES.keys()))
mode = st.sidebar.radio("Display Mode", ["Daily Quote", "Random Quote", "Browse All"])
show_hi = st.sidebar.checkbox("Show Hindi Translation", value=True)

# --- Helper to Show Quote ---
def show_quote(q):
    st.markdown(f"### 🧭 {q['en']}")
    if show_hi:
        st.markdown(f"_\u0939\u093f\u0902\u0926\u0940:_ {q['hi']}")

quotes = CATEGORIES[category]

# --- Daily Mode ---
if mode == "Daily Quote":
    idx = date.today().toordinal() % len(quotes)
    st.subheader(f"📅 Today's Quote — {category}")
    show_quote(quotes[idx])
    st.markdown(f"_Quote {idx+1} of {len(quotes)}_")
    if st.button("🔀 Show Another Random Quote"):
        show_quote(random.choice(quotes))

# --- Random Mode ---
elif mode == "Random Quote":
    st.subheader(f"🎯 Random Quote — {category}")
    q = random.choice(quotes)
    show_quote(q)
    if st.button("Next Random"):
        show_quote(random.choice(quotes))

# --- Browse Mode ---
else:
    st.subheader(f"📚 Browse All — {category}")
    for i, q in enumerate(quotes, 1):
        st.markdown(f"**{i}.** {q['en']}")
        if show_hi:
            st.markdown(f"_\u0939\u093f\u0902\u0926\u0940:_ {q['hi']}")
        st.markdown("---")

st.markdown("---")
st.caption("⚠️ Inspired by Jack Schwager's Market Wizards interviews — use for mindset training, not financial advice.")
