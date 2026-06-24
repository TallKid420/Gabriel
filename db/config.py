"""
db.config
=========

Central configuration for the unified PostgreSQL + pgvector backend.

All storage in Gabriel (chat sessions, messages, agents, per-agent tool state,
the crawler link queue, the vector knowledge base, and LangGraph chat
checkpoints) lives in a single self-hosted PostgreSQL database.

Configuration is read from environment variables, optionally loaded from a
``.env`` file at the project root (see ``.env.example``).

Environment variables
----------------------
DATABASE_URL      libpq connection string for the Postgres instance.
                  Default: postgresql://gabriel:gabriel@localhost:5432/gabriel
EMBEDDING_DIM     Dimensionality of the embedding vectors stored in the
                  ``documents`` table. Must match the embedding model.
                  Default: 1024 (bge-m3).
OLLAMA_BASE_URL   Base URL of the Ollama server used for embeddings/LLM.
                  Default: http://localhost:11434
EMBEDDING_MODEL   Embedding model name served by Ollama.
                  Default: bge-m3
"""

from __future__ import annotations

import os
from pathlib import Path

# Project root is the parent of the ``db`` package directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load a project-level .env if python-dotenv is available. This is best-effort:
# real environment variables always win, and a missing .env is fine.
try:  # pragma: no cover - trivial
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass


DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://gabriel:gabriel@localhost:5432/gabriel",
)

EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "bge-m3")
