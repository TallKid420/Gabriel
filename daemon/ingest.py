"""
ingest.py

Ingest heartbeat: claims crawled items from the queue, loads their raw files,
routes to the appropriate processor (page markdown or file chunker), stores
results in the vector database, and updates queue state.

Used by: heartbeat.py
"""

import json
import asyncio

from daemon.logger import RichLogManager

from docling.document_converter import DocumentConverter
from daemon.document import DocumentNormalizer

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from daemon.database import LinkQueue, VectorDatabase

logger = RichLogManager().get_logger(__name__)
normalizer = DocumentNormalizer

# ── Constants ─────────────────────────────────────────────────────────────────

INGEST_BATCH_SIZE: int = 10  # Default if not set in config


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_raw_page(raw_path: str) -> dict:
    """
    Load a raw JSON envelope written by crawler._write_raw_markdown.

    Expected shape:
        { url, markdown, crawled_at, content_kind }

    Raises:
        FileNotFoundError  — raw_path does not exist
        json.JSONDecodeError — file is not valid JSON
        KeyError           — envelope is missing required fields
    """
    path = Path(raw_path)
    if not path.exists():
        raise FileNotFoundError(f"Raw file not found: {raw_path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Validate required fields so ingest.py fails loudly rather than
    # silently ingesting empty/malformed documents
    for field in ("url", "markdown", "content_kind"):
        if field not in data:
            raise KeyError(f"Raw envelope missing field '{field}' in {raw_path}")

    return data


async def _ingest_page(url: str, markdown: str, vector_db: "VectorDatabase") -> None:
    """
    Pass a crawled page's markdown to the vector database for chunking,
    embedding, and storage.

    Raises on failure — caller handles and marks queue accordingly.
    """
    await vector_db.process_and_store_document(url, markdown)

async def _ingest_file(url: str, raw_path: str, vector_db: "VectorDatabase") -> None:
    """Process a single document and return metadata"""

    path = Path(raw_path)
    markdown: str

    # Try docling autodetect first
    try:
        markdown = normalizer.docling_normalizer(path=path)

    except Exception as e:
        logger.error(f"Docling Error; Moving to backup: {e}")
        
        markdown = normalizer.normalize_document(path=path)

    # Save output
    await vector_db.process_and_store_document(url, markdown)


# ── Public API ────────────────────────────────────────────────────────────────

async def ingest_heartbeat(
    queue: "LinkQueue",
    vector_db: "VectorDatabase",
    config: object,
) -> None:
    """
    Single ingest heartbeat tick. Called by heartbeat.py on each interval.

    Steps:
      1. Claim up to ingest_batch_size items where ingest_status = 'pending'
      2. If none: return early
      3. For each item:
           - load raw file from raw_path
           - route by content_kind: 'page' -> vector_db, 'file' -> chunker stub
           - on success: queue.mark_ingest_success(url)
           - on failure: queue.mark_ingest_failed(url, reason, retryable)
      4. Print summary

    Config attributes read:
        config.ingest_batch_size   int   — items to claim per tick
    """

    # ── 1. Claim pending ingest items ─────────────────────────────────────────
    batch_size = getattr(config, "ingest_batch_size", INGEST_BATCH_SIZE)
    rows = queue.claim_pending_ingest(limit=batch_size)

    if not rows:
        logger.info("[ingest] No pending items to ingest.")
        return

    logger.info(f"[ingest] Claimed {len(rows)} items for ingest tick")

    # ── 2. Process each item ──────────────────────────────────────────────────
    ingested_count = 0
    failed_count   = 0

    for row in rows:
        url          = row["url"]
        raw_path     = row.get("raw_path")
        content_kind = row.get("content_kind", "page")

        # ── Guard: raw_path must exist ────────────────────────────────────
        if not raw_path:
            queue.mark_ingest_failed(
                url,
                reason="missing_raw_path",
                retryable=False,
            )
            logger.critical(f"[ingest] No raw_path for {url}, marking permanent failure")
            failed_count += 1
            continue

        # ── Load raw file ─────────────────────────────────────────────────
        try:
            envelope = _load_raw_page(raw_path)
        except FileNotFoundError:
            # File was deleted or never written — not retryable, needs recrawl
            queue.mark_ingest_failed(
                url,
                reason="raw_file_missing",
                retryable=False,
            )
            logger.exception(f"[ingest] Raw file missing for {url}: {raw_path}")
            failed_count += 1
            continue
        except (json.JSONDecodeError, KeyError) as e:
            # Corrupt or malformed envelope — not retryable
            queue.mark_ingest_failed(
                url,
                reason=f"raw_file_corrupt: {e}",
                retryable=False,
            )
            logger.exception(f"[ingest] Corrupt raw file for {url}: {e}")
            failed_count += 1
            continue

        # ── Route by content_kind ─────────────────────────────────────────
        try:
            if content_kind == "page":
                markdown = envelope.get("markdown", "")

                if not markdown.strip():
                    # Empty markdown — not retryable, nothing to embed
                    queue.mark_ingest_failed(
                        url,
                        reason="empty_markdown",
                        retryable=False,
                    )
                    logger.warning(f"[ingest] Empty markdown for {url}, skipping")
                    failed_count += 1
                    continue

                print("1")
                await _ingest_page(url, markdown, vector_db)
                print("1 done")

            elif content_kind == "file":
                print("2")
                await _ingest_file(url, raw_path, vector_db)
                print("2 done")

            else:
                # Unknown content_kind — schema violation, not retryable
                queue.mark_ingest_failed(
                    url,
                    reason=f"unknown_content_kind: {content_kind}",
                    retryable=False,
                )
                logger.warning(f"[ingest] Unknown content_kind '{content_kind}' for {url}")
                failed_count += 1
                continue

        except NotImplementedError as e:
            # File ingestion stub — not retryable until implemented
            queue.mark_ingest_failed(url, reason=str(e), retryable=False)
            logger.warning(f"[ingest] Not implemented for {url}: {e}")
            failed_count += 1
            continue

        except asyncio.TimeoutError:
            # Embedding/LLM call timed out — retryable
            queue.mark_ingest_failed(
                url,
                reason="timeout_during_ingest",
                retryable=True,
            )
            logger.warning(f"[ingest] Timeout ingesting {url}, will retry")
            failed_count += 1
            continue
        
        except ConnectionError as e:
            # Network error during embedding/LLM call — retryable
            queue.mark_ingest_failed(
                url,
                reason=f"connection_error_during_ingest: {e}",
                retryable=True,
            )
            logger.warning(f"[ingest] Connection error ingesting {url}: {e}, will retry")
            failed_count += 1
            continue

        except Exception as e:
            # Catch-all: connection errors, OOM, unexpected LLM failures
            # Treat as retryable — we don't know the cause yet
            queue.mark_ingest_failed(
                url,
                reason=f"unexpected: {type(e).__name__}: {e}",
                retryable=True,
            )
            logger.exception(f"[ingest] Unexpected error ingesting {url}: {e}")
            failed_count += 1
            continue

        # ── Success ───────────────────────────────────────────────────────
        queue.mark_ingest_success(url)
        ingested_count += 1
        logger.info(f"[ingest] Ingested: {url}")

    # ── 3. Summary ────────────────────────────────────────────────────────────
    logger.info(
        f"[ingest] Tick complete — "
        f"ingested={ingested_count}, "
        f"failed={failed_count}"
    )