import streamlit as st

def deprecated_models_ui():
    """
    Deprecated UI for the *Models* page.
    The functionality has moved elsewhere or will be removed in a future release.
    """

    # ----------------------------------------------------------------------
    # 1️⃣ Deprecation banner – makes it obvious that this page is obsolete
    # ----------------------------------------------------------------------
    st.title("🚧 Models (Deprecated) 🚧")
    st.warning(
        """
        **This page has been deprecated.**  

        - Adding, updating or configuring models is now handled in the new *Model Management* dashboard.
        - All interactive controls on this page have been disabled/removed.
        - Please refer to the updated documentation for the current workflow.
        """
    )

    # ----------------------------------------------------------------------
    # 2️⃣ (Optional) Keep a short static description for reference
    # ----------------------------------------------------------------------
    st.info(
        "The original purpose of this page was to let you manage AI models – "
        "including adding new ones, updating existing ones, and configuring settings. "
        "That functionality is now available elsewhere."
    )

    # ----------------------------------------------------------------------
    # 3️⃣ No interactive widgets are rendered here.
    # ----------------------------------------------------------------------


# --------------------------------------------------------------------------
# Keep the original implementation (commented out) for reference / future use.
# --------------------------------------------------------------------------

# def models_ui():
#     st.title("Models")
#
#     st.write(
#         "This page will allow you to manage your AI models, including adding new "
#         "models, updating existing ones, and configuring model settings."
#     )
#
# --------------------------------------------------------------------------

if __name__ == "__main__":
    deprecated_models_ui()