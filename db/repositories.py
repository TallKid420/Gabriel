"""
db.repositories
===============

Persistence layer for the unified PostgreSQL + pgvector backend. Every read and
write to durable storage in Gabriel goes through one of the repositories here:

* :class:`SessionRepository` — chat sessions + messages
                               (was ``database/sessions.json``).
* :class:`AgentRepository`   — agents + per-agent tool enablement
                               (was ``database/checkpoints.sqlite``).
* :class:`LinkRepository`    — crawler link queue
                               (was ``database/links.sqlite``).
* :class:`VectorRepository`  — vector knowledge base
                               (was the ChromaDB ``agent_collection``).

All repositories share the singleton connection pool from :mod:`db.pool`.

Notes on vectors
----------------
Vector values are passed to PostgreSQL as ``%s::vector`` string literals (e.g.
``'[0.1,0.2,...]'``). This is fully reliable regardless of whether the optional
``pgvector`` Python adapter is registered, and is used for both inserts and the
cosine-distance (``<=>``) similarity queries.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from db.pool import get_pool


# ── Time / retry helpers ──────────────────────────────────────────────────--
# These live here (rather than in daemon.database) so the persistence layer has
# no upward dependency. ``daemon.database`` re-exports them for backwards
# compatibility.

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _backoff(retry_count: int) -> float:
    """Exponential backoff with jitter (~60s, ~4m, ~16m for attempts 0/1/2)."""
    base = 60
    jitter = random.uniform(0, 30)
    return base * (4 ** retry_count) + jitter


def _retry_at_iso(retry_count: int) -> str:
    """ISO timestamp offset from now by the backoff for ``retry_count``."""
    delta = timedelta(seconds=_backoff(retry_count))
    return (datetime.now(timezone.utc) + delta).isoformat()


# ── Vector helpers ────────────────────────────────────────────────────────--

def _vector_literal(vec: Iterable[float]) -> str:
    """Render an embedding as a pgvector string literal: ``[0.1,0.2,...]``."""
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


# ── Sessions ──────────────────────────────────────────────────────────────--

class SessionRepository:
    """Chat sessions and their messages."""

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Return all sessions (with messages) ordered by creation."""
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, created_at, agent_name FROM sessions ORDER BY seq ASC"
            )
            sessions = cur.fetchall()

            cur.execute(
                "SELECT session_id, role, content FROM messages "
                "ORDER BY session_id, position ASC"
            )
            messages = cur.fetchall()

        grouped: Dict[str, List[Dict[str, str]]] = {}
        for m in messages:
            grouped.setdefault(m["session_id"], []).append(
                {"role": m["role"], "content": m["content"]}
            )

        for s in sessions:
            s["messages"] = grouped.get(s["id"], [])
        return sessions

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, created_at, agent_name FROM sessions WHERE id = %s",
                (session_id,),
            )
            session = cur.fetchone()
            if session is None:
                return None

            cur.execute(
                "SELECT role, content FROM messages WHERE session_id = %s "
                "ORDER BY position ASC",
                (session_id,),
            )
            session["messages"] = [
                {"role": r["role"], "content": r["content"]} for r in cur.fetchall()
            ]
        return session

    def exists(self, session_id: str) -> bool:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM sessions WHERE id = %s", (session_id,))
            return cur.fetchone() is not None

    def create_session(
        self,
        session_id: str,
        title: str,
        created_at: str,
        agent_name: Optional[str],
    ) -> None:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (id, title, created_at, agent_name) "
                "VALUES (%s, %s, %s, %s)",
                (session_id, title, created_at, agent_name),
            )

    def delete_session(self, session_id: str) -> bool:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
            return cur.rowcount > 0

    def append_message(self, session_id: str, role: str, content: str) -> None:
        """Append a message. Caller must ensure the session exists."""
        pool = get_pool()
        with pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (session_id, position, role, content) "
                "SELECT %s, COALESCE(MAX(position), -1) + 1, %s, %s "
                "FROM messages WHERE session_id = %s",
                (session_id, role, content, session_id),
            )

    def update_title(self, session_id: str, title: str) -> None:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE sessions SET title = %s WHERE id = %s", (title, session_id)
            )

    def set_agent(self, session_id: str, agent_name: str) -> bool:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE sessions SET agent_name = %s WHERE id = %s",
                (agent_name, session_id),
            )
            return cur.rowcount > 0

    def clear_messages(self, session_id: str) -> bool:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            if not self.exists(session_id):
                return False
            cur.execute("DELETE FROM messages WHERE session_id = %s", (session_id,))
            return True

    def replace_all(self, sessions: List[Dict[str, Any]]) -> None:
        """Atomically replace the entire session store.

        Mirrors the old JSON ``_save_raw`` semantics (whole-file overwrite):
        any session not present in ``sessions`` is removed. ``sessions`` is a
        list of dicts shaped like ``ChatSession.to_dict()``.
        """
        pool = get_pool()
        with pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            # ON DELETE CASCADE removes the associated messages.
            cur.execute("DELETE FROM sessions")
            for s in sessions:
                cur.execute(
                    "INSERT INTO sessions (id, title, created_at, agent_name) "
                    "VALUES (%s, %s, %s, %s)",
                    (s["id"], s.get("title", "New chat"), s.get("created_at", ""), s.get("agent_name")),
                )
                for position, message in enumerate(s.get("messages", [])):
                    cur.execute(
                        "INSERT INTO messages (session_id, position, role, content) "
                        "VALUES (%s, %s, %s, %s)",
                        (s["id"], position, message.get("role", ""), message.get("content", "")),
                    )


