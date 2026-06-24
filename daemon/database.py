"""
daemon.database
===============

Backwards-compatible facade over the unified PostgreSQL + pgvector backend.

Historically this module owned three independent storage backends:

* ``VectorDatabase`` — a ChromaDB vector store,
* ``Database``       — a SQLite database of agents/tools + LangGraph SQLite
                       checkpoints, and
* ``LinkQueue``      — a SQLite crawler link queue.

All three are now thin wrappers around the repositories in :mod:`db`, so every
read/write goes to a single self-hosted PostgreSQL database. The public class
names, constructor signatures (including the now-ignored ``chroma_db_path`` /
``db_path`` arguments) and method signatures are preserved so the rest of the
codebase keeps working unchanged.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from daemon.logger import RichLogManager
from db.repositories import (
    MAX_CRAWL_ATTEMPTS,
    MAX_INGEST_ATTEMPTS,
    AgentRepository,
    LinkRepository,
    VectorRepository,
    _backoff,
    _now_iso,
    _retry_at_iso,
)

logger = RichLogManager().get_logger(__name__)

#Re-exported for backwards compatibility. TODO: Remove if needed
__all__ = [
    "ProcessedChunk",
    "VectorDatabase",
    "Database",
    "LinkQueue",
    "_now_iso",
    "_backoff",
    "_retry_at_iso",
    "MAX_CRAWL_ATTEMPTS",
    "MAX_INGEST_ATTEMPTS",
]


@dataclass
class ProcessedChunk:
    url: str
    chunk_number: int
    title: str
    summary: str
    content: str
    metadata: Dict[str, Any]


class VectorDatabase:
    """Vector knowledge base backed by pgvector (was ChromaDB).

    Embeddings are produced with Ollama (an external model server, not a
    storage backend) and persited into the ''documents'' table. The embedding
    model is created lazily so importing this module stays cheap and so tests
    can inject a fake embedder via :meth:`set_embeddings`.
    """ #TODO add cross combatibility so embedding model can be any provider.

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        embedding_model: str = "bge-m3",
        chroma_db_path: Optional[str] = None, # accepted + ignored (legacy) TODO: Remove Legacy Depracated
        embeddings: Any = None,
        **_legacy_kwargs: Any,
    ):
        self.base_url = base_url
        self._embedding_model_name = embedding_model
        self._embeddings = embeddings
        self._repo = VectorRepository()
        self._ollama_semaphore = None

    # --- Embeddings ---
    @property
    def embeddings_model(self):
        """Lazily contruct the Ollama embeddings client."""
        if self._embeddings is None:
            from langchain_ollama import OllamaEmbeddings

            self._embeddings = OllamaEmbeddings(
                model=self._embedding_model_name,
                base_url=self.base_url,
            )
        return self._embeddings
    
    def set_embeddings(self, embeddings: Any) -> None:
        """Override the embeddings client (used in tests)."""
        self._embeddings = embeddings

    # --- VECTOR DATABASE UTILITIES ---
    def similarity_search(self, query: str, k: int = 5) -> List[Any]:
        """Search the vector database, returning langchain ''Document'' objects."""
        from langchain_core.documents import Document

        try:
            embedding = self._embedding_model.embed_query(query)
            results = self._repo.search(embedding, k)
            return [
                Document(page_content=r["content"], metadata=r.get("metadata") or {})
                for r in results
            ]
        except Exception as e:
            raise Exception(f"Vector DB Search Error: {e}")
        
    # --- Knowledge-base management (used by MemoryService) ---

    def count(self) -> int:
        return self._repo.count()
    
    def list_documents(self) -> List[Dict[str, Any]]:
        return self._repo.list_documents()
    
    def delete(self, doc_ids: List[str]) -> int:
        return self._repo.delete(doc_ids)


    # --- SEMAPHORE MANAGEMENT ---

    def get_ollama_semaphore(self):
        """Lazily initialize an asyncio semaphore for the current running loop."""
        current_loop = asyncio.get_running_loop()
        if self._ollama_semaphore is None or getattr(self._ollama_semaphore, "_loop", None) is not current_loop:
            self._ollama_semaphore = asyncio.Semaphore(2)
        return self._ollama_semaphore

    @staticmethod
    def get_title_and_summary(chunk: str, url: str, **kwargs) -> Dict[str, str]:
        # Extract title from first markdown heading, fall back to URL path
        for line in chunk.splitlines():
            line = line.strip()
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                break
        else:
            from urllib.parse import urlparse
            path = urlparse(url).path.strip("/")
            title = path.split("/")[-1].replace("-", " ").replace("_", " ").title() or url

        # Summary = first 200 chars of actual content
        summary = chunk.strip()[:200].replace("\n", " ")

        return {"title": title, "summary": summary}

    async def process_chunk(self, chunk: str, chunk_number: int, url: str) -> ProcessedChunk:
        # Get the semaphore that is bound to the current loop being run by the tool
        semaphore = self.get_ollama_semaphore()
        print(f"[save] process_chunk start: url={url} chunk_number={chunk_number}")
        
        async with semaphore:
            # Move blocking sync calls to threads
            extracted = await asyncio.to_thread(self.get_title_and_summary, chunk, url)
        print(f"[save] process_chunk done: url={url} chunk_number={chunk_number}")

        metadata = {
            "url": url,
            "chunk_number": chunk_number,
            "title": extracted.get('title', 'Untitled'),
            "summary": extracted.get('summary', 'No summary'),
            "crawled_at": datetime.now(timezone.utc).isoformat(),
            "source": "research_agent"
        }
        return ProcessedChunk(
            url=url,
            chunk_number=chunk_number,
            title=extracted.get('title', 'Untitled'),
            summary=extracted.get('summary', 'No summary'),
            content=chunk,
            metadata=metadata
        )
    
    # --- PROCESSING LOGIC ---

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 5000) -> List[str]:
        # Basic splitting
        return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    

    async def insert_chunks_local(self, chunks: List[ProcessedChunk]):
        """Embed processed chunks and insert them into the pgvector store."""
        if not chunks:
            logger.warning("No Chunks Sent - database.py ~ 198")
            return
        
        source_url = chunks[0].metadata.get('url') if chunks else 'N/A'
        contents = [c.content for c in chunks]
        print(f"[save] insert_chunks_local: embdding {len(contents)} documents for {source_url}")
        # Produce embeddings via Ollama (was handled internally by Chroma)
        embeddings = await asyncio.to_thread(self.embeddings_model.embed_documents, contents)

        rows = [
            {"content": c.content, "metadata": c.metadata, "embedding": emb}
            for c, emb in zip(chunks, embeddings)
        ]
        await asyncio.to_thread(self._repo.insert_documents, rows)
        print(f"[save] insert_chunks_local: saved {len(rows)} chunks to Postgres for {source_url}")

    async def process_and_store_document(self, url: str, markdown: str):
        print(f"[save] process_and_store_document start for {url}")
        chunks = self.chunk_text(markdown)
        print(f"[save] process_and_store_document: split into {len(chunks)} chunks for {url}")
        tasks = [self.process_chunk(c, i, url) for i, c in enumerate(chunks)]
        processed_chunks = await asyncio.gather(*tasks)
        print(f"[save] process_and_store_document: processed {len(processed_chunks)} chunks for {url}")
        
        # Store all chunks for this document
        await self.insert_chunks_local(processed_chunks)
        print(f"[save] process_and_store_document complete for {url}")

class Database:
    """Agents + per-agent tool state + LangGraph checkpoints (was SQLite).

    Agent/tool methods are delegated to :class:`db.repositories.AgentRepository`
    via ``__getattr__``; chat-history checkpointing now uses a PostgreSQL-backed
    ``PostgresSaver`` (see :func:`Database.get_checkpointer`).
    """

    def __init__(self, db_path: Any = None, **_legacy_kwargs: Any):
        self._repo = AgentRepository()

    def __getattr__(self, name):
        # Delegate agent/tool methods (register_agent, sync_agents, get_agents,
        # sync_agent_tools, get_agent_tool_states, get_enabled_tool_ids,
        # set_agent_tool_enabled, ...) to the repository.
        if name == "_repo":
            raise AttributeError(name)
        return getattr(self._repo, name)
    
    def get_checkpointer(self):
        """Return the shared LangGraph ``PostgressSaver`` (creates tables once)."""
        from db.checkpointer import get_checkpointer

        return get_checkpointer()
        


class LinkQueue:
    """Crawler link queue (was SQLite ``links.sqlite``).

    A thin facade over :class:`db.repositories.LinkRepository`; all public
    methods (``add_urls``, ``claim_pending_crawl``, ``mark_crawl_success``, ...)
    are delegated unchanged.
    """

    def __init__(self, db_path: Any = None, **_legacy_kwargs: Any):
        self._repo = LinkRepository()

    def __getattr__(self, name: str):
        if name == "_repo":
            raise AttributeError(name)
        return getattr(self._repo, name)