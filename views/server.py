import streamlit as st

def server_ui():
    st.title("Server")
    client = st.session_state.daemon

    status = client.status()
    running = status.get("running", False)

    col1, col2, col3, = st.columns(3)
    col1.metric("Status", "🟢 Running" if running else "🔴 Stopped")
    col2.metric("Ticks", status.get("tick_count", "—"))
    col3.metric("PID", status.get("pid", "—"))

    d1, d2 = st.columns(2)
    if d1.button("Start daemon", use_container_width=True, disabled=running):
        result = client.start()
        st.toast(f"Started PID {result.get('pid')}" if result.get("started") else "Already running")
        st.rerun()
    if d2.button("Stop daemon", use_container_width=True, disabled=not running):
        client.stop()
        st.rerun()

    if status.get("last_results"):
        st.subheader("Last Agent Results")
        for item in status["last_results"]:
            icon = "✅" if item["success"] else "❌"
            st.write(f"{icon} `{item['agent_name']}`")

if __name__ == "__main__":
    server_ui()