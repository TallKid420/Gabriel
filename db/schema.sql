-- ============================================================================
-- Gabriel — unified PostgreSQL + pgvector schema
-- ============================================================================
-- This file is the single source of truth for every application table.
--
-- It is applied by ``python -m db.migrate``, which:
--   1. CREATE EXTENSION IF NOT EXISTS vector;
--   2. substitutes the ``__EMBEDDING_DIM__`` placeholder below with the
--      configured EMBEDDING_DIM (see db/config.py), and
--   3. executes this script.
--
-- LangGraph chat checkpoints live in their own tables created by
-- ``PostgresSaver.setup()`` (see db/checkpointer.py) — not here.
--
-- Timestamp columns that the SQLite implementation compared lexicographically
-- (e.g. next_retry_at, discovered_at) are kept as TEXT holding ISO-8601 UTC
-- strings so the exact ordering/expiry semantics are preserved.
-- ============================================================================


-- ── Chat sessions ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    seq        BIGSERIAL,
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    agent_name TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_seq ON sessions (seq);


-- ── Chat messages ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id         BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    position   INTEGER NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, position)
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, position);


-- ── Agents ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agents (
    agent_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    updated_at TEXT NOT NULL
);


-- ── Per-agent tool enablement ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_tools (
    agent_id   TEXT NOT NULL,
    tool_id    TEXT NOT NULL,
    enabled    BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (agent_id, tool_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_tools_agent ON agent_tools (agent_id);


-- ── Crawler link queue ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS links (
    id                  BIGSERIAL PRIMARY KEY,
    url                 TEXT NOT NULL UNIQUE,
    parent_url          TEXT,
    content_kind        TEXT NOT NULL DEFAULT 'page',
    source_type         TEXT NOT NULL,
    source_value        TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    crawl_status        TEXT NOT NULL DEFAULT 'pending',
    ingest_status       TEXT NOT NULL DEFAULT 'not_started',
    discovered_at       TEXT NOT NULL,
    claimed_at          TEXT,
    crawled_at          TEXT,
    ingested_at         TEXT,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    next_retry_at       TEXT,
    last_http_status    INTEGER,
    last_failure_reason TEXT,
    last_failure_stage  TEXT,
    raw_path            TEXT
);

CREATE INDEX IF NOT EXISTS idx_links_crawl_status  ON links (crawl_status);
CREATE INDEX IF NOT EXISTS idx_links_ingest_status ON links (ingest_status);
CREATE INDEX IF NOT EXISTS idx_links_next_retry_at ON links (next_retry_at);


-- ── Vector knowledge base ───────────────────────────────────────────────────
-- Replaces the former ChromaDB ``agent_collection``. One row per stored chunk.
CREATE TABLE IF NOT EXISTS documents (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url        TEXT,
    content    TEXT NOT NULL,
    metadata   JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding  vector(__EMBEDDING_DIM__),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_url ON documents (url);

-- Approximate nearest-neighbour index using cosine distance to match the
-- semantics of the previous Chroma/embedding setup.
CREATE INDEX IF NOT EXISTS idx_documents_embedding
    ON documents USING hnsw (embedding vector_cosine_ops);
