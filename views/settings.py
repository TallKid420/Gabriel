import logging

import streamlit as st

from app import get_api

log = logging.getLogger(__name__)


def settings_ui():
    st.title("⚙️ Settings")

    api = get_api()
    daemon = st.session_state.daemon

    tabs = st.tabs([
        "Agent Control",
        "System Configuration",
        "Database Settings",
        "Preferences"
    ])

    # ==========================================
    # Tab 1: Agent Control
    # ==========================================
    with tabs[0]:
        st.header("Agent Control")
        st.write("Enable or disable agents globally.")

        try:
            all_agents = api.list_agents()
        except Exception as e:
            st.error(f"Could not load agents from backend: {e}")
            all_agents = []

        if not all_agents:
            st.warning("No agents found in configuration.")
        else:
            agent_types = sorted({a["type"] for a in all_agents})

            for agent_type in agent_types:
                with st.expander(f"📁 {agent_type.upper()}", expanded=True):
                    agents_of_type = [a for a in all_agents if a["type"] == agent_type]

                    for agent in agents_of_type:
                        col1, col2 = st.columns([4, 1])

                        with col1:
                            status_emoji = "✅" if agent["enabled"] else "⚪"
                            st.markdown(f"**{status_emoji} {agent['name']}**")
                            st.caption(
                                f"Model: `{agent['model']}` | Provider: `{agent['provider']}`"
                            )

                        with col2:
                            current_enabled = agent["enabled"]
                            new_enabled = st.toggle(
                                "Enabled",
                                value=current_enabled,
                                key=f"agent_toggle_{agent['name']}",
                            )

                            if new_enabled != current_enabled:
                                if new_enabled:
                                    api.enable_agent(agent["name"])
                                else:
                                    api.disable_agent(agent["name"])
                                st.rerun()

    # ==========================================
    # Tab 2: System Configuration
    # ==========================================
    with tabs[1]:
        st.header("System Configuration")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Daemon Settings")

            # Fetch live config from daemon process via HTTP
            current_config = daemon.get_config()
            daemon_reachable = bool(current_config)

            if not daemon_reachable:
                st.warning("Daemon is not running. Start it to edit configuration.")

            tick_interval = st.number_input(
                "Tick Interval (seconds)",
                min_value=0.1,
                max_value=300.0,
                value=float(current_config.get("tick_interval_sec", 1.0)),
                step=0.1,
                disabled=not daemon_reachable,
                help="How often the daemon runs its tick loop",
            )

            shutdown_timeout = st.number_input(
                "Shutdown Timeout (seconds)",
                min_value=1,
                max_value=60,
                value=int(current_config.get("shutdown_timeout_sec", 5)),
                step=1,
                disabled=not daemon_reachable,
                help="How long to wait for daemon to shut down gracefully",
            )

            daemon_name = st.text_input(
                "Daemon Name",
                value=current_config.get("name", "sample-daemon"),
                disabled=not daemon_reachable,
                help="Identifier for this daemon instance",
            )

            if daemon_reachable and st.button("Apply Config", use_container_width=True):
                result = daemon.patch_config(
                    tick_interval_sec=tick_interval,
                    shutdown_timeout_sec=float(shutdown_timeout),
                    name=daemon_name,
                )
                if "error" in result:
                    st.error(f"Failed to apply: {result['error']}")
                else:
                    st.success("Configuration updated")
                    st.rerun()

        with col2:
            st.subheader("Daemon Status")

            status = daemon.status()

            status_col1, status_col2 = st.columns(2)
            with status_col1:
                if status.get("running"):
                    st.success("🟢 Running")
                else:
                    st.info("⚪ Stopped")
            with status_col2:
                st.metric("Ticks", status.get("tick_count", "—"))

            col_start, col_stop = st.columns(2)
            with col_start:
                if st.button("▶️ Start Daemon", use_container_width=True):
                    result = daemon.start()
                    if result.get("started"):
                        st.success(f"Daemon started (PID {result.get('pid')})")
                    else:
                        st.warning(result.get("message", "Already running"))
                    st.rerun()

            with col_stop:
                if st.button("⏹️ Stop Daemon", use_container_width=True):
                    result = daemon.stop()
                    if result.get("stopped"):
                        st.success("Daemon stopped")
                    else:
                        st.warning(result.get("message", "Not running"))
                    st.rerun()

            st.divider()

            if status.get("last_results"):
                st.subheader("Last Execution Results")
                for result in status["last_results"]:
                    with st.expander(f"Agent: {result['agent_name']}", expanded=False):
                        if result["success"]:
                            st.success("✅ Success")
                        else:
                            st.error("❌ Failed")
                        st.code(result.get("output", "No output"))

    # ==========================================
    # Tab 3: Database Settings
    # ==========================================
    with tabs[2]:
        st.header("Database Settings")
        st.info("Configure database connections for memory and state management.")

        db_type = st.selectbox(
            "Database Type",
            options=["SQLite (Default)", "PostgreSQL", "MySQL"],
            help="Choose your database backend"
        )

        if db_type == "SQLite (Default)":
            db_path = st.text_input(
                "Database Path",
                value="./database/",
                help="Path to SQLite database directory"
            )
            st.caption("📝 SQLite is suitable for single-user deployments")

        elif db_type == "PostgreSQL":
            col1, col2 = st.columns(2)
            with col1:
                pg_host = st.text_input("Host", value="localhost")
                pg_user = st.text_input("User", value="postgres")
            with col2:
                pg_port = st.number_input("Port", value=5432, min_value=1, max_value=65535)
                pg_password = st.text_input("Password", type="password")

            pg_database = st.text_input("Database", value="gabriel")

            if st.button("Test Connection", use_container_width=True):
                st.info("Connection test not yet implemented")

        elif db_type == "MySQL":
            col1, col2 = st.columns(2)
            with col1:
                mysql_host = st.text_input("Host", value="localhost")
                mysql_user = st.text_input("User", value="root")
            with col2:
                mysql_port = st.number_input("Port", value=3306, min_value=1, max_value=65535)
                mysql_password = st.text_input("Password", type="password")

            mysql_database = st.text_input("Database", value="gabriel")

            if st.button("Test Connection", use_container_width=True):
                st.info("Connection test not yet implemented")

    # ==========================================
    # Tab 4: Preferences
    # ==========================================
    with tabs[3]:
        st.header("User Preferences")

        st.subheader("Display Preferences")
        theme = st.selectbox(
            "Theme",
            options=["Auto", "Light", "Dark"],
            help="Choose the application theme"
        )

        st.subheader("Default Values")

        col1, col2 = st.columns(2)

        with col1:
            default_provider = st.selectbox(
                "Default Provider",
                options=["ollama", "openai", "anthropic", "local"],
                help="Default provider for new agents"
            )

        with col2:
            default_model = st.text_input(
                "Default Model",
                value="gpt-4",
                help="Default model for new agents"
            )

        st.subheader("Notification Settings")
        col1, col2 = st.columns(2)

        with col1:
            st.checkbox(
                "Show agent execution notifications",
                value=True,
                help="Display notifications when agents execute"
            )

        with col2:
            st.checkbox(
                "Show error alerts",
                value=True,
                help="Alert on errors and warnings"
            )

        st.divider()

        st.subheader("Advanced")

        if st.checkbox("Enable debug logging"):
            st.caption("Debug logs will be more verbose")

        if st.checkbox("Export settings"):
            st.info("Export functionality coming soon")


if __name__ == "__main__":
    settings_ui()