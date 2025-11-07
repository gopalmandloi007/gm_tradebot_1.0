import streamlit as st
import random

# Page Config
st.set_page_config(page_title="Trading Mind Quotes - Gopal Mandloi", page_icon="💭", layout="wide")

# Custom CSS
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

# 💡 Helper function
def trader_section(name, emoji, quote_pairs):
    st.subheader(f"{emoji} {name}")
    for en, hi in quote_pairs:
        st.markdown(f"""
            <div class='quote-card'>
                <div class='quote-en'>💬 {en}</div>
                <div class='quote-hi'>📝 {hi}</div>
            </div>
        """, unsafe_allow_html=True)

# 🧠 Categories
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

# 🌟 Page Header
st.title("💭 Trading Psychology Quotes - Gopal Mandloi")
st.markdown("### Master Your Mindset: Fear, Greed, Overconfidence, FOMO & Discipline")

# 🗂️ Tabs for emotion-based quotes
tabs = st.tabs(["😨 Fear", "💰 Greed", "😎 Overconfidence", "⚡ FOMO", "🌈 Bonus"])
for i, (tab_name, quote_list) in enumerate(quotes.items()):
    with tabs[i]:
        st.subheader(f"{tab_name} Quotes")
        random_quote = random.choice(quote_list)
        if st.button(f"🎲 Random {tab_name} Quote"):
            random_quote = random.choice(quote_list)

        st.markdown(f"""
            <div class='quote-card'>
                <div class='quote-en'>💬 {random_quote[0]}</div>
                <div class='quote-hi'>📝 {random_quote[1]}</div>
            </div>
        """, unsafe_allow_html=True)

        for en, hi in quote_list:
            st.markdown(f"""
                <div class='quote-card'>
                    <div class='quote-en'>💬 {en}</div>
                    <div class='quote-hi'>📝 {hi}</div>
                </div>
            """, unsafe_allow_html=True)

# 🔥 Trader Wisdom Section
st.markdown("---")
st.header("📘 Trading Legends & Their Wisdom")

trader_section("Mark Minervini", "🚀", [
    ("You don’t have to be right a lot, you just have to lose little when you’re wrong.",
     "Galat hone par chhota loss lo — bada loss mat hone do."),
    ("Discipline is the bridge between goals and accomplishment.",
     "Discipline hi sapno aur success ke beech ka bridge hai."),
    ("Protect your capital as if your life depends on it – because it does.",
     "Apni capital ko apni jaan ki tarah bachao.")
])

trader_section("Nicolas Darvas", "💼", [
    ("I made up my mind to buy high and sell higher.",
     "Cheap stocks ke chakkar me mat padho, momentum stocks pakdo."),
    ("I believe in analysis, not in forecasting.",
     "Guesswork nahi, analysis karo."),
    ("I have no ego in the stock market, if I’m wrong, I sell immediately.",
     "Ego nahi — galat ho to turant nikal jao.")
])

trader_section("William O’Neil", "📘", [
    ("Cut your losses at 7% or 8%, no exceptions.",
     "Rule fix karo — loss chhota rakho."),
    ("Great stocks are found in great industries during uptrends.",
     "Strong sectors me hi strong stocks milte hain."),
    ("Buy when a stock breaks out of its base on heavy volume.",
     "Volume ke sath breakout me entry lo.")
])

trader_section("Paul Tudor Jones", "💰", [
    ("Don’t focus on making money, focus on protecting what you have.",
     "Pehle paisa bachao, fir kamao."),
    ("Losers average losers.",
     "Girte stocks me averaging mat karo."),
    ("Play great defense, not great offense.",
     "Trading me defense hi best strategy hai.")
])

trader_section("Peter Lynch", "🔍", [
    ("Know what you own, and know why you own it.",
     "Jo kharido use samjho, blindly mat follow karo."),
    ("In stocks, time is your friend; impulse is your enemy.",
     "Patience se paisa banta hai, impulse se nahi.")
])

trader_section("Jesse Livermore", "⚔️", [
    ("The big money is not in the buying and selling, but in the waiting.",
     "Bada paisa patience se banta hai."),
    ("Markets are never wrong; opinions often are.",
     "Market kabhi galat nahi hota, opinion galat hote hain.")
])

trader_section("Stan Weinstein", "📊", [
    ("Never buy or sell without checking the chart.",
     "Chart hi guide hai — bina dekhe trade mat lo."),
    ("Buy Stage 2 strength; sell Stage 4 weakness.",
     "Stage 2 me buy karo, Stage 4 me sell karo."),
])

trader_section("Warren Buffett", "🧓", [
    ("Be fearful when others are greedy, and greedy when others are fearful.",
     "Jab sab dar rahe ho tab kharido."),
    ("Rule No.1: Never lose money. Rule No.2: Never forget Rule No.1.",
     "Loss se bacho — yahi sabse bada rule hai.")
])

st.markdown("---")
st.caption("Created with ❤️ by Gopal Mandloi | Inspired by Market Wizards & Trading Legends")
