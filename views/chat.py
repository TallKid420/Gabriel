"""Chat page — presentation only.

This view no longer imports agents, executors or the session store. It renders
chat history fetched from the backend and streams replies from the API's SSE
endpoint, rendering the *normalized* event contract produced by ``AgentService``.
"""

import json

import streamlit as st

from app import get_api
from views.sessions import SessionManager


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


def render_event_stream(stream) -> str:
    """Render the normalized event stream coming from the backend API."""
    tools_container = st.container()
    text_container = st.empty()
    rendered_text = ""
    tool_expanders: dict[str, object] = {}

    for event in stream:
        try:
            etype = event.get("type")
            if etype == "token":
                rendered_text += event.get("content", "")
                text_container.markdown(rendered_text)
            elif etype == "tool_start":
                name = event.get("name", "unknown")
                with tools_container:
                    expander = st.expander(f"Tool: {name}", expanded=True)
                    expander.write(f"**Input:**\n```json\n{event.get('input', {})}\n```")
                tool_expanders[name] = expander
            elif etype == "tool_output":
                expander = tool_expanders.get(event.get("name", "unknown"))
                if expander:
                    expander.write(
                        f"**Intermediate output:**\n```text\n{event.get('content', '')}\n```"
                    )
            elif etype == "tool_end":
                expander = tool_expanders.get(event.get("name", "unknown"))
                if expander:
                    expander.write(f"**Output:**\n```text\n{event.get('output', '')}\n```")
            elif etype == "error":
                st.error(event.get("message", "Unknown error"))
            elif etype == "done":
                if event.get("content"):
                    rendered_text = event["content"]
                    text_container.markdown(rendered_text)
        except Exception as e:  # defensive: never let one event crash the page
            st.error(f"Error rendering event: {e}")
            continue

    return rendered_text


def chat_ui() -> None:
    api = get_api()
    session_id = st.session_state.get("active_session_id")
    if not session_id:
        st.info("No active session. Create one from the Sessions page.")
        return

    try:
        session = api.get_session(session_id)
    except Exception as e:
        st.error(f"Could not load session from backend: {e}")
        return

    agent_name = session.get("agent_name")
    agent_info = f" · Agent: {agent_name}" if agent_name else ""
    left, right = st.columns([10, 1])

    with left:
        st.markdown(
            f"""
            <div style="display:flex; align-items:center; justify-content:flex-start; gap:1rem; padding:0.75rem 0.5rem; border-bottom:1px solid rgba(255,255,255,0.12); margin-bottom:1rem;">
                <div style="font-size:1.5rem; font-weight:700; margin:0;">Chat</div>
                <div style="font-size:1rem; color:#5f6368; margin:0;">Session: {session.get('title', '')}{agent_info}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        if st.button("+", key="new_chat_button", help="New Chat", use_container_width=True):
            SessionManager.create_session()
            st.rerun()
        if st.button("Clear", key="clear_chat_button", help="Clear Chat", use_container_width=True):
            api.clear_session(session_id)
            st.rerun()

    for msg in session.get("messages", []):
        with st.chat_message(msg["role"]):
            st.markdown(format_response(msg["content"]))

    prompt = st.chat_input(placeholder="Message", accept_file=False, accept_audio=False)
    if not prompt:
        return

    # Resolve the agent for this turn from the backend's enabled agents.
    selected_agent_name = agent_name or st.session_state.get("last_manual_agent_name")
    if not selected_agent_name:
        try:
            enabled = api.list_agents(enabled_only=True)
        except Exception:
            enabled = []
        if not enabled:
            st.error("No enabled agents available for chat")
            return
        chat_agents = [a for a in enabled if a["type"] == "chat"]
        selected_agent_name = (chat_agents or enabled)[0]["name"]

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                stream = api.chat_stream(session_id, prompt, selected_agent_name)
                render_event_stream(stream)
            except Exception as e:
                st.error(f"Backend chat error: {e}")
                return

    # The backend persists both the user and assistant messages, so just rerun
    # to show the canonical history.
    st.rerun()


if __name__ == "__main__":
    chat_ui()
