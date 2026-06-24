"""Tools page — presentation only.

Tool discovery and per-agent enablement go through the backend Tools API; this
view no longer imports ``load_tool_registry`` or ``Database``.
"""

import logging

import streamlit as st

from app import get_api

log = logging.getLogger(__name__)


def render_tools_page():
    api = get_api()
    st.title("🛠️ Tool Management")
    st.info(
        "Enable or disable tools **per agent**. Each agent has its own "
        "independent set of permissions stored in the backend = toggling a "
        "tool for one agent never affects another."
    )

    try:
        all_tools = api.list_tools()
    except Exception as e:
        st.error(f"Could not load tools from backend: {e}")
        return

    if not all_tools:
        st.warning("No tools discovered. Check your tool decorators in 'executor/tools/'.")
        return

    try:
        agents = api.list_tool_agents()
    except Exception as e:
        st.error(f"Could not load agents from backend: {e}")
        return

    if not agents:
        st.warning(
            "No agents found. Create an agent on the **Agents** page first, "
            "then return here to manage its tools."
        )
        return

    name_to_id = {a["name"]: a["agent_id"] for a in agents}
    selected_name = st.selectbox(
        "Select an agent", options=list(name_to_id.keys()), key="tool_mgmt_selected_agent"
    )
    selected_agent_id = name_to_id[selected_name]

    st.markdown(f"### Managing tools for: '{selected_name}'")
    st.caption(f"Agent ID: '{selected_agent_id}'")
    st.divider()

    tool_states = api.get_agent_tool_states(selected_agent_id)
    enabled_count = sum(1 for v in tool_states.values() if v)
    st.caption(f"{enabled_count} of {len(all_tools)} tools are enabled for **{selected_name}**")

    search_query = st.text_input(
        "🔍 Search tools", placeholder="Search by name or description..."
    ).lower()

    filtered_tools = all_tools
    if search_query:
        filtered_tools = [
            t
            for t in all_tools
            if search_query in t["display_name"].lower()
            or search_query in t["id"].lower()
            or search_query in t["description"].lower()
        ]

    if not filtered_tools:
        st.warning(f"No tools found matching '{search_query}'")
        return

    categories = sorted({t["category"] for t in filtered_tools})
    for cat in categories:
        with st.expander(f"📁 {cat.upper()}", expanded=True):
            cat_tools = [t for t in filtered_tools if t["category"] == cat]
            for tool in cat_tools:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**{tool['display_name']}** (`{tool['id']}`)")
                    st.caption(tool["description"])
                with col2:
                    current_val = tool_states.get(tool["id"], False)
                    new_val = st.toggle(
                        "Enabled",
                        value=current_val,
                        key=f"toggle_{selected_agent_id}_{tool['id']}",
                    )
                    if new_val != current_val:
                        api.toggle_tool(selected_agent_id, tool["id"], new_val)
                        st.rerun()


if __name__ == "__main__":
    render_tools_page()
