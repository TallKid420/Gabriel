"""
db.migrate
==========

Idempotent schema migration for the unified PostgreSQL + pgvector backend.

Run it once after provisioning the database (see ``POSTGRES_SETUP.md``)::

    python -m db.migrate

It will:
  1. enable the ``vector`` (pgvector) extension,
  2. apply ``db/schema.sql`` (with the ``__EMBEDDING_DIM__`` placeholder
     replaced by the configured ``EMBEDDING_DIM``), and
  3. create the LangGraph checkpoint tables via ``PostgresSaver.setup()``.

All steps use ``CREATE ... IF NOT EXISTS`` (or equivalent) and are safe to
re-run.
"""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg

from db.config import DATABASE_URL, EMBEDDING_DIM

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def _load_schema_sql() -> str:
    raw = _SCHEMA_PATH.read_text(encoding="utf-8")
    return raw.replace("__EMBEDDING_DIM__", str(EMBEDDING_DIM))


def run_migration() -> None:
    """Apply the application schema and the checkpoint schema."""
    schema_sql = _load_schema_sql()

    logger.info("Connecting to %s", DATABASE_URL)
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            logger.info("Ensuring pgvector extension is installed...")
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

            logger.info("Applying application schema (EMBEDDING_DIM=%s)...", EMBEDDING_DIM)
            cur.execute(schema_sql)

    logger.info("Setting up LangGraph checkpoint tables...")
    # Imported lazily so the migration does not hard-require langgraph for the
    # application tables alone.
    from db.checkpointer import setup_checkpointer

    setup_checkpointer()

    logger.info("Migration complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_migration()
    print("✅ PostgreSQL schema migration complete.")
