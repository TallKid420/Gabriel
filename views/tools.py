import streamlit as st
import logging
from executor.toolhandler import load_tool_registry
from daemon.database import Database

log = logging.getLogger(__name__)


@st.cache_resource
def get_database():
    """Cache the database connection across page loads."""
    return Database()

def _config_agents():
    config_manager = st.session_state.get("config_manager")
    if config_manager is None:
        return []
    return list(config_manager.system_agents) + list(config_manager.custom_agents)

def render_tools_page():
    st.title("🛠️ Tool Management")
    st.info(
        "Enable or disable tools **per agent**. Each agent has its own "
        "independent set of permissions stored in the database = toggling a "
        "tool for one agent never affects another."
    )

    db = get_database()

    # 1. Discover every tools physically present in the repository.
    registry = load_tool_registry()
    all_tools = registry.list_tools()

    if not all_tools:
        st.warning("No tools discovered in 'executor/tools/'. Check your tool decorators.")
        return

    # 2. Sync agent catalog
    config_agents = _config_agents()
    if config_agents:
        db.sync_agents([(agent.agent_id, agent.name) for agent in config_agents])

    # 3. Load all agents from the database for the dropdown.
    agents = db.get_agents()
    if not agents:
        st.warning(
            "No agents found. Create an agent on the **Agents** page first, "
            "then return here to manage its tools."
        )
        return
    
    # 4. Agent selector at the top of the page 
    name_to_id = {agent["name"]: agent["agent_id"] for agent in agents}
    agent_names = list(name_to_id.keys())

    selected_name = st.selectbox(
        "Select an agent",
        options=agent_names,
        key="tool_mgat_selected_agent",
    )
    selected_agent_id = name_to_id[selected_name]

    st.markdown(f"### Managing tools for: '{selected_name}'")
    st.caption(f"Agent ID: '{selected_agent_id}'")
    st.divider()

    # 5. Ensure every discovered tool has a row for this agent (disabled by default)
    db.sync_agent_tools([t.id for t in all_tools])

    # 6. Read the current per-agent truth from the database.
    tool_states = db.get_agent_tool_states(selected_agent_id)
    enabled_count = sum(1 for v in tool_states.values() if v)
    st.caption(f"{enabled_count} of {len(all_tools)} tools are enabled for **{selected_name}**")

    # 7. Search bar.
    search_query = st.text_input(
        "🔍 Search tools", 
        placeholder="Search by name or description...",
    ).lower()

    # 8. Filter tools based on search query
    filtered_tools = all_tools
    if search_query:
        filtered_tools = [
            t for t in all_tools
            if search_query in t.display_name.lower()
            or search_query in t.id.lower()
            or search_query in t.description.lower()
        ]

    if not filtered_tools:
        st.warning(f"No tools found matching '{search_query}'")
        return
    
    # 7. Group tools by category for a cleaner UI.
    categories = sorted({t.category for t in filtered_tools})

    for cat in categories:
        with st.expander(f"📁 {cat.upper()}", expanded=True):
            cat_tools = [t for t in filtered_tools if t.category == cat]

            for tool in cat_tools:
                col1, col2 = st.columns([4, 1])

                with col1:
                    st.markdown(f"**{tool.display_name}** (`{tool.id}`)")
                    st.caption(tool.description)

                with col2:
                    current_val = tool_states.get(tool.id, False)
                    new_val = st.toggle(
                        "Enabled",
                        value=current_val,
                        key=f"toggle_{selected_agent_id}_{tool.id}",
                    )

                    if new_val != current_val:
                        db.set_agent_tool_enabled(
                            agent_id=selected_agent_id,
                            tool_id=tool.id, 
                            enabled=new_val
                        )
                        st.rerun()

if __name__ == "__main__":
    render_tools_page()