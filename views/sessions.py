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
    status = "🟢 Active" if is_active else "⚪ Open"

    with st.container():
        cols = st.columns([6, 3, 1])
        with cols[0]:
            if st.button(label, key=f"session_select_{session_id}", use_container_width=True, on_click=lambda sid=session_id: st.session_state.__setitem__("active_session_id", sid)):
                pass
            st.caption(f"Agent: {session.agent_name or '—'} • Messages: {len(session.messages)}")
        with cols[1]:
            st.markdown(f"**{status}**")
            st.caption(session.created_at)
        with cols[2]:
            if st.button("✕", key=f"session_delete_{session_id}", on_click=lambda sid=session_id: SessionManager.delete_session(sid)):
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
    active_id = st.session_state.active_session_id
    active_title = st.session_state.sessions.get(active_id).title if active_id in st.session_state.sessions else "—"

    left, right = st.columns([3, 1])

    with right:
        st.metric("Total sessions", total_sessions)

    with left:
        if total_sessions == 0:
            st.info("No saved sessions found. Create a new chat to get started.")
        else:
            for session_id, session in st.session_state.sessions.items():
                _render_session_card(session_id, session)
                st.divider()

    st.markdown("### Enabled Agents")
    enabled_agents = None
    try:
        enabled_agents = st.session_state.config_manager.get_enabled_agents()
    except Exception:
        enabled_agents = []

    if enabled_agents:
        names = [f"{agent.name} ({agent.type})" for agent in enabled_agents]
        selected_name = st.selectbox("Choose agent", options=names, index=0)
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
