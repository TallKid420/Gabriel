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
        st.info(
            "Gabriel stores **all** state — sessions, chat history, agents, tool "
            "state, the crawler link queue, LangGraph checkpoints, and vector "
            "memory — in a single self-hosted **PostgreSQL + pgvector** database."
        )

        import os

        database_url = os.getenv(
            "DATABASE_URL", "postgresql://gabriel:gabriel@localhost:5432/gabriel"
        )
        embedding_dim = os.getenv("EMBEDDING_DIM", "1024")

        st.text_input(
            "DATABASE_URL",
            value=database_url,
            disabled=True,
            help="Connection string read from the DATABASE_URL environment variable "
            "(set it in your .env file).",
        )
        st.text_input(
            "Embedding dimensions",
            value=str(embedding_dim),
            disabled=True,
            help="Vector size for the pgvector `documents.embedding` column "
            "(EMBEDDING_DIM). Must match your embedding model — bge-m3 = 1024.",
        )

        st.caption(
            "📝 To change the backend, edit `DATABASE_URL` in your `.env` file and "
            "run the schema migration with `python -m db.migrate`. "
            "See `POSTGRES_SETUP.md` for full installation and setup instructions."
        )

        if st.button("Test Connection", use_container_width=True):
            try:
                from db import get_pool

                with get_pool().connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                        cur.fetchone()
                st.success("✅ Connected to PostgreSQL successfully")
            except Exception as exc:  # pragma: no cover - UI feedback only
                st.error(f"❌ Connection failed: {exc}")

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