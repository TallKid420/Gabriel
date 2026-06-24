"""
db.pool
=======

Process-wide singleton :class:`psycopg_pool.ConnectionPool` for the unified
PostgreSQL backend.

The pool is configured exactly the way both LangGraph's ``PostgresSaver`` and
the pgvector repositories want it:

* ``autocommit=True``      — required by ``PostgresSaver`` and convenient for
                             the simple, single-statement repository methods.
* ``prepare_threshold=0``  — required by ``PostgresSaver``.
* ``row_factory=dict_row`` — repositories address columns by name.

On every new connection we *best-effort* register the pgvector type adapters so
``vector`` columns round-trip as Python objects. Registration failing (e.g. the
adapter not being importable) is non-fatal: every query in this codebase casts
explicitly with ``%s::vector`` string literals, so it never depends on the
adapter being present.
"""

from __future__ import annotations

import logging
from typing import Optional

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from db.config import DATABASE_URL

logger = logging.getLogger(__name__)

_pool: Optional[ConnectionPool] = None


def _configure(conn) -> None:
    """Best-effort: register pgvector adapters on a freshly created connection."""
    try:
        from pgvector.psycopg import register_vector

        register_vector(conn)
    except Exception:  # pragma: no cover - adapter is optional
        # All queries use explicit ``::vector`` casts, so this is purely a
        # convenience and safe to skip.
        logger.debug("pgvector adapter registration skipped", exc_info=True)


def get_pool() -> ConnectionPool:
    """Return the lazily-initialised, process-wide connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=1,
            max_size=10,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
            configure=_configure,
            open=True,
        )
    return _pool


def close_pool() -> None:
    """Close the pool (used on shutdown / in tests)."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
