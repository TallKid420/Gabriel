import streamlit as st
from typing import Any

from agents.base_agent import BaseAgent

DEFAULT_ENDPOINT = "http://localhost:11434"
CREATABLE_AGENT_TYPES = ["chat", "engineer", "researcher", "server"]
DEFAULT_PROVIDERS = ["ollama", "openai", "anthropic", "local"]


def _card_html(agent: BaseAgent) -> str:
    system_prompt = agent.system_prompt or "—"
    endpoint = agent.endpoint or "—"
    enabled = "✅ Enabled" if agent.enabled else "⚪ Disabled"

    return f"""
<div style='border:2px solid rgba(200, 200, 200, 0.5); border-radius:12px; padding:16px; background:var(--background-secondary); box-shadow:0 1px 3px var(--shadow-color); height:100%; display:flex; flex-direction:column;'>
  <div style='display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:12px;'>
    <div style='flex:1; min-width:0;'>
      <div style='font-size:1.1rem; font-weight:700; margin-bottom:4px; word-break:break-word;'>{agent.name}</div>
      <div style='font-size:0.85rem; color:var(--text-secondary); margin-bottom:4px;'>Type: <strong>{agent.type}</strong></div>
    </div>
    <div style='font-size:0.85rem; color:#0f9d58; font-weight:700; white-space:nowrap;'>{enabled}</div>
  </div>
  <div style='font-size:0.8rem; flex:1;'>
    <div style='margin-bottom:3px;'>Model: <code style='background:var(--background-tertiary); padding:2px 4px; border-radius:4px; color:var(--text-primary);'>{agent.model}</code></div>
  </div>
</div>
"""


def _get_provider_options(agents: list[BaseAgent]) -> list[str]:
    providers = {agent.provider for agent in agents if agent.provider}
    providers.update(DEFAULT_PROVIDERS)
    return sorted(providers)


def _ensure_state_flags() -> None:
    if "agent_to_edit" not in st.session_state:
        st.session_state.agent_to_edit = None
    if "show_create_agent_modal" not in st.session_state:
        st.session_state.show_create_agent_modal = False


def _show_edit_modal(agent: BaseAgent) -> None:
    st.markdown(f"### ✏️ Edit agent: {agent.name}")
    with st.form(f"edit_agent_form_{agent.name}"):
        new_name = st.text_input("Name", value=agent.name)
        endpoint = st.text_input("Endpoint", value=agent.endpoint or "")
        model = st.text_input("Model", value=agent.model)
        system_prompt = st.text_area("System prompt", value=agent.system_prompt or "", height=140)

        with st.expander("Advanced settings"):
            timeout_seconds = st.number_input(
                "Timeout seconds",
                min_value=1,
                max_value=600,
                value=agent.timeout_seconds or 20,
                step=1,
            )
            temperature = st.number_input(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                value=float(agent.temperature or 0.0),
                step=0.01,
                format="%.2f",
            )
            max_tokens = st.number_input(
                "Max tokens",
                min_value=1,
                value=agent.max_tokens or 1024,
                step=1,
            )

        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("💾 Save changes", use_container_width=True)
        with col2:
            if st.form_submit_button("❌ Cancel", use_container_width=True):
                st.session_state.agent_to_edit = None
                st.rerun()

        if submitted:
            config_manager = st.session_state.config_manager
            if new_name.strip() == "" or model.strip() == "":
                st.error("Name and model are required.")
            else:
                try:
                    update_data = {
                        "name": new_name.strip(),
                        "endpoint": endpoint.strip() or None,
                        "model": model.strip(),
                        "system_prompt": system_prompt.strip() or None,
                        "timeout_seconds": int(timeout_seconds),
                        "temperature": float(temperature),
                        "max_tokens": int(max_tokens),
                    }
                    if config_manager.update_agent(agent.name, update_data):
                        st.success("Agent updated successfully.")
                        st.session_state.agent_to_edit = None
                        st.rerun()
                    else:
                        st.error("Failed to update agent.")
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Error updating agent: {str(e)}")


