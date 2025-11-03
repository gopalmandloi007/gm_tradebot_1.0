import streamlit as st
import random

st.set_page_config(page_title="Trading Mind Quotes - Gopal Mandloi", page_icon="💭", layout="wide")

# Custom CSS for style
st.markdown("""
    <style>
    body {
        background-color: #0e1117;
        color: #fafafa;
    }
    .quote-card {
        background-color: #1e1e1e;
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 15px;
        box-shadow: 0 4px 12px rgba(255,255,255,0.1);
    }
    .quote-en {
        font-size: 18px;
        font-weight: bold;
        color: #00ffcc;
    }
    .quote-hi {
        font-size: 17px;
        color: #ffffff;
    }
    </style>
""", unsafe_allow_html=True)


# Quotes dictionary
quotes = {
    "Fear": [
        ("Cut your losses quickly.", "Apne losses ko jaldi cut karo, hope me mat raho — “shayad wapas aayega” yeh trap hai."),
        ("Hope is not a strategy.", "Umeed strategy nahi hoti bhai — plan banao, dua nahi."),
        ("Define your risk before you enter.", "Trade lene se pehle apna risk fix karo, baad me mat sochna."),
        ("Don’t fight the market.", "Market ke against mat ladho, uske flow ke sath chalo."),
        ("Fear will make you exit too early.", "Dar tumhe profit wale trade se bhi bahar nikal dega."),
        ("Protect your capital first.", "Pehle apna capital bacha, profit baad me kama lena."),
        ("No trade is also a decision.", "Kabhi kabhi trade na lena bhi ek smart trade hoti hai."),
    ],
    "Greed": [
        ("Pigs get slaughtered. Take profits when you have them.", "Lalach me mat padho — profit mile to secure karo."),
        ("You don't have to catch every move.", "Har move ko pakadne ki zarurat nahi hoti."),
        ("Trade the plan, not your emotions.", "Plan pe chalo, emotions pe nahi."),
        ("Money is made by sitting, not trading too much.", "Paise patience se bante hain, overtrading se nahi."),
        ("A greedy trader never survives long.", "Lalach wala trader zyada din market me nahi tikta."),
        ("Small consistent profits beat big random wins.", "Chhote stable profits badi lucky jeet se behtar hote hain."),
        ("Book profit, don’t marry your stocks.", "Stock se pyar nahi, timing se paisa banta hai."),
    ],
    "Overconfidence": [
        ("The market can remain irrational longer than you can remain solvent.", "Market tumse zyada time tak galat reh sakta hai — overconfident mat ho."),
        ("Never risk more than you can afford to lose.", "Utna hi risk lo jitna lose karne ki capacity ho."),
        ("One good trade doesn’t make you a genius.", "Ek accha trade tumhe genius nahi banata."),
        ("Stay humble or the market will make you humble.", "Namrata se raho, warna market namrata sikha dega."),
        ("When you think you can’t lose, that’s when you do.", "Jab lagta hai ab kabhi loss nahi hoga — wahi galti hoti hai."),
        ("Confidence comes from process, not results.", "Real confidence process se aata hai, result se nahi."),
        ("Market rewards discipline, not ego.", "Market discipline ko reward karta hai, ego ko punish."),
    ],
    "FOMO": [
        ("Missing one trade won’t make you poor.", "Ek trade miss hone se koi gareeb nahi hota."),
        ("Wait for your pitch, not every pitch.", "Har opportunity par mat koodo, apna setup ka wait karo."),
        ("Patience is also a position.", "Sabr bhi ek position hoti hai."),
        ("If you chase trades, you’ll lose focus.", "Agar har trade ke peeche bhagoge, focus kho doge."),
        ("Market will always give another chance.", "Market hamesha doosra mauka deta hai, panic mat karo."),
        ("Entry late se better hai galat entry.", "Late entry sahi hai, galat entry nahi."),
        ("Let the trade come to you.", "Trade tumhare paas aane do, zabardasti mat karo."),
    ],
    "Bonus": [
        ("Trade what you see, not what you think.", "Jo chart dikhata hai wahi trade karo, apna guess nahi."),
        ("Losing is part of learning.", "Har loss ek lesson hai, fail nahi."),
        ("Discipline beats intelligence.", "Smart hone se zyada important hai discipline."),
        ("Market rewards patience and punishes impulsiveness.", "Market patience ko reward karta hai, impulsiveness ko punish."),
        ("Fear + Greed control = Freedom.", "Jab fear aur greed dono control me ho jaayein, tab milta hai financial freedom."),
    ]
}

# Header
st.title("💭 Trading Psychology Quotes - Gopal Mandloi")
st.markdown("### Master Your Mindset: Fear, Greed, Overconfidence, FOMO & Discipline")

# Tabs
tabs = st.tabs(["😨 Fear", "💰 Greed", "😎 Overconfidence", "⚡ FOMO", "🌈 Bonus"])

for i, (tab_name, quote_list) in enumerate(quotes.items()):
    with tabs[i]:
        st.subheader(f"{tab_name} Quotes")
        random_quote = random.choice(quote_list)
        if st.button(f"🎲 Random {tab_name} Quote"):
            random_quote = random.choice(quote_list)

        with st.container():
            st.markdown(f"""
                <div class='quote-card'>
                    <div class='quote-en'>💬 {random_quote[0]}</div>
                    <div class='quote-hi'>📝 {random_quote[1]}</div>
                </div>
            """, unsafe_allow_html=True)

        # Show all quotes in the tab
        for en, hi in quote_list:
            st.markdown(f"""
                <div class='quote-card'>
                    <div class='quote-en'>💬 {en}</div>
                    <div class='quote-hi'>📝 {hi}</div>
                </div>
            """, unsafe_allow_html=True)

st.markdown("---")
st.caption("Created with ❤️ by Gopal Mandloi | Inspired by Market Wizards & Trading Legends")
