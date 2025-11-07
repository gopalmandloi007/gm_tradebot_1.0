import streamlit as st
from PIL import Image

st.set_page_config(page_title="Legendary Trader Rules & Quotes", page_icon="📈", layout="wide")

st.title("💹 Legendary Traders’ Rules & Quotes")
st.markdown("### 🧠 Mindset | 📊 Strategy | 💰 Risk Management | 🔥 Discipline")

st.markdown("---")

# Function for clean layout
def trader_section(name, emoji, quotes):
    st.markdown(f"## {emoji} **{name}**")
    for q, h in quotes:
        st.markdown(f"""
        💬 *{q}*  
        👉 {h}
        """)
    st.markdown("---")

# MARK MINERVINI
trader_section("Mark Minervini", "🚀", [
    ("You don’t have to be right a lot, you just have to lose little when you’re wrong.",
     "Galat hone par chhota loss lo — bada loss mat hone do."),
    ("Discipline is the bridge between goals and accomplishment.",
     "Discipline hi sapno aur success ke beech ka bridge hai."),
    ("The stock market transfers money from the impatient to the patient.",
     "Market unse paisa lekar deta hai jo impatient hain, unko jo patient hain."),
    ("Protect your capital as if your life depends on it – because it does.",
     "Apni capital ko apni jaan ki tarah bachao.")
])

# NICOLAS DARVAS
trader_section("Nicolas Darvas", "💼", [
    ("I made up my mind to buy high and sell higher.",
     "Cheap stocks ke chakkar me mat padho, momentum stocks pakdo."),
    ("I believe in analysis, not in forecasting.",
     "Guesswork nahi, analysis karo."),
    ("I have no ego in the stock market, if I’m wrong, I sell immediately.",
     "Ego nahi — galat ho to turant nikal jao."),
    ("The only sound reason for buying a stock is that it is rising in price.",
     "Sirf wahi stock kharido jo upar ja raha ho.")
])

# WILLIAM O’NEIL
trader_section("William O’Neil", "📘", [
    ("Cut your losses at 7% or 8%, no exceptions.",
     "Rule fix karo — loss chhota rakho."),
    ("The secret to winning is losing the least when you’re wrong.",
     "Kam loss lena hi jeet ka secret hai."),
    ("Great stocks are found in great industries during uptrends.",
     "Strong sectors me hi strong stocks milte hain."),
    ("Buy when a stock breaks out of its base on heavy volume.",
     "Volume ke sath breakout me entry lo.")
])

# PAUL TUDOR JONES
trader_section("Paul Tudor Jones", "💰", [
    ("Don’t focus on making money, focus on protecting what you have.",
     "Pehle paisa bachao, fir kamao."),
    ("Losers average losers.",
     "Girte stocks me averaging mat karo."),
    ("Play great defense, not great offense.",
     "Trading me defense hi best strategy hai."),
    ("Every day I assume every position I have is wrong.",
     "Alert rehne ke liye har din maan lo ki tum galat ho sakte ho.")
])

# PETER LYNCH
trader_section("Peter Lynch", "🔍", [
    ("Know what you own, and know why you own it.",
     "Jo kharido use samjho, blindly mat follow karo."),
    ("The person who turns over the most rocks wins the game.",
     "Research karo, opportunities dhoondo."),
    ("In stocks, time is your friend; impulse is your enemy.",
     "Patience se paisa banta hai, impulse se nahi."),
    ("You get stock market declines. If you don't understand that, you’re not ready.",
     "Market girta hai, ye normal hai — ready raho.")
])

# JESSE LIVERMORE
trader_section("Jesse Livermore", "⚔️", [
    ("The big money is not in the buying and selling, but in the waiting.",
     "Bara paisa patience se banta hai."),
    ("It was never my thinking that made the big money, it was my sitting.",
     "Sochne se nahi, baithne se paisa banta hai."),
    ("Markets are never wrong; opinions often are.",
     "Market kabhi galat nahi hota, opinion galat hote hain."),
    ("There is nothing new on Wall Street.",
     "Market psychology kabhi nahi badalti.")
])

# STAN WEINSTEIN
trader_section("Stan Weinstein", "📊", [
    ("Never buy or sell without checking the chart.",
     "Chart hi guide hai — bina dekhe trade mat lo."),
    ("Buy Stage 2 strength; sell Stage 4 weakness.",
     "Stage 2 me buy karo, Stage 4 me sell karo."),
    ("It’s better to be late and right than early and wrong.",
     "Late hona better hai agar direction sahi hai."),
    ("Always be consistent – inconsistency kills traders.",
     "Consistency hi trading success ka base hai.")
])

# GEORGE SOROS
trader_section("George Soros", "💡", [
    ("It's not whether you're right or wrong, but how much you make when you're right and how much you lose when you're wrong.",
     "Accuracy nahi, risk-reward matter karta hai.")
])

# WARREN BUFFETT
trader_section("Warren Buffett", "🧓", [
    ("Be fearful when others are greedy, and greedy when others are fearful.",
     "Jab sab dar rahe ho tab kharido."),
    ("Rule No.1: Never lose money. Rule No.2: Never forget Rule No.1.",
     "Loss se bacho — yahi sabse bada rule hai.")
])

st.success("✨ Summary: Trading me sabse bada edge mindset aur risk control hai. Charts, systems aur indicators tabhi kaam karte hain jab trader emotionally stable rahe. 💯")

