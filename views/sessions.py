"""Sessions page — presentation only.

Session CRUD is delegated to the backend via the API client. ``active_session_id``
remains in Streamlit session state because it is genuine UI selection state.
"""

import streamlit as st
from typing import Optional

from app import get_api


class SessionManager:
    """Thin façade over the backend session API (kept for call-site compat)."""

    @staticmethod
    def create_session(agent_name: Optional[str] = None) -> None:
        api = get_api()
        created = api.create_session(agent_name=agent_name)
        st.session_state.active_session_id = created["id"]

    @staticmethod
    def delete_session(session_id: str) -> None:
        api = get_api()
        api.delete_session(session_id)
        remaining = api.list_sessions()
        if not remaining:
            SessionManager.create_session()
            return
        if st.session_state.get("active_session_id") == session_id:
            st.session_state.active_session_id = remaining[0]["id"]


def _render_session_card(session: dict) -> None:
    label = session.get("title") or "New chat"
    is_active = session["id"] == st.session_state.get("active_session_id")
    status = "🟢" if is_active else "⚪"

    with st.container(border=True):
        col1, col2 = st.columns([1, 8])
        with col1:
            st.markdown(
                f"<div style='text-align: center; font-size: 1.2em;'>{status}</div>",
                unsafe_allow_html=True,
            )
        with col2:
            if st.button(
                label,
                key=f"session_select_{session['id']}",
                use_container_width=True,
                on_click=lambda sid=session["id"]: st.session_state.__setitem__(
                    "active_session_id", sid
                ),
            ):
                pass
            st.caption(
                f"**Messages:** {session.get('message_count', 0)} • "
                f"**Created:** {session.get('created_at', '')}"
            )

        col_del = st.columns([11, 1])
        with col_del[1]:
            if st.button(
                "✕",
                key=f"session_delete_{session['id']}",
                on_click=lambda sid=session["id"]: SessionManager.delete_session(sid),
                help="Delete session",
            ):
                pass


def session_ui() -> None:
    api = get_api()
    st.title("Sessions")
    st.write("Browse, open, and manage your saved chats.")

    try:
        sessions = api.list_sessions()
    except Exception as e:
        st.error(f"Could not load sessions from backend: {e}")
        return

    st.metric("Total sessions", len(sessions))

    if not sessions:
        st.info("No saved sessions found. Create a new chat to get started.")
    else:
        sessions_by_agent: dict[str, list[dict]] = {}
        for session in sessions:
            agent = session.get("agent_name") or "No Agent"
            sessions_by_agent.setdefault(agent, []).append(session)

        for agent in sorted(sessions_by_agent.keys()):
            with st.expander(f"🤖 {agent}", expanded=True):
                cols = st.columns(2)
                for idx, session in enumerate(sessions_by_agent[agent]):
                    with cols[idx % 2]:
                        _render_session_card(session)

    st.divider()
    st.subheader("Start New Chat")
    try:
        enabled_agents = api.list_agents(enabled_only=True)
    except Exception:
        enabled_agents = []

    if enabled_agents:
        names = [f"{a['name']} ({a['type']})" for a in enabled_agents]
        selected_name = st.selectbox(
            "Choose agent", options=names, index=0, label_visibility="collapsed"
        )
        selected_agent = enabled_agents[names.index(selected_name)]
        st.button(
            "Chat with selected agent",
            use_container_width=True,
            on_click=lambda name=selected_agent["name"]: (
                st.session_state.__setitem__("last_manual_agent_name", name),
                SessionManager.create_session(name),
            ),
            key=f"chat_with_{selected_agent['name']}",
        )
    else:
        st.info("No enabled agents in config/agents.yaml")


if __name__ == "__main__":
    session_ui()
