import streamlit as st
import logging
from executor.toolhandler import load_tool_registry
from daemon.database import Database

log = logging.getLogger(__name__)

def render_tools_page():
    st.title("🛠️ Tool Management")
    st.info("Enable or disable tools globally. Enabled tools are available to all agents.")

    db = Database()
    
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

    # 4. Group tools by category for a cleaner UI
    categories = sorted(list(set(t.category for t in all_tools)))

    for cat in categories:
        with st.expander(f"📁 {cat.upper()}", expanded=True):
            cat_tools = [t for t in all_tools if t.category == cat]
            
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