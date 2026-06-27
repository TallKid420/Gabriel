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
from fastapi.exceptions import HTTPException
from typing import Any
import warnings
import logging

log = logging.getLogger(__name__)

class MemoryService:
    def __init__(self, chroma_db_path: str | None = None) -> None:
        self._normalizer = None
        self._vdb = None
        self._dblq = None # Database Link Quene

        if chroma_db_path is not None:
            warnings.warn(
                "chroma_db_path parameter is deprecated and will be removed in a future version",
                DeprecationWarning,
                stacklevel=2,
            )

    @property
    def normalizer(self):
        if self.normalizer is None:
            from daemon.document import DocumentNormalizer

            self._normalizer = DocumentNormalizer()
        return self._normalizer


    @property
    def dblq(self):
        if self._dblq is None:
            from db.repositories import LinkRepository

            self._dblq = LinkRepository()
        return self._dblq

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

# TODO MemoryService should have ingest_url() and ingest_file() 
# methods that internally enqueue URLs via LinkQueue.add_urls or 
# call the ingestion heartbeat manually for uploaded files.

    async def ingest_url(self, url: str) -> None:
        self.dblq.add_url(
            url=url,
            source_type="direct_url",
        )

    async def ingest_file(self, filePath: str) -> None:
        """
        Embed a local document into the vector store.

        A synthetic URL of the form ``file://{absolute_path.as_uri()}`` is used as
        metadata so that search results can be traced back to the original file.
        """
        from pathlib import Path

        path = Path(filePath)

        if not path.is_file():
            raise HTTPException(status_code=422, detail=f"Document not found: {filePath}")

        markdown: str

        try:
            markdown = self.normalizer.docling_normalizer(path=path)

        except Exception as e:
            log.error(f"Docling Error; Moving to backup: {e}")
            markdown = self.normalizer.normalize_document(path=path)

        except NotImplementedError:
            raise HTTPException(
                status_code=422,
                detail=f"Document type '{path.suffix.lower()}' not supported",
            )
        except Exception as exc:           # catch any unexpected import / runtime error
            log.debug("ingest_file error for %s: %s", filePath, path.suffix.lower())
            raise HTTPException(status_code=422, detail=str(path.suffix.lower()))

        url = f"file://{path.resolve().as_uri()}"
        log.debug(
            "Ingesting file %s as URL %s – %d chars",
            filePath,
            url,
            len(markdown),
        )

        # Forward to the vector store
        await self.vdb.process_and_store_document(url, markdown)