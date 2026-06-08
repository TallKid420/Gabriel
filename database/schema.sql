CREATE TABLE IF NOT EXISTS links (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE INDEX IF NOT EXISTS idx_links_crawl_status   ON links (crawl_status);
CREATE INDEX IF NOT EXISTS idx_links_ingest_status  ON links (ingest_status);
CREATE INDEX IF NOT EXISTS idx_links_next_retry_at  ON links (next_retry_at);