# ── Agents + tools ──────────────────────────────────────────────────────────

class AgentRepository:
    """Agents and per-agent tool enablement."""

    def register_agent(self, agent_id: str, name: str) -> None:
        now = _now_iso()
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agents (agent_id, name, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (agent_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    updated_at = EXCLUDED.updated_at
                """,
                (str(agent_id), str(name), now),
            )

    def sync_agents(self, agents: List[tuple]) -> None:
        now = _now_iso()
        rows = [(str(agent_id), str(name), now) for agent_id, name in agents]
        if not rows:
            return
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO agents (agent_id, name, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (agent_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    updated_at = EXCLUDED.updated_at
                """,
                rows,
            )

    def get_agents(self) -> List[Dict[str, str]]:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT agent_id, name FROM agents ORDER BY lower(name)"
            )
            rows = cur.fetchall()
        return [{"agent_id": row["agent_id"], "name": row["name"]} for row in rows]

    def sync_agent_tools(
        self, agent_id: str, tool_ids: Optional[List[str]] = None
    ) -> None:
        if tool_ids is None:
            from executor.toolhandler import load_tool_registry

            tool_ids = [record.id for record in load_tool_registry().list_tools()]

        if not tool_ids:
            return

        now = _now_iso()
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO agent_tools (agent_id, tool_id, enabled, updated_at)
                VALUES (%s, %s, FALSE, %s)
                ON CONFLICT (agent_id, tool_id) DO NOTHING
                """,
                [(str(agent_id), tool_id, now) for tool_id in tool_ids],
            )

    def get_agent_tool_states(self, agent_id: str) -> Dict[str, bool]:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT tool_id, enabled FROM agent_tools WHERE agent_id = %s",
                (str(agent_id),),
            )
            rows = cur.fetchall()
        return {row["tool_id"]: bool(row["enabled"]) for row in rows}

    def get_enabled_tool_ids(self, agent_id: str) -> set[str]:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT tool_id FROM agent_tools WHERE agent_id = %s AND enabled = TRUE",
                (str(agent_id),),
            )
            rows = cur.fetchall()
        return {row["tool_id"] for row in rows}

    def set_agent_tool_enabled(
        self, agent_id: str, tool_id: str, enabled: bool
    ) -> None:
        now = _now_iso()
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_tools (agent_id, tool_id, enabled, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (agent_id, tool_id) DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    updated_at = EXCLUDED.updated_at
                """,
                (str(agent_id), tool_id, bool(enabled), now),
            )


# ── Crawler link queue ──────────────────────────────────────────────────────

MAX_CRAWL_ATTEMPTS = 3
MAX_INGEST_ATTEMPTS = 3


