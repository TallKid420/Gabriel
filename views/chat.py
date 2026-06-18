from app import ChatSession, save_sessions
from views.sessions import SessionManager

import json
import streamlit as st


def format_response(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return "_No content returned._"
    if text.startswith("{") or text.startswith("["):
        try:
            parsed = json.loads(text)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
            return f"json\n{pretty}\n"
        except Exception:
            return text
    return text


def render_streamed_reply(stream) -> str:

    tools_container = st.container()
    text_container = st.empty()
    
    rendered_text = ""

    tool_expanders = {}

    for chunk in stream:
        try:
            match chunk["type"]:
                case "messages":
                    token, metadata = chunk["data"]
                    text = ""  # ← initialize FIRST
                    if isinstance(token.content, str):
                        text = token.content
                    elif isinstance(token.content, list) and token.content:
                        text = token.content[0].get("text", "")
                    if text:
                        rendered_text += text
                        text_container.markdown(rendered_text)

                case "tool_start":
                    tool_name = chunk["name"]

                    with tools_container:
                        expander = st.expander(f"Tool: {tool_name}", expanded=True)
                        expander.write(f"**Input:**\n```json\n{chunk['input']}\n```")
                    tool_expanders[tool_name] = expander

                case "tool_output":
                    tool_name = chunk["name"]
                    expander = tool_expanders.get(tool_name)
                    if expander:
                        expander.write(
                            f"**Intermediate output:**\n```text\n{chunk['content']}\n```"
                        )

                case "tool_end":
                    tool_name = chunk["name"]

                    expander = tool_expanders.get(tool_name)

                    if expander:
                        output = getattr(
                            chunk["output"],
                            "content",
                            str(chunk["output"])
                        )

                        expander.write(
                            f"**Output:**\n```text\n{output}\n```"
                        )
        except Exception as e:
            st.error(f"Error rendering chunk: {e}")
            continue

    return rendered_text


def maybe_update_title(session: ChatSession) -> None:
    if session.title == "New chat":
        user_messages = [m["content"] for m in session.messages if m["role"] == "user"]
        if user_messages:
            session.title = user_messages[0][:48] or "New chat"

def current_session() -> ChatSession:
    return st.session_state.sessions[st.session_state.active_session_id]

def clear_active_session() -> None:
    session = current_session()
    session.messages = []

def chat_ui() -> None:
    session = current_session()

    agent_info = f" · Agent: {session.agent_name}" if session.agent_name else ""
    left, right = st.columns([10, 1])

    with left:
        st.markdown(
            f"""
            <div style="display:flex; align-items:center; justify-content:flex-start; gap:1rem; padding:0.75rem 0.5rem; border-bottom:1px solid rgba(255,255,255,0.12); margin-bottom:1rem;">
                <div style="font-size:1.5rem; font-weight:700; margin:0;">Chat</div>
                <div style="font-size:1rem; color:#5f6368; margin:0;">Session: {session.title}{agent_info}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        if st.button(
            "+",
            key="new_chat_button",
            help="New Chat (Ctrl + N)",
            use_container_width=True,
        ):
            SessionManager.create_session()
            st.experimental_rerun()

        if st.button(
            "Clear",
            key="clear_chat_button",
            help="Clear Chat",
            use_container_width=True,
        ):
            clear_active_session()

    for msg in session.messages:
        with st.chat_message(msg["role"]):
            st.markdown(format_response(msg["content"]))

    prompt = st.chat_input(
        placeholder="Message",
        accept_file=False,
        accept_audio=False,
    )
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
    save_sessions(st.session_state.sessions)

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            stream = st.session_state.agent_executor.execute_stream(
                agent=selected_agent,
                messages=session.messages,
                thread_id=session.id,
            )
            reply = render_streamed_reply(stream)

    session.messages.append({"role": "assistant", "content": reply})
    save_sessions(st.session_state.sessions)


if __name__ == "__main__":
    chat_ui()