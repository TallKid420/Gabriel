import streamlit as st

def settings_ui():
    st.title("Settings")

    st.header("Agent configuration")
    st.write("Configure the available agents and their settings here.")

if __name__ == "__main__":
    settings_ui()