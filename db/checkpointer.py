"""
db.checkpointer
===============

LangGraph chat-history checkpointing, backed by PostgreSQL.

Replaces the previous ``langgraph.checkpoint.sqlite.SqliteSaver`` (which wrote
to ``database/checkpoints.sqlite``). The ``PostgresSaver`` stores its
checkpoint tables in the same unified database and reuses the shared pool from
:mod:`db.pool` (which is already configured with ``autocommit=True`` and
``prepare_threshold=0`` exactly as ``PostgresSaver`` requires).
"""

from __future__ import annotations

import logging
from typing import Optional

from db.pool import get_pool

logger = logging.getLogger(__name__)

_checkpointer = None


def setup_checkpointer() -> None:
    """Create the LangGraph checkpoint tables (idempotent)."""
    from langgraph.checkpoint.postgres import PostgresSaver

    saver = PostgresSaver(get_pool())
    saver.setup()


def get_checkpointer():
    """Return the process-wide :class:`PostgresSaver` singleton.

    On first call the checkpoint tables are created if they do not yet exist,
    so agents work even if ``db.migrate`` was not run separately.
    """
    global _checkpointer
    if _checkpointer is None:
        from langgraph.checkpoint.postgres import PostgresSaver

        saver = PostgresSaver(get_pool())
        try:
            saver.setup()
        except Exception:
            logger.exception("PostgresSaver.setup() failed")
            raise
        _checkpointer = saver
    return _checkpointer
