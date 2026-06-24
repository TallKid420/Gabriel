"""
db
==

Unified PostgreSQL + pgvector data layer for Gabriel.

Every durable backend in the project — chat sessions/messages, agents and
per-agent tool state, the crawler link queue, the vector knowledge base, and
LangGraph chat checkpoints — is stored in a single self-hosted PostgreSQL
database with the ``pgvector`` extension.

Public surface
--------------
* :func:`db.config` values — ``DATABASE_URL``, ``EMBEDDING_DIM`` etc.
* :func:`db.pool.get_pool` — the shared connection pool.
* :func:`db.checkpointer.get_checkpointer` — LangGraph ``PostgresSaver``.
* Repositories in :mod:`db.repositories`.

Run ``python -m db.migrate`` once to create the schema.
"""

from __future__ import annotations

from db.config import (
    DATABASE_URL,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    OLLAMA_BASE_URL,
)
from db.pool import close_pool, get_pool
from db.repositories import (
    AgentRepository,
    LinkRepository,
    SessionRepository,
    VectorRepository,
)

__all__ = [
    "DATABASE_URL",
    "EMBEDDING_DIM",
    "EMBEDDING_MODEL",
    "OLLAMA_BASE_URL",
    "get_pool",
    "close_pool",
    "AgentRepository",
    "LinkRepository",
    "SessionRepository",
    "VectorRepository",
]
