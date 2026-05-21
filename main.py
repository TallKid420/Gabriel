import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import streamlit as st

from agents.executor import AgentExecutor
from config.config_manager import ConfigManager
from daemon.daemon import ServerDaemon


@dataclass
class ChatSession:
    id: str
    title: str
    created_at: str
    agent_name: str | None = None
    messages: list[dict[str, str]] = field(default_factory=list)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_response(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return "_No content returned._"
    if text.startswith("{") or text.startswith("["):
        try:
            parsed = json.loads(text)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
            return f"```json\n{pretty}\n```"
        except Exception:
            return text
    return text


def ensure_state() -> None:
    if "config_manager" not in st.session_state:
        st.session_state.config_manager = ConfigManager("config/agents.yaml")
    if "agent_executor" not in st.session_state:
        st.session_state.agent_executor = AgentExecutor()
    if "daemon" not in st.session_state:
        st.session_state.daemon = ServerDaemon()
    if "last_manual_agent_name" not in st.session_state:
        st.session_state.last_manual_agent_name = None
    if "sessions" not in st.session_state:
        session_id = str(uuid.uuid4())
        st.session_state.sessions = {
            session_id: ChatSession(
                id=session_id,
                title="New chat",
                created_at=now_iso(),
                agent_name=None,
                messages=[],
            )
        }
        st.session_state.active_session_id = session_id
    # if "model" not in st.session_state:
    #     st.session_state.model = ""
    # if "skills" not in st.session_state:
    #     st.session_state.skills = dict(DEFAULT_SKILLS)
    # if "settings" not in st.session_state:
    #     st.session_state.settings = dict(DEFAULT_SETTINGS)


def create_session(agent_name: str | None = None) -> None:
    session_id = str(uuid.uuid4())
    st.session_state.sessions[session_id] = ChatSession(
        id=session_id,
        title=(f"{agent_name} chat" if agent_name else "New chat"),
        created_at=now_iso(),
        agent_name=agent_name,
        messages=[],
    )
    st.session_state.active_session_id = session_id


def current_session() -> ChatSession:
    return st.session_state.sessions[st.session_state.active_session_id]


def maybe_update_title(session: ChatSession) -> None:
    if session.title == "New chat":
        user_messages = [m["content"] for m in session.messages if m["role"] == "user"]
        if user_messages:
            session.title = user_messages[0][:48] or "New chat"


def clear_active_session() -> None:
    session = current_session()
    session.messages = []
    session.title = "New chat"


def delete_session(session_id: str) -> None:
    if session_id not in st.session_state.sessions:
        return
    del st.session_state.sessions[session_id]
    if not st.session_state.sessions:
        create_session()
        return
    if st.session_state.active_session_id == session_id:
        st.session_state.active_session_id = next(iter(st.session_state.sessions.keys()))


def sidebar_ui() -> None:
    st.sidebar.title("Gabriel")

    session = current_session()
    total_sessions = len(st.session_state.sessions)
    total_messages = len(session.messages)

    c1, c2 = st.sidebar.columns(2)
    c1.metric("Sessions", total_sessions)
    c2.metric("Messages", total_messages)

    tab_chat, tab_system = st.sidebar.tabs(["Chat", "System"])

    with tab_chat:
        st.button("New session", on_click=create_session, use_container_width=True)
        st.button("Clear active chat", on_click=clear_active_session, use_container_width=True)
        st.subheader("Sessions")
        for session_id, existing_session in list(st.session_state.sessions.items()):
            label = existing_session.title or "New chat"
            is_active = session_id == st.session_state.active_session_id
            left, right = st.columns([5, 1])
            if left.button(
                f"{'● ' if is_active else ''}{label}",
                key=f"session_select_{session_id}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.active_session_id = session_id
                st.rerun()
            if right.button("✕", key=f"session_delete_{session_id}", use_container_width=True):
                delete_session(session_id)
                st.rerun()

    with tab_system:
        daemon_status = st.session_state.daemon.status()
        st.write(f"Running: `{daemon_status['running']}`")
        st.write(f"Ticks: `{daemon_status['tick_count']}`")

        enabled_agents = st.session_state.config_manager.get_enabled_agents()
        st.subheader("Enabled Agents")
        if enabled_agents:
            names = [f"{agent.name} ({agent.type})" for agent in enabled_agents]
            selected_name = st.selectbox("Choose agent", options=names, index=0)
            selected_agent = enabled_agents[names.index(selected_name)]
            if st.button("Chat with selected agent", use_container_width=True):
                create_session(selected_agent.name)
                st.session_state.last_manual_agent_name = selected_agent.name
                st.rerun()
        else:
            st.write("No enabled agents in config/agents.yaml")

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


def chat_ui() -> None:
    session = current_session()
    st.title("Chat")
    st.caption(f"Session: {session.title}")

    if session.agent_name:
        st.caption(f"Agent: {session.agent_name}")

    for msg in session.messages:
        with st.chat_message(msg["role"]):
            st.markdown(format_response(msg["content"]))

    prompt = st.chat_input("Message")
    if not prompt:
        return

    enabled_agents = st.session_state.config_manager.get_enabled_agents()
    selected_agent_name = session.agent_name or st.session_state.last_manual_agent_name
    selected_agent = next((a for a in enabled_agents if a.name == selected_agent_name), None)
    if selected_agent is None:
        chat_agents = [a for a in enabled_agents if a.type == "chat"]
        selected_agent = chat_agents[0] if chat_agents else (enabled_agents[0] if enabled_agents else None)
        if selected_agent is None:
            st.error("No enabled agents available for chat")
            return
        session.agent_name = selected_agent.name

    session.messages.append({"role": "user", "content": prompt})
    maybe_update_title(session)

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            stream = st.session_state.agent_executor.execute_stream(
                agent=selected_agent,
                messages=session.messages,
            )
            reply = st.write_stream(stream)

    session.messages.append({"role": "assistant", "content": str(reply)})


def main() -> None:
    st.set_page_config(page_title="Gabriel", page_icon="💬", layout="wide")
    ensure_state()
    sidebar_ui()
    chat_ui()


if __name__ == "__main__":
    main()
