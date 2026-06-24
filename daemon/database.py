from langchain_ollama import OllamaEmbeddings
from langchain_core.documents import Document
from langchain_chroma import Chroma

from daemon.logger import RichLogManager

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, List

from pathlib import Path
import sqlite3

import random
import asyncio

logger = RichLogManager().get_logger(__name__)

CP_DB_PATH = Path(__file__).resolve().parent.parent / "database" / "checkpoints.sqlite"

@dataclass
class ProcessedChunk:
    url: str
    chunk_number: int
    title: str
    summary: str
    content: str
    metadata: Dict[str, Any]

class VectorDatabase:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        embedding_model: str = "bge-m3",
        chroma_db_path: str = "./database/",
    ):
        self.base_url        = base_url

        self.embeddings_model = OllamaEmbeddings(
            model=embedding_model,
            base_url=base_url,
        )
        self.vectorstore = Chroma(
            collection_name="agent_collection",
            embedding_function=self.embeddings_model,
            persist_directory=chroma_db_path,
        )
        self._ollama_semaphore = None

    # --- VECTOR DATABASE UTILITIES ---
    def similarity_search(self, query: str, k: int = 5) -> List[Document]:
        """Search the vector database for relevant documents."""
        try:
            results = self.vectorstore.similarity_search(query, k)
            return results or []
        except Exception as e:
            raise Exception(f"Vector DB Search Error: {e}")


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
        """Insert processed chunks into the local ChromaDB."""
        # try:
        documents = [
            Document(
                page_content=c.content,
                metadata=c.metadata
            ) for c in chunks
        ]
        source_url = chunks[0].metadata.get('url') if chunks else 'N/A'
        print(f"[save] insert_chunks_local: adding {len(documents)} documents for {source_url}")
        # ChromaDB handles embeddings internally via the embeddings_model we passed
        await asyncio.to_thread(self.vectorstore.add_documents, documents)
        print(f"[save] insert_chunks_local: saved {len(chunks)} chunks to local DB for {source_url}")
        # except Exception as e:
        #     logger.exception(f"Local DB Error: {e}")
        #     raise

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
    def __init__(self, db_path: Path = CP_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def connect_sync(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    _REQUIRED_COLLUMS = {
        "agents": {"agent_id", "name", "updated_at"},
        "agent_tools": {"agent_id", "tool_id", "enabled", "updated_at"},
    }

    def _existing_columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row["name"] for row in rows}
    
    def _reconcile_legacy_schema(self, conn: sqlite3.Connection) -> None:
        for table, required in self._REQUIRED_COLLUMS.items():
            cols = self._existing_columns(conn, table)
            if cols and not required.issubset(cols):
                logger.warning(
                    "Rebuilding incompatible legacy '%s' table "
                    "(found columns %s, expected %s)",
                )
                conn.execute(f"DROP TABLE IF EXISTS {table}")

    def _init_db(self) -> None:
        with self.connect_sync() as conn:
            self._reconcile_legacy_schema(conn)

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id   TEXT PRIMARY KEY,
                    name       TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_tools (
                    agent_id    TEXT NOT NULL,
                    tool_id     TEXT NOT NULL,
                    enabled     INTEGER NOT NULL DEFAULT 0,
                    updated_at  TEXT NOT NULL,
                    PRIMARY KEY (agent_id, tool_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_tools_agent ON agent_tools (agent_id)"
            )

    def register_agent(self, agent_id: str, name: str) -> None:
        now = _now_iso()
        with self.connect_sync() as conn:
            conn.execute(
                """
                INSERT INTO agents (agent_id, name, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    name = excluded.name,
                    updated_at = excluded.updated_at
                """,
                (str(agent_id), str(name), now),
            )

    def sync_agents(self, agents: List[tuple]) -> None:
        now = _now_iso()
        rows = [(str(agent_id), str(name), now) for agent_id, name in agents]
        if not rows:
            return
        with self.connect_sync() as conn:
            conn.executemany(
                """
                INSERT INTO agents (agent_id, name, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    name = excluded.name,
                    updated_at = excluded.updated_at
                """,
                rows,
            )

    def get_agents(self) -> List[Dict[str, str]]:
        with self.connect_sync() as conn:
            rows = conn.execute(
                "SELECT agent_id, name FROM agents ORDER BY name COLLATE NOCASE"
            ).fetchall()

        return [{"agent_id": row["agent_id"], "name": row["name"]} for row in rows]

    def sync_agent_tools(self, agent_id: str, tool_ids: List[str] | None = None) -> None:
        
        if tool_ids is None:
            # If tool_ids is equal to literal object None
            from executor.toolhandler import load_tool_registry

            tool_ids = [record.id for record in load_tool_registry().list_tools()]

        if not tool_ids:
            # If tool_ids is equal to []
            return
        
        now = _now_iso() 
        with self.connect_sync() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO agent_tools (agent_id, tool_id, enabled, updated_at)
                VALUES (?, ?, 0, ?)
                """,
                [(str(agent_id), tool_id, now) for tool_id in tool_ids],
            )

    def get_agent_tool_states(self, agent_id: str) -> Dict[str, bool]:
        with self.connect_sync() as conn:
            rows = conn.execute(
                """
                SELECT tool_id, enabled
                FROM agent_tools
                WHERE agent_id = ?
                """,
                (str(agent_id),),
            ).fetchall()

        return {row["tool_id"]: bool(row["enabled"]) for row in rows}
    
    
    def get_enabled_tool_ids(self, agent_id: str) -> set[str]:
        with self.connect_sync() as conn:
            rows = conn.execute(
                """
                SELECT tool_id
                FROM agent_tools
                WHERE agent_id = ? AND enabled = 1
                """,
                (str(agent_id),),
            ).fetchall()
        return {row["tool_id"] for row in rows}
    
    def set_agent_tool_enabled(self, agent_id: str, tool_id: str, enabled: bool) -> None:
        now = _now_iso()
        with self.connect_sync() as conn:
            conn.execute(
                """
                INSERT INTO agent_tools (agent_id, tool_id, enabled, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(agent_id, tool_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (str(agent_id), tool_id, 1 if enabled else 0, now),
            )

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
LQ_DB_PATH = Path(__file__).resolve().parent.parent / "database" / "links.sqlite"

MAX_CRAWL_ATTEMPTS  = 3
MAX_INGEST_ATTEMPTS = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _backoff(retry_count: int) -> float:
    """
    Exponential backoff with jitter.
      attempt 0 -> ~60s
      attempt 1 -> ~4m
      attempt 2 -> ~16m
    Returns seconds as a float.
    """
    base    = 60
    jitter  = random.uniform(0, 30)
    return base * (4 ** retry_count) + jitter


def _retry_at_iso(retry_count: int) -> str:
    """Return an ISO timestamp offset from now by the backoff for retry_count."""
    from datetime import timedelta
    delta = timedelta(seconds=_backoff(retry_count))
    return (datetime.now(timezone.utc) + delta).isoformat()


class LinkQueue:
    """
    Manages the links.sqlite queue database.

    All public methods are synchronous and thread-safe via SQLite's
    WAL mode + BEGIN IMMEDIATE transactions for claim operations.

    Intended usage:
        lq = LinkQueue()
        lq.add_urls(["https://example.com"], source_type="direct_url", source_value="cli")
        rows = lq.claim_pending_crawl(limit=5)
        for row in rows:
            ...
            lq.mark_crawl_success(row["url"], raw_path="/data/raw/abc.md")
    """

    def __init__(self, db_path: Path = LQ_DB_PATH):
        self.db_path = db_path
        self._init_db()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        schema = _SCHEMA_PATH.read_text()
        with self._connect() as conn:
            conn.executescript(schema)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return dict(row)

    # ── URL intake ────────────────────────────────────────────────────────────

    def add_urls(
        self,
        urls: List[str],
        source_type: str,
        source_value: str | None = None,
        content_kind: str = "page",
        parent_url: str | None = None,
    ) -> int:
        """
        Normalize and insert URLs as pending.
        Silently skips any URL already present in the DB (any status).

        Returns count of newly inserted URLs.
        """
        from daemon.url_parser.normalizer import normalize_url

        now = _now_iso()
        added = 0

        with self._connect() as conn:
            for raw_url in urls:
                normalized = normalize_url(raw_url)
                if not normalized:
                    continue

                try:
                    conn.execute(
                        """
                        INSERT INTO links (
                            url, parent_url, content_kind,
                            source_type, source_value,
                            crawl_status, ingest_status,
                            discovered_at
                        ) VALUES (?, ?, ?, ?, ?, 'pending', 'not_started', ?)
                        """,
                        (normalized, parent_url, content_kind,
                         source_type, source_value, now),
                    )
                    added += 1
                except sqlite3.IntegrityError:
                    # UNIQUE constraint: URL already exists, skip silently
                    pass

        return added

    # ── Crawl claim / result ──────────────────────────────────────────────────

    def claim_pending_crawl(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Atomically claim up to `limit` URLs ready for crawling.

        Eligible rows:
          - crawl_status = 'pending'
          - next_retry_at IS NULL OR next_retry_at <= now

        Sets crawl_status = 'in_progress', claimed_at = now.
        Returns list of row dicts.
        """
        now = _now_iso()
        with self._connect() as conn:
            # BEGIN IMMEDIATE prevents concurrent daemons from double-claiming
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT * FROM links
                WHERE crawl_status = 'pending'
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ORDER BY discovered_at ASC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()

            if not rows:
                conn.execute("COMMIT")
                return []

            ids = [r["id"] for r in rows]
            conn.execute(
                f"""
                UPDATE links
                SET crawl_status = 'in_progress',
                    claimed_at   = ?
                WHERE id IN ({','.join('?' * len(ids))})
                """,
                [now, *ids],
            )
            conn.execute("COMMIT")

        return [self._row_to_dict(r) for r in rows]

    def mark_crawl_success(
        self,
        url: str,
        raw_path: str,
        content_kind: str = "page",
    ) -> None:
        """
        Mark a URL as successfully crawled.
        Sets ingest_status to 'pending' so the ingest worker picks it up.
        """
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE links
                SET crawl_status  = 'crawled',
                    ingest_status = 'pending',
                    raw_path      = ?,
                    content_kind  = ?,
                    crawled_at    = ?,
                    last_failure_reason = NULL,
                    last_http_status    = NULL,
                    last_failure_stage  = NULL
                WHERE url = ?
                """,
                (raw_path, content_kind, now, url),
            )

    def mark_crawl_failed(
        self,
        url: str,
        reason: str,
        http_status: int | None = None,
        retryable: bool = False,
    ) -> None:
        """
        Record a crawl failure.

        If retryable and under MAX_CRAWL_ATTEMPTS:
          - keeps crawl_status = 'pending'
          - sets next_retry_at using exponential backoff

        Otherwise sets crawl_status = 'failed'.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT retry_count FROM links WHERE url = ?", (url,)
            ).fetchone()

            if row is None:
                print(f"[LinkQueue] mark_crawl_failed: URL not found: {url}")
                return

            retry_count = row["retry_count"] + 1

            if retryable and retry_count < MAX_CRAWL_ATTEMPTS:
                next_retry = _retry_at_iso(retry_count)
                conn.execute(
                    """
                    UPDATE links
                    SET crawl_status        = 'pending',
                        retry_count         = ?,
                        next_retry_at       = ?,
                        last_http_status    = ?,
                        last_failure_reason = ?,
                        last_failure_stage  = 'crawl'
                    WHERE url = ?
                    """,
                    (retry_count, next_retry, http_status, reason, url),
                )
                print(
                    f"[LinkQueue] crawl retry {retry_count}/{MAX_CRAWL_ATTEMPTS} "
                    f"scheduled at {next_retry} for {url}"
                )
            else:
                conn.execute(
                    """
                    UPDATE links
                    SET crawl_status        = 'failed',
                        retry_count         = ?,
                        next_retry_at       = NULL,
                        last_http_status    = ?,
                        last_failure_reason = ?,
                        last_failure_stage  = 'crawl'
                    WHERE url = ?
                    """,
                    (retry_count, http_status, reason, url),
                )
                print(f"[LinkQueue] crawl permanently failed for {url}: {reason}")

    def release_claimed(self, reason: str = "daemon_shutdown") -> int:
        """
        Reset all in-progress URLs back to pending.

        Called on daemon shutdown to ensure no URLs are permanently stuck
        in 'in_progress' state if the daemon was stopped mid-tick.

        Returns the number of rows released.
        """
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE links
                SET crawl_status        = 'pending',
                    claimed_at          = NULL,
                    last_failure_reason = ?,
                    last_failure_stage  = 'crawl'
                WHERE crawl_status = 'in_progress'
                """,
                (reason,),
            )
            crawl_released = conn.execute("SELECT changes()").fetchone()[0]

            conn.execute(
                """
                UPDATE links
                SET ingest_status       = 'pending',
                    last_failure_reason = ?,
                    last_failure_stage  = 'ingest'
                WHERE ingest_status = 'in_progress'
                """,
                (reason,),
            )
            ingest_released = conn.execute("SELECT changes()").fetchone()[0]

        total = crawl_released + ingest_released
        if total:
            print(
                f"[LinkQueue] release_claimed: released {crawl_released} crawl "
                f"+ {ingest_released} ingest rows (reason={reason})"
            )
        return total


    def mark_404_requeue(self, original_url: str, stripped_url: str) -> int:
        """
        Handle a 404 response by:
          1. Marking the original URL as 'skipped' with reason '404_stripped_requeued'
          2. Inserting the query-param-stripped URL as a fresh pending entry
             with parent_url pointing back to the original.

        Returns 1 if the stripped URL was newly inserted, 0 if it already existed.
        """
        now = _now_iso()
        with self._connect() as conn:
            # Mark original as skipped
            conn.execute(
                """
                UPDATE links
                SET crawl_status        = 'skipped',
                    last_failure_reason = '404_stripped_requeued',
                    last_http_status    = 404,
                    last_failure_stage  = 'crawl'
                WHERE url = ?
                """,
                (original_url,),
            )

            # Insert stripped URL as fresh entry
            try:
                conn.execute(
                    """
                    INSERT INTO links (
                        url, parent_url, content_kind,
                        source_type, source_value,
                        crawl_status, ingest_status,
                        retry_count, discovered_at
                    )
                    SELECT
                        ?,                  -- stripped_url
                        url,                -- parent_url = original
                        content_kind,
                        source_type,
                        source_value,
                        'pending',
                        'not_started',
                        0,                  -- fresh retry_count
                        ?                   -- now
                    FROM links WHERE url = ?
                    """,
                    (stripped_url, now, original_url),
                )
                print(
                    f"[LinkQueue] 404 requeue: '{original_url}' -> '{stripped_url}'"
                )
                return 1
            except sqlite3.IntegrityError:
                # Stripped URL already in queue
                print(
                    f"[LinkQueue] 404 requeue: stripped URL already exists: '{stripped_url}'"
                )
                return 0

    # ── Ingest claim / result ─────────────────────────────────────────────────

    def claim_pending_ingest(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Atomically claim up to `limit` rows ready for ingestion.

        Eligible rows:
          - ingest_status = 'pending'
          - crawl_status  = 'crawled'

        Sets ingest_status = 'in_progress'.
        Returns list of row dicts.
        """
        now = _now_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT * FROM links
                WHERE ingest_status = 'pending'
                  AND crawl_status  = 'crawled'
                ORDER BY crawled_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            if not rows:
                conn.execute("COMMIT")
                return []

            ids = [r["id"] for r in rows]
            conn.execute(
                f"""
                UPDATE links
                SET ingest_status = 'in_progress'
                WHERE id IN ({','.join('?' * len(ids))})
                """,
                ids,
            )
            conn.execute("COMMIT")

        return [self._row_to_dict(r) for r in rows]

    def mark_ingest_success(self, url: str) -> None:
        """Mark a URL as fully ingested into the vector store."""
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE links
                SET ingest_status       = 'stored',
                    ingested_at         = ?,
                    last_failure_reason = NULL,
                    last_failure_stage  = NULL
                WHERE url = ?
                """,
                (now, url),
            )

    def mark_ingest_failed(
        self,
        url: str,
        reason: str,
        retryable: bool = False,
    ) -> None:
        """
        Record an ingest failure.

        If retryable and under MAX_INGEST_ATTEMPTS:
          - keeps ingest_status = 'pending'
          - sets next_retry_at using exponential backoff

        Otherwise sets ingest_status = 'failed'.
        Note: crawl_status remains 'crawled' — the raw file is still on disk.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT retry_count FROM links WHERE url = ?", (url,)
            ).fetchone()

            if row is None:
                print(f"[LinkQueue] mark_ingest_failed: URL not found: {url}")
                return

            retry_count = row["retry_count"] + 1

            if retryable and retry_count < MAX_INGEST_ATTEMPTS:
                next_retry = _retry_at_iso(retry_count)
                conn.execute(
                    """
                    UPDATE links
                    SET ingest_status       = 'pending',
                        retry_count         = ?,
                        next_retry_at       = ?,
                        last_failure_reason = ?,
                        last_failure_stage  = 'ingest'
                    WHERE url = ?
                    """,
                    (retry_count, next_retry, reason, url),
                )
                print(
                    f"[LinkQueue] ingest retry {retry_count}/{MAX_INGEST_ATTEMPTS} "
                    f"scheduled at {next_retry} for {url}"
                )
            else:
                conn.execute(
                    """
                    UPDATE links
                    SET ingest_status       = 'failed',
                        retry_count         = ?,
                        next_retry_at       = NULL,
                        last_failure_reason = ?,
                        last_failure_stage  = 'ingest'
                    WHERE url = ?
                    """,
                    (retry_count, reason, url),
                )
                print(f"[LinkQueue] ingest permanently failed for {url}: {reason}")

    # ── Backpressure ──────────────────────────────────────────────────────────

    def get_raw_saved_count(self) -> int:
        """
        Count URLs that have been crawled but not yet ingested.
        Used by the heartbeat for backpressure: if this exceeds the configured
        threshold, crawling is paused until the ingest worker catches up.
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM links
                WHERE ingest_status IN ('pending', 'in_progress')
                  AND crawl_status  = 'crawled'
                """
            ).fetchone()
        return row["cnt"] if row else 0

    # ── Manual operations ─────────────────────────────────────────────────────

    def force_recrawl(self, url: str) -> None:
        """
        Reset a URL to be re-crawled from scratch.
        Clears all state: retry count, raw path, failure info, retry schedule.
        Does NOT delete the raw file from disk — caller is responsible.
        """
        with self._connect() as conn:
            conn.execute(
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
                WHERE url = ?
                """,
                (url,),
            )
            if conn.execute("SELECT changes()").fetchone()[0] == 0:
                print(f"[LinkQueue] force_recrawl: URL not found: {url}")
            else:
                print(f"[LinkQueue] force_recrawl: reset {url}")

    # ── Debug / stats ─────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """
        Return a summary dict of queue state counts.
        Useful for TUI display and heartbeat logging.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    crawl_status,
                    ingest_status,
                    COUNT(*) AS cnt
                FROM links
                GROUP BY crawl_status, ingest_status
                """
            ).fetchall()

        stats: Dict[str, Any] = {}
        for row in rows:
            key = f"crawl={row['crawl_status']} ingest={row['ingest_status']}"
            stats[key] = row["cnt"]
        return stats