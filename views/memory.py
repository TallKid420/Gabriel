import streamlit as st


def memory_ui():
    st.title("Memory")

    st.markdown(
        """
        This page lets you define resources for your agent to ingest later.
        Add URLs or upload documents here.
        """
    )

    st.divider()

    with st.form(key="memory_resource_form"):
        st.subheader("Add links or documents")

        st.markdown(
            "Provide one or more URLs for the agent to crawl and/or upload files that should be added to the knowledge database."
        )

        urls = st.text_area(
            label="Resource URLs",
            placeholder="https://example.com/article\nhttps://docs.example.com/spec.pdf",
            help="Enter one URL per line.",
            height=120,
        )

        uploaded_files = st.file_uploader(
            label="Upload documents",
            type=["txt", "md", "pdf", "docx"],
            accept_multiple_files=True,
            help="Upload documents for future ingestion into the memory database.",
        )

        notes = st.text_area(
            label="Notes / metadata",
            placeholder="Optional context for these resources...",
            height=80,
        )

        submit_button = st.form_submit_button("Save resource list")

        if submit_button:
            st.success("Resources saved to the UI form. Backend ingestion is not wired yet.")
            if urls:
                st.markdown("**URLs to ingest:**")
                for url in [u.strip() for u in urls.splitlines() if u.strip()]:
                    st.write(f"- {url}")
            if uploaded_files:
                st.markdown("**Uploaded documents:**")
                for uploaded_file in uploaded_files:
                    st.write(f"- {uploaded_file.name} ({uploaded_file.type or 'unknown type'})")
            if notes:
                st.markdown("**Notes:**")
                st.write(notes)

    st.divider()

    st.subheader("Current resource queue")
    st.info(
        "This section is a layout placeholder. Once ingestion is wired, your agent will crawl the links and embed uploaded documents here."
    )
    st.write("- No resources queued yet.")


if __name__ == "__main__":
    memory_ui()
