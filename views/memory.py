"""Memory page — presentation only.

Reads and mutations go through the backend Memory API; this view no longer
instantiates ``VectorDatabase`` or touches the Chroma collection directly.
"""

import logging

import streamlit as st

from app import get_api

log = logging.getLogger(__name__)


def memory_ui():
    api = get_api()
    st.title("Memory")
    st.markdown(
        """
        This page lets you manage your agent's knowledge base.
        Add new resources or view what's already been stored.
        """
    )
    st.divider()

    tab1, tab2 = st.tabs(["Add Resources", "View Stored Memories"])

    with tab1:
        st.subheader("Add links or documents")
        st.markdown(
            "Provide one or more URLs for the agent to crawl and/or upload files "
            "that should be added to the knowledge database."
        )
        with st.form(key="memory_resource_form"):
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
            )
            notes = st.text_area(label="Notes / metadata", height=80)
            submit_button = st.form_submit_button("Save resource list")

            if submit_button:
                st.success(
                    "Resources captured. Backend ingestion endpoint is not wired "
                    "yet (tracked in the technical-debt list)."
                )
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

    with tab2:
        st.subheader("Stored Memories")
        try:
            data = api.list_memories()
        except Exception as e:
            st.error(f"Failed to load memories from backend: {e}")
            log.exception("Failed to load memories via API")
            return

        count = data.get("count", 0)
        grouped = data.get("grouped", {})
        if count == 0:
            st.info("No memories stored yet. Add some resources in the 'Add Resources' tab.")
            return

        st.success(f"Found {count} stored memories")
        for source, docs in grouped.items():
            with st.expander(f"📄 {source}", expanded=False):
                st.caption(f"{len(docs)} chunk(s) from this source")
                for i, doc in enumerate(docs):
                    col1, col2 = st.columns([10, 1])
                    with col1:
                        st.markdown(f"**Chunk {i + 1}**")
                        meta = doc.get("metadata", {})
                        if "title" in meta:
                            st.caption(f"Title: {meta['title']}")
                        if "crawled_at" in meta:
                            st.caption(f"Indexed: {meta['crawled_at']}")
                        preview = doc["content"][:300]
                        if len(doc["content"]) > 300:
                            preview += "..."
                        st.markdown(f"> {preview}")
                    with col2:
                        if st.button("🗑️", key=f"delete_{doc['id']}"):
                            api.delete_memories([doc["id"]])
                            st.rerun()


if __name__ == "__main__":
    memory_ui()
