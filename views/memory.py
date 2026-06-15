import streamlit as st
from daemon.database import VectorDatabase
import logging

log = logging.getLogger(__name__)


@st.cache_resource
def get_vector_db():
    """Cache the vector database connection across page loads."""
    return VectorDatabase(chroma_db_path="./database/")


def memory_ui():
    st.title("Memory")

    st.markdown(
        """
        This page lets you manage your agent's knowledge base.
        Add new resources or view what's already been stored.
        """
    )

    st.divider()

    # Get cached database instance
    try:
        vdb = get_vector_db()
    except Exception as e:
        st.error(f"Failed to connect to memory database: {e}")
        return

    # Tabs for adding new resources vs viewing existing ones
    tab1, tab2 = st.tabs(["Add Resources", "View Stored Memories"])

    with tab1:
        st.subheader("Add links or documents")

        st.markdown(
            "Provide one or more URLs for the agent to crawl and/or upload files that should be added to the knowledge database."
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

    with tab2:
        st.subheader("Stored Memories")

        try:
            # Get the collection
            collection = vdb.vectorstore._collection

            # Fetch all documents from the collection
            count = collection.count()
            if count == 0:
                st.info("No memories stored yet. Add some resources in the 'Add Resources' tab.")
            else:
                st.success(f"Found {count} stored memories")

                results = collection.get(
                    include=["documents", "metadatas"]
                )

                if results and results["ids"]:
                    # Group by URL/source
                    grouped = {}
                    for doc_id, metadata, document in zip(
                        results["ids"],
                        results["metadatas"],
                        results["documents"]
                    ):
                        source = metadata.get("url", metadata.get("source", "Unknown"))
                        if source not in grouped:
                            grouped[source] = []
                        grouped[source].append({
                            "id": doc_id,
                            "content": document,
                            "metadata": metadata
                        })

                    # Display grouped memories
                    for source, docs in grouped.items():
                        with st.expander(f"📄 {source}", expanded=False):
                            st.caption(f"{len(docs)} chunk(s) from this source")

                            for i, doc in enumerate(docs):
                                col1, col2 = st.columns([10, 1])

                                with col1:
                                    st.markdown(f"**Chunk {i + 1}**")

                                    # Show metadata
                                    meta = doc["metadata"]
                                    if "title" in meta:
                                        st.caption(f"Title: {meta['title']}")
                                    if "crawled_at" in meta:
                                        st.caption(f"Indexed: {meta['crawled_at']}")

                                    # Show content preview
                                    preview = doc["content"][:300]
                                    if len(doc["content"]) > 300:
                                        preview += "..."
                                    st.markdown(f"> {preview}")

                                with col2:
                                    if st.button("🗑️", key=f"delete_{doc['id']}"):
                                        collection.delete(ids=[doc["id"]])
                                        st.cache_resource.clear()
                                        st.rerun()
                else:
                    st.info("No memories stored yet.")
        except Exception as e:
            st.error(f"Error loading memories: {e}")
            log.exception("Failed to load memories from database")


if __name__ == "__main__":
    memory_ui()