def _show_create_modal(agent_types: list[str], provider_options: list[str]) -> None:
    st.markdown("### ➕ Create new agent")
    with st.form("create_agent_form"):
        name = st.text_input("Name")
        agent_type = st.selectbox("Type", options=agent_types, index=0)
        provider = st.selectbox("Provider", options=provider_options, index=0)
        model = st.text_input("Model")
        endpoint = st.text_input("Endpoint", value=DEFAULT_ENDPOINT)

        with st.expander("Advanced settings"):
            timeout_seconds = st.number_input(
                "Timeout seconds",
                min_value=1,
                max_value=600,
                value=20,
                step=1,
            )
            max_tokens = st.number_input(
                "Max tokens",
                min_value=1,
                value=1024,
                step=1,
            )
            temperature = st.number_input(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                value=0.0,
                step=0.01,
                format="%.2f",
            )

        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("✅ Create agent", use_container_width=True)
        with col2:
            if st.form_submit_button("❌ Cancel", use_container_width=True):
                st.session_state.show_create_agent_modal = False
                st.rerun()

        if submitted:
            if not name.strip() or not agent_type.strip() or not provider.strip() or not model.strip():
                st.error("Name, Type, Provider, and Model are required.")
            else:
                config_manager = st.session_state.config_manager
                agent_data = {
                    "name": name.strip(),
                    "type": agent_type.strip(),
                    "provider": provider.strip(),
                    "model": model.strip(),
                    "endpoint": endpoint.strip() or DEFAULT_ENDPOINT,
                    "timeout_seconds": int(timeout_seconds),
                    "temperature": float(temperature),
                    "max_tokens": int(max_tokens),
                    "enabled": True,
                }
                try:
                    config_manager.add_agent(agent_data)
                    st.success("Agent created successfully.")
                    st.session_state.show_create_agent_modal = False
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def agents_ui() -> None:
    st.title("Agents")
    st.write("View, edit, and create agents from the current configuration.")

    _ensure_state_flags()

    config_manager = st.session_state.config_manager
    agent_list = config_manager.system_agents + config_manager.custom_agents
    provider_options = _get_provider_options(agent_list)

    # Check if editing or creating
    selected_edit_agent = st.session_state.agent_to_edit
    if selected_edit_agent:
        target = config_manager.get_agent(selected_edit_agent)
        if target:
            st.divider()
            _show_edit_modal(target)
            if st.button("← Back to agents"):
                st.session_state.agent_to_edit = None
                st.rerun()
        else:
            st.error(f"Unable to find agent '{selected_edit_agent}' to edit.")
        return

    if st.session_state.show_create_agent_modal:
        st.divider()
        _show_create_modal(CREATABLE_AGENT_TYPES, provider_options)
        if st.button("← Back to agents"):
            st.session_state.show_create_agent_modal = False
            st.rerun()
        return

    # Header with create button
    top_cols = st.columns([1, 0.15], gap="small")
    with top_cols[0]:
        st.markdown("#### Agent catalog")
    with top_cols[1]:
        if st.button("➕ New", use_container_width=True):
            st.session_state.show_create_agent_modal = True
            st.rerun()

    if not agent_list:
        st.info("No agents found in config/agents.yaml.")
        return

    # Grid layout with consistent sizing
    cols_per_row = 3
    for idx in range(0, len(agent_list), cols_per_row):
        row_agents = agent_list[idx : idx + cols_per_row]
        cols = st.columns(3, gap="small")  # Always 3 columns for consistent sizing

        for col, agent in zip(cols, row_agents):
            with col:
                st.markdown(_card_html(agent), unsafe_allow_html=True)
                if st.button("✏️ Edit", key=f"edit_{agent.name}", use_container_width=True):
                    st.session_state.agent_to_edit = agent.name
                    st.rerun()

if __name__ == "__main__":
    agents_ui()
