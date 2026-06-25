import streamlit as st

def deprecated_server_ui():
    """
    Deprecated UI for the Server page.
    This function only displays a deprecation notice and does **not**
    expose any of the previous controls.
    """

    # ----------------------------------------------------------------------
    # 1️⃣ Deprecation banner – makes it obvious that this page is obsolete
    # ----------------------------------------------------------------------
    st.title("🚧 Server (Deprecated) 🚧")
    st.warning(
        """
        **This page has been deprecated.**  
        The server management UI has moved to a new location or will be removed in a future release.

        - The start/stop buttons are disabled.
        - Metrics and status information are no longer displayed here.
        - Please refer to the updated documentation or the new dashboard for managing the daemon.
        """
    )

    # ----------------------------------------------------------------------
    # 2️⃣ (Optional) Keep a read‑only snapshot of the last known status
    # ----------------------------------------------------------------------
    # If you still want to show *static* information (e.g., the most recent
    # status that was saved in session state), you can do something like:
    #
    # client = st.session_state.get("daemon")
    # if client is not None:
    #     try:
    #         status = client.status()
    #         col1, col2, col3 = st.columns(3)
    #         col1.metric(
    #             "Status",
    #             "🟢 Running" if status.get("running", False) else "🔴 Stopped",
    #         )
    #         col2.metric("Ticks", status.get("tick_count", "—"))
    #         col3.metric("PID", status.get("pid", "—"))
    #
    #         if status.get("last_results"):
    #             st.subheader("Last Agent Results")
    #             for item in status["last_results"]:
    #                 icon = "✅" if item["success"] else "❌"
    #                 st.write(f"{icon} `{item['agent_name']}`")
    #     except Exception as e:
    #         st.error(f"Could not retrieve status: {e}")

    # ----------------------------------------------------------------------
    # 3️⃣ No interactive controls – they are intentionally omitted
    # ----------------------------------------------------------------------


# --------------------------------------------------------------------------
# Keep the original implementation (commented out) for reference / future use.
# --------------------------------------------------------------------------

# def server_ui():
#     st.title("Server")
#     client = st.session_state.daemon
#
#     status = client.status()
#     running = status.get("running", False)
#
#     col1, col2, col3 = st.columns(3)
#     col1.metric("Status", "🟢 Running" if running else "🔴 Stopped")
#     col2.metric("Ticks", status.get("tick_count", "—"))
#     col3.metric("PID", status.get("pid", "—"))
#
#     d1, d2 = st.columns(2)
#     if d1.button("Start daemon", use_container_width=True, disabled=running):
#         result = client.start()
#         st.toast(
#             f"Started PID {result.get('pid')}"
#             if result.get("started")
#             else "Already running"
#         )
#         st.rerun()
#     if d2.button("Stop daemon", use_container_width=True, disabled=not running):
#         client.stop()
#         st.rerun()
#
#     if status.get("last_results"):
#         st.subheader("Last Agent Results")
#         for item in status["last_results"]:
#             icon = "✅" if item["success"] else "❌"
#             st.write(f"{icon} `{item['agent_name']}`")
#
# --------------------------------------------------------------------------

if __name__ == "__main__":
    deprecated_server_ui()