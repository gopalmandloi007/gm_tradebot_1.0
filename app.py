import streamlit as st

st.set_page_config(page_title="📊 Trade Dashboard", layout="wide")

if "api_session_key" not in st.session_state:
    st.warning("⚠️ Please log in first from the Login page (sidebar).")
    st.stop()

st.title("📊 Trade Dashboard")

st.markdown(
    """
    ## Welcome!

    Use the sidebar to navigate to different sections like Holdings, Orders, Charts, etc.
    """
)
