"""Memory page — presentation only.

Reads and mutations go through the backend Memory API; this view no longer
instantiates ``VectorDatabase`` or touches the Chroma collection directly.
"""

import logging

import streamlit as st

from app import get_api
from io import BytesIO

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
        st.subheader("Add Resources")

        resource_type = st.selectbox(
            "Resource Type",
            [
                "Resource URLs",
                "Upload documents",
                "Notes / metadata",
            ],
        )

        st.divider()

        with st.form(key="memory_resource_form"):

            urls = None
            uploaded_files = None
            notes = None

            if resource_type == "Resource URLs":
                st.markdown(
                    "Provide one or more URLs for the agent to crawl."
                )

                urls = st.text_area(
                    label="Resource URLs",
                    placeholder=(
                        "https://example.com/article\n"
                        "https://docs.example.com/spec.pdf"
                    ),
                    help="Enter one URL per line.",
                    height=120,
                )

            elif resource_type == "Upload documents":
                st.markdown(
                    "Upload documents that should be added to the knowledge database."
                )

                uploaded_files = st.file_uploader(
                    label="Upload documents",
                    type=["txt", "md", "pdf", "docx"],
                    accept_multiple_files=True,
                )

            elif resource_type == "Notes / metadata":
                st.markdown(
                    "Add additional information or metadata for the resource."
                )

                notes = st.text_area(
                    label="Notes / metadata",
                    height=120,
                )

            submit_button = st.form_submit_button("Save resource")

            if submit_button:
                try:
                    responses = []

                    if urls:
                        for url in [u.strip() for u in urls.splitlines() if u.strip()]:
                            responses.append(api.ingest_url(url=url))

                    elif uploaded_files:
                        for uploaded_file in uploaded_files:
                            responses.append(api.ingest_file(file=uploaded_file))

                    elif notes:
                        # Convert to file object.
                        data = BytesIO(notes.encode("utf-8"))
                        data.filename = "notes.md"

                        responses.append(api.ingest_file(file=data))

                    else: 
                        st.warning(
                            "No resource provided. Please enter a URL, upload a document, "
                            "or add notes before saving."
                        )
                        return
                    
                    for resp in responses:
                        st.success(resp.get("detail", "Resource ingested successfully"))
                        
                except Exception as e:
                    st.error(f"Failed to ingest resource: {e}")
                    log.exception("Memory ingestion failed")


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
