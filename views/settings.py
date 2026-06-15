import streamlit as st
from daemon.database import Database
import logging

log = logging.getLogger(__name__)


@st.cache_resource
def get_database():
    """Cache the database connection across page loads."""
    return Database()


def settings_ui():
    st.title("⚙️ Settings")

    config_manager = st.session_state.config_manager
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

        all_agents = config_manager.system_agents + config_manager.custom_agents

        if not all_agents:
            st.warning("No agents found in configuration.")
        else:
            # Group by type
            agent_types = sorted(list(set(agent.type for agent in all_agents)))

            for agent_type in agent_types:
                with st.expander(f"📁 {agent_type.upper()}", expanded=True):
                    agents_of_type = [a for a in all_agents if a.type == agent_type]

                    for agent in agents_of_type:
                        col1, col2 = st.columns([4, 1])

                        with col1:
                            status_emoji = "✅" if agent.enabled else "⚪"
                            st.markdown(f"**{status_emoji} {agent.name}**")
                            st.caption(f"Model: `{agent.model}` | Provider: `{agent.provider}`")

                        with col2:
                            current_enabled = agent.enabled
                            new_enabled = st.toggle(
                                "Enabled",
                                value=current_enabled,
                                key=f"agent_toggle_{agent.name}"
                            )

                            if new_enabled != current_enabled:
                                if new_enabled:
                                    config_manager.enable_agent(agent.name)
                                else:
                                    config_manager.disable_agent(agent.name)
                                st.rerun()

    # ==========================================
    # Tab 2: System Configuration
    # ==========================================
    with tabs[1]:
        st.header("System Configuration")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Daemon Settings")

            # Tick interval
            tick_interval = st.number_input(
                "Tick Interval (seconds)",
                min_value=0.1,
                max_value=300.0,
                value=daemon.config.tick_interval_sec,
                step=0.1,
                help="How often the daemon runs its tick loop"
            )

            if tick_interval != daemon.config.tick_interval_sec:
                daemon.config.tick_interval_sec = tick_interval
                st.success("Tick interval updated")

            # Shutdown timeout
            shutdown_timeout = st.number_input(
                "Shutdown Timeout (seconds)",
                min_value=1,
                max_value=60,
                value=int(daemon.config.shutdown_timeout_sec),
                step=1,
                help="How long to wait for daemon to shut down gracefully"
            )

            if shutdown_timeout != daemon.config.shutdown_timeout_sec:
                daemon.config.shutdown_timeout_sec = float(shutdown_timeout)
                st.success("Shutdown timeout updated")

            # Daemon name
            daemon_name = st.text_input(
                "Daemon Name",
                value=daemon.config.name,
                help="Identifier for this daemon instance"
            )

            if daemon_name != daemon.config.name:
                daemon.config.name = daemon_name
                st.success("Daemon name updated")

        with col2:
            st.subheader("Daemon Status")

            # Display daemon status
            status = daemon.status()

            status_col1, status_col2 = st.columns(2)
            with status_col1:
                if status["running"]:
                    st.success("🟢 Running")
                else:
                    st.info("⚪ Stopped")

            with status_col2:
                tick_count = status["tick_count"]
                st.metric("Ticks", tick_count)

            # Control buttons
            col_start, col_stop = st.columns(2)
            with col_start:
                if st.button("▶️ Start Daemon", use_container_width=True):
                    if daemon.start():
                        st.success("Daemon started")
                        st.rerun()
                    else:
                        st.warning("Daemon already running")

            with col_stop:
                if st.button("⏹️ Stop Daemon", use_container_width=True):
                    if daemon.stop():
                        st.success("Daemon stopped")
                        st.rerun()
                    else:
                        st.warning("Daemon not running")

            st.divider()

            # Show last execution results
            if status["last_results"]:
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