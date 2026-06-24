"""
MemoryService
=============

Owns the vector-store knowledge base. Extracted out of ``views/memory.py`` so
the UI no longer instantiates ``VectorDatabase`` or reaches into the underlying
verctor collection directly.

Storage is backed by the unified PostgreSQL + pgvector database (see the
''db'' package). ``VectorDatabase`` pulls in Ollama embeddings, so it is 
imported and constructed lazily.
"""

from __future__ import annotations
from typing import Any
import warnings


class MemoryService:
    def __init__(self, chroma_db_path: str | None = None) -> None:
        self._vdb = None
        if chroma_db_path is not None:
            warnings.warn(
                "chroma_db_path parameter is deprecated and will be removed in a future version",
                DeprecationWarning,
                stacklevel=2,
            )

    @property
    def vdb(self):
        if self._vdb is None:
            from daemon.database import VectorDatabase

            self._vdb = VectorDatabase()
        return self._vdb

    # -- reads ---------------------------------------------------------------
    def count(self) -> int:
        return self.vdb.count()

    def list_memories(self) -> dict[str, list[dict[str, Any]]]:
        """Return stored chunks grouped by source URL."""
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in self.vdb.list_documents():
                metadata = row.get("metadata") or {}
                source = metadata.get("url", metadata.get("source", "Unknown"))
                grouped.setdefault(source, []).append(
                    {
                        "id": row.get("id"), 
                        "content": row.get("content"), 
                        "metadata": metadata,
                    }
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
        self.vdb.delete(ids=doc_ids)

    async def add_document(self, url: str, markdown: str) -> None:
        await self.vdb.process_and_store_document(url, markdown)
