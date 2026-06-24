"""
MemoryService
=============

Owns the vector-store knowledge base. Extracted out of ``views/memory.py`` so
the UI no longer instantiates ``VectorDatabase`` or reaches into the underlying
Chroma collection directly.

``VectorDatabase`` pulls in Ollama embeddings + Chroma, so it is imported and
constructed lazily.
"""

from __future__ import annotations

from typing import Any, Optional


class MemoryService:
    def __init__(self, chroma_db_path: str = "./database/") -> None:
        self._chroma_db_path = chroma_db_path
        self._vdb = None

    @property
    def vdb(self):
        if self._vdb is None:
            from daemon.database import VectorDatabase

            self._vdb = VectorDatabase(chroma_db_path=self._chroma_db_path)
        return self._vdb

    @property
    def _collection(self):
        return self.vdb.vectorstore._collection

    # -- reads ---------------------------------------------------------------
    def count(self) -> int:
        return self._collection.count()

    def list_memories(self) -> dict[str, list[dict[str, Any]]]:
        """Return stored chunks grouped by source URL."""
        collection = self._collection
        if collection.count() == 0:
            return {}
        results = collection.get(include=["documents", "metadatas"])
        grouped: dict[str, list[dict[str, Any]]] = {}
        if results and results.get("ids"):
            for doc_id, metadata, document in zip(
                results["ids"], results["metadatas"], results["documents"]
            ):
                source = metadata.get("url", metadata.get("source", "Unknown"))
                grouped.setdefault(source, []).append(
                    {"id": doc_id, "content": document, "metadata": metadata}
                )
        return grouped

    def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        docs = self.vdb.similarity_search(query, k=k)
        return [
            {"content": d.page_content, "metadata": getattr(d, "metadata", {})}
            for d in docs
        ]

    # -- writes --------------------------------------------------------------
    def delete(self, doc_ids: list[str]) -> None:
        self._collection.delete(ids=doc_ids)

    async def add_document(self, url: str, markdown: str) -> None:
        await self.vdb.process_and_store_document(url, markdown)
