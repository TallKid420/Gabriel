import streamlit as st

def server_ui():
    st.title("Server")

    st.header("Server Status")
    
    daemon_status = st.session_state.daemon.status()
    st.write(f"Running: `{daemon_status['running']}`")
    st.write(f"Ticks: `{daemon_status['tick_count']}`")

    if daemon_status.get("last_results"):
        st.subheader("Daemon results")
        for item in daemon_status["last_results"]:
            st.write(f"{item['agent_name']}: {'ok' if item['success'] else 'error'}")

    d1, d2 = st.columns(2)
    if d1.button("Start daemon", use_container_width=True):
        st.session_state.daemon.start()
        st.rerun()
    if d2.button("Stop daemon", use_container_width=True):
        st.session_state.daemon.stop()
        st.rerun()

if __name__ == "__main__":
    server_ui()