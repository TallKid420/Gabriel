import streamlit as st
import logging
from executor.toolhandler import load_tool_registry
from daemon.database import Database

log = logging.getLogger(__name__)


@st.cache_resource
def get_database():
    """Cache the database connection across page loads."""
    return Database()


def render_tools_page():
    st.title("🛠️ Tool Management")
    st.info("Enable or disable tools globally. Enabled tools are available to all agents.")

    db = get_database()

    # 1. Discover all tools physically in the repository
    # Load with None for enabled_ids initially so we see EVERYTHING available
    registry = load_tool_registry(enabled_ids=None)
    all_tools = registry.list_tools()

    if not all_tools:
        st.warning("No tools discovered in 'executor/tools/'. Check your tool decorators.")
        return

    # 2. Sync with Database
    # Ensure any newly added code-files have a row in the DB (defaulting to disabled)
    db.sync_tool_registry([t.id for t in all_tools])

    # 3. Get the current truth from Database
    tool_states = db.get_tool_states()

    # 4. Add search bar
    search_query = st.text_input("🔍 Search tools", placeholder="Search by name or description...").lower()

    # 5. Filter tools based on search query
    filtered_tools = all_tools
    if search_query:
        filtered_tools = [
            t for t in all_tools
            if search_query in t.display_name.lower()
            or search_query in t.id.lower()
            or search_query in t.description.lower()
        ]

    # 6. Group tools by category for a cleaner UI
    categories = sorted(list(set(t.category for t in filtered_tools)))

    if not filtered_tools:
        st.warning(f"No tools found matching '{search_query}'")
        return

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
                    # Use tool.id as the key for streamlit to prevent state collisions
                    new_val = st.toggle(
                        "Enabled",
                        value=current_val,
                        key=f"toggle_{tool.id}"
                    )

                    if new_val != current_val:
                        db.set_tool_enabled(tool_id=tool.id, enabled=new_val)
                        st.rerun()

if __name__ == "__main__":
    render_tools_page()