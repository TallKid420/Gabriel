from app import now_iso, ChatSession, save_sessions

import streamlit as st
import uuid
from typing import Optional


class SessionManager:
    @staticmethod
    def create_session(agent_name: Optional[str] = None) -> None:
        # ensure sessions dict exists
        if "sessions" not in st.session_state:
            st.session_state.sessions = {}
        session_id = str(uuid.uuid4())
        st.session_state.sessions[session_id] = ChatSession(
            id=session_id,
            title=(f"{agent_name} chat" if agent_name else "New chat"),
            created_at=now_iso(),
            agent_name=agent_name,
            messages=[],
        )
        st.session_state.active_session_id = session_id
        save_sessions(st.session_state.sessions)

    @staticmethod
    def delete_session(session_id: str) -> None:
        if "sessions" not in st.session_state or session_id not in st.session_state.sessions:
            return
        del st.session_state.sessions[session_id]
        if not st.session_state.sessions:
            SessionManager.create_session()
            return
        if st.session_state.get("active_session_id") == session_id:
            st.session_state.active_session_id = next(iter(st.session_state.sessions.keys()))
        save_sessions(st.session_state.sessions)


def _render_session_card(session_id: str, session: ChatSession) -> None:
    label = session.title or "New chat"
    is_active = session_id == st.session_state.get("active_session_id")
    status = "🟢" if is_active else "⚪"

    with st.container(border=True):
        col1, col2 = st.columns([1, 8])
        with col1:
            st.markdown(f"<div style='text-align: center; font-size: 1.2em;'>{status}</div>", unsafe_allow_html=True)
        with col2:
            if st.button(label, key=f"session_select_{session_id}", use_container_width=True, on_click=lambda sid=session_id: st.session_state.__setitem__("active_session_id", sid)):
                pass
            st.caption(f"**Messages:** {len(session.messages)} • **Created:** {session.created_at}")

        col_del = st.columns([11, 1])
        with col_del[1]:
            if st.button("✕", key=f"session_delete_{session_id}", on_click=lambda sid=session_id: SessionManager.delete_session(sid), help="Delete session"):
                pass


def session_ui() -> None:
    # ensure session_state keys exist
    if "sessions" not in st.session_state or not st.session_state.sessions:
        st.session_state.sessions = {}
        SessionManager.create_session()
    if "active_session_id" not in st.session_state:
        st.session_state.active_session_id = next(iter(st.session_state.sessions.keys()))

    st.title("Sessions")
    st.write("Browse, open, and manage your saved chats.")

    total_sessions = len(st.session_state.sessions)
    st.metric("Total sessions", total_sessions)

    if total_sessions == 0:
        st.info("No saved sessions found. Create a new chat to get started.")
    else:
        # Group sessions by agent
        sessions_by_agent = {}
        for session_id, session in st.session_state.sessions.items():
            agent = session.agent_name or "No Agent"
            if agent not in sessions_by_agent:
                sessions_by_agent[agent] = []
            sessions_by_agent[agent].append((session_id, session))

        # Sort agent names alphabetically
        sorted_agents = sorted(sessions_by_agent.keys())

        for agent in sorted_agents:
            with st.expander(f"🤖 {agent}", expanded=True):
                cols = st.columns(2)
                for idx, (session_id, session) in enumerate(sessions_by_agent[agent]):
                    with cols[idx % 2]:
                        _render_session_card(session_id, session)

    st.divider()
    st.subheader("Start New Chat")
    enabled_agents = None
    try:
        enabled_agents = st.session_state.config_manager.get_enabled_agents()
    except Exception:
        enabled_agents = []

    if enabled_agents:
        names = [f"{agent.name} ({agent.type})" for agent in enabled_agents]
        selected_name = st.selectbox("Choose agent", options=names, index=0, label_visibility="collapsed")
        selected_agent = enabled_agents[names.index(selected_name)]
        st.button(
            "Chat with selected agent",
            use_container_width=True,
            on_click=lambda name=selected_agent.name: (st.session_state.__setitem__("last_manual_agent_name", name), SessionManager.create_session(name)),
            key=f"chat_with_{selected_agent.name}",
        )
    else:
        st.info("No enabled agents in config/agents.yaml")


if __name__ == "__main__":
    session_ui()