class LinkRepository:
    """Crawler link queue — Postgres port of the former ``links.sqlite``.

    Atomic claim operations use ``SELECT ... FOR UPDATE SKIP LOCKED`` so
    concurrent crawl/ingest workers never double-claim a row (the Postgres
    equivalent of the previous SQLite ``BEGIN IMMEDIATE`` transactions).
    """

    # ── URL intake ────────────────────────────────────────────────────────--
    def add_urls(
        self,
        urls: List[str],
        source_type: str,
        source_value: Optional[str] = None,
        content_kind: str = "page",
        parent_url: Optional[str] = None,
    ) -> int:
        """Normalize and insert URLs as pending. Returns count newly inserted."""
        from daemon.url_parser.normalizer import normalize_url
        now = _now_iso()
        added = 0
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            for raw_url in urls:
                normalized = normalize_url(raw_url)
                if not normalized:
                    continue
                cur.execute(
                    """
                    INSERT INTO links (
                        url, parent_url, content_kind,
                        source_type, source_value,
                        crawl_status, ingest_status,
                        discovered_at
                    ) VALUES (%s, %s, %s, %s, %s, 'pending', 'not_started', %s)
                    ON CONFLICT (url) DO NOTHING
                    """,
                    (normalized, parent_url, content_kind, source_type, source_value, now),
                )
                if cur.rowcount:
                    added += 1
        return added

    def add_url(
        self,
        url: str,
        source_type: str,
        source_value: Optional[str] = None,
        content_kind: str = "page",
        parent_url: Optional[str] = None,
    ) -> bool:
        """
        Normalize and insert a single URL as pending.

        Returns:
            bool: True if the URL was inserted, False if it already existed or was invalid.
        """
        from daemon.url_parser.normalizer import normalize_url

        normalized = normalize_url(url)
        if not normalized:
            return False

        now = _now_iso()

        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO links (
                    url,
                    parent_url,
                    content_kind,
                    source_type,
                    source_value,
                    crawl_status,
                    ingest_status,
                    discovered_at
                )
                VALUES (%s, %s, %s, %s, %s, 'pending', 'not_started', %s)
                ON CONFLICT (url) DO NOTHING
                """,
                (
                    normalized,
                    parent_url,
                    content_kind,
                    source_type,
                    source_value,
                    now,
                ),
            )

            return cur.rowcount > 0

    # ── Crawl claim / result ──────────────────────────────────────────────--
    def claim_pending_crawl(self, limit: int = 10) -> List[Dict[str, Any]]:
        now = _now_iso()
        pool = get_pool()
        with pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM links
                WHERE crawl_status = 'pending'
                  AND (next_retry_at IS NULL OR next_retry_at <= %s)
                ORDER BY discovered_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (now, limit),
            )
            rows = cur.fetchall()
            if not rows:
                return []

            ids = [r["id"] for r in rows]
            cur.execute(
                """
                UPDATE links
                SET crawl_status = 'in_progress', claimed_at = %s
                WHERE id = ANY(%s)
                """,
                (now, ids),
            )
        return [dict(r) for r in rows]

    def mark_crawl_success(
        self, url: str, raw_path: str, content_kind: str = "page"
    ) -> None:
        now = _now_iso()
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE links
                SET crawl_status  = 'crawled',
                    ingest_status = 'pending',
                    raw_path      = %s,
                    content_kind  = %s,
                    crawled_at    = %s,
                    last_failure_reason = NULL,
                    last_http_status    = NULL,
                    last_failure_stage  = NULL
                WHERE url = %s
                """,
                (raw_path, content_kind, now, url),
            )

    def mark_crawl_failed(
        self,
        url: str,
        reason: str,
        http_status: Optional[int] = None,
        retryable: bool = False,
    ) -> None:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT retry_count FROM links WHERE url = %s", (url,))
            row = cur.fetchone()
            if row is None:
                print(f"[LinkQueue] mark_crawl_failed: URL not found: {url}")
                return

            retry_count = row["retry_count"] + 1
            if retryable and retry_count < MAX_CRAWL_ATTEMPTS:
                next_retry = _retry_at_iso(retry_count)
                cur.execute(
                    """
                    UPDATE links
                    SET crawl_status        = 'pending',
                        retry_count         = %s,
                        next_retry_at       = %s,
                        last_http_status    = %s,
                        last_failure_reason = %s,
                        last_failure_stage  = 'crawl'
                    WHERE url = %s
                    """,
                    (retry_count, next_retry, http_status, reason, url),
                )
                print(
                    f"[LinkQueue] crawl retry {retry_count}/{MAX_CRAWL_ATTEMPTS} "
                    f"scheduled at {next_retry} for {url}"
                )
            else:
                cur.execute(
                    """
                    UPDATE links
                    SET crawl_status        = 'failed',
                        retry_count         = %s,
                        next_retry_at       = NULL,
                        last_http_status    = %s,
                        last_failure_reason = %s,
                        last_failure_stage  = 'crawl'
                    WHERE url = %s
                    """,
                    (retry_count, http_status, reason, url),
                )
                print(f"[LinkQueue] crawl permanently failed for {url}: {reason}")

    def release_claimed(self, reason: str = "daemon_shutdown") -> int:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE links
                SET crawl_status        = 'pending',
                    claimed_at          = NULL,
                    last_failure_reason = %s,
                    last_failure_stage  = 'crawl'
                WHERE crawl_status = 'in_progress'
                """,
                (reason,),
            )
            crawl_released = cur.rowcount

            cur.execute(
                """
                UPDATE links
                SET ingest_status       = 'pending',
                    last_failure_reason = %s,
                    last_failure_stage  = 'ingest'
                WHERE ingest_status = 'in_progress'
                """,
                (reason,),
            )
            ingest_released = cur.rowcount

        total = crawl_released + ingest_released
        if total:
            print(
                f"[LinkQueue] release_claimed: released {crawl_released} crawl "
                f"+ {ingest_released} ingest rows (reason={reason})"
            )
        return total

    def mark_404_requeue(self, original_url: str, stripped_url: str) -> int:
        now = _now_iso()
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE links
                SET crawl_status        = 'skipped',
                    last_failure_reason = '404_stripped_requeued',
                    last_http_status    = 404,
                    last_failure_stage  = 'crawl'
                WHERE url = %s
                """,
                (original_url,),
            )
            cur.execute(
                """
                INSERT INTO links (
                    url, parent_url, content_kind,
                    source_type, source_value,
                    crawl_status, ingest_status,
                    retry_count, discovered_at
                )
                SELECT %s, url, content_kind, source_type, source_value,
                       'pending', 'not_started', 0, %s
                FROM links WHERE url = %s
                ON CONFLICT (url) DO NOTHING
                """,
                (stripped_url, now, original_url),
            )
            if cur.rowcount:
                print(f"[LinkQueue] 404 requeue: '{original_url}' -> '{stripped_url}'")
                return 1
            print(
                f"[LinkQueue] 404 requeue: stripped URL already exists: '{stripped_url}'"
            )
            return 0

    # ── Ingest claim / result ─────────────────────────────────────────────--
    def claim_pending_ingest(self, limit: int = 10) -> List[Dict[str, Any]]:
        pool = get_pool()
        with pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM links
                WHERE ingest_status = 'pending'
                  AND crawl_status  = 'crawled'
                ORDER BY crawled_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (limit,),
            )
            rows = cur.fetchall()
            if not rows:
                return []

            ids = [r["id"] for r in rows]
            cur.execute(
                "UPDATE links SET ingest_status = 'in_progress' WHERE id = ANY(%s)",
                (ids,),
            )
        return [dict(r) for r in rows]

    def mark_ingest_success(self, url: str) -> None:
        now = _now_iso()
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE links
                SET ingest_status       = 'stored',
                    ingested_at         = %s,
                    last_failure_reason = NULL,
                    last_failure_stage  = NULL
                WHERE url = %s
                """,
                (now, url),
            )

    def mark_ingest_failed(
        self, url: str, reason: str, retryable: bool = False
    ) -> None:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT retry_count FROM links WHERE url = %s", (url,))
            row = cur.fetchone()
            if row is None:
                print(f"[LinkQueue] mark_ingest_failed: URL not found: {url}")
                return

            retry_count = row["retry_count"] + 1
            if retryable and retry_count < MAX_INGEST_ATTEMPTS:
                next_retry = _retry_at_iso(retry_count)
                cur.execute(
                    """
                    UPDATE links
                    SET ingest_status       = 'pending',
                        retry_count         = %s,
                        next_retry_at       = %s,
                        last_failure_reason = %s,
                        last_failure_stage  = 'ingest'
                    WHERE url = %s
                    """,
                    (retry_count, next_retry, reason, url),
                )
                print(
                    f"[LinkQueue] ingest retry {retry_count}/{MAX_INGEST_ATTEMPTS} "
                    f"scheduled at {next_retry} for {url}"
                )
            else:
                cur.execute(
                    """
                    UPDATE links
                    SET ingest_status       = 'failed',
                        retry_count         = %s,
                        next_retry_at       = NULL,
                        last_failure_reason = %s,
                        last_failure_stage  = 'ingest'
                    WHERE url = %s
                    """,
                    (retry_count, reason, url),
                )
                print(f"[LinkQueue] ingest permanently failed for {url}: {reason}")

    # ── Backpressure ──────────────────────────────────────────────────────--
    def get_raw_saved_count(self) -> int:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS cnt FROM links
                WHERE ingest_status IN ('pending', 'in_progress')
                  AND crawl_status  = 'crawled'
                """
            )
            row = cur.fetchone()
        return row["cnt"] if row else 0

    # ── Manual operations ─────────────────────────────────────────────────--
    def force_recrawl(self, url: str) -> None:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE links
                SET crawl_status        = 'pending',
                    ingest_status       = 'not_started',
                    retry_count         = 0,
                    next_retry_at       = NULL,
                    raw_path            = NULL,
                    claimed_at          = NULL,
                    crawled_at          = NULL,
                    ingested_at         = NULL,
                    last_http_status    = NULL,
                    last_failure_reason = NULL,
                    last_failure_stage  = NULL
                WHERE url = %s
                """,
                (url,),
            )
            if cur.rowcount == 0:
                print(f"[LinkQueue] force_recrawl: URL not found: {url}")
            else:
                print(f"[LinkQueue] force_recrawl: reset {url}")

    # ── Debug / stats ─────────────────────────────────────────────────────--
    def get_stats(self) -> Dict[str, Any]:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT crawl_status, ingest_status, COUNT(*) AS cnt
                FROM links
                GROUP BY crawl_status, ingest_status
                """
            )
            rows = cur.fetchall()
        stats: Dict[str, Any] = {}
        for row in rows:
            key = f"crawl={row['crawl_status']} ingest={row['ingest_status']}"
            stats[key] = row["cnt"]
        return stats


# ── Vector knowledge base ─────────────────────────────────────────────────--

class VectorRepository:
    """pgvector-backed knowledge base — replaces the ChromaDB collection."""

    def insert_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Insert chunk rows.

        Each item: ``{"content": str, "metadata": dict, "embedding": list[float]}``.
        """
        if not documents:
            return
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            for doc in documents:
                metadata = doc.get("metadata") or {}
                cur.execute(
                    """
                    INSERT INTO documents (url, content, metadata, embedding)
                    VALUES (%s, %s, %s::jsonb, %s::vector)
                    """,
                    (
                        metadata.get("url"),
                        doc["content"],
                        json.dumps(metadata),
                        _vector_literal(doc["embedding"]),
                    ),
                )

    def count(self) -> int:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM documents")
            row = cur.fetchone()
        return row["cnt"] if row else 0

    def list_documents(self) -> List[Dict[str, Any]]:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id::text AS id, url, content, metadata FROM documents "
                "ORDER BY created_at ASC"
            )
            rows = cur.fetchall()
        return [
            {
                "id": row["id"],
                "url": row["url"],
                "content": row["content"],
                "metadata": row["metadata"] or {},
            }
            for row in rows
        ]

    def delete(self, doc_ids: List[str]) -> int:
        if not doc_ids:
            return 0
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM documents WHERE id = ANY(%s::uuid[])",
                ([str(d) for d in doc_ids],),
            )
            return cur.rowcount

    def search(self, embedding: Iterable[float], k: int = 5) -> List[Dict[str, Any]]:
        """Return the ``k`` nearest chunks by cosine distance."""
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT content, metadata
                FROM documents
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (_vector_literal(embedding), k),
            )
            rows = cur.fetchall()
        return [
            {"content": row["content"], "metadata": row["metadata"] or {}}
            for row in rows
        ]
