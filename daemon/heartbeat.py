"""
heartbeat.py

Crawler daemon entry point. Reads crawler.yaml, initialises all shared
objects (LinkQueue, VectorDatabase), then runs two independent async loops:

    crawl loop  — calls crawl_heartbeat()  every crawl_interval_sec
    ingest loop — calls ingest_heartbeat() every ingest_interval_sec

Both loops run concurrently via asyncio.gather. Each loop is independent:
a slow crawl tick does not delay ingest, and vice versa.

Lifecycle:
    - Started by the UI (subprocess or asyncio task)
    - Handles SIGINT / SIGTERM for clean shutdown
    - Optionally keeps running after UI exits (config: keep_alive_on_ui_exit)
    - On restart, picks up where it left off (queue state is persisted in SQLite)

Usage:
    python -m daemon.heartbeat --config config/crawler.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import time

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.config_loader import CrawlerConfig, load
from daemon.logger import RichLogManager

logger = RichLogManager().get_logger(__name__)


def _load_crawler_config(path: Path) -> CrawlerConfig:
    """
    Load crawler.yaml and construct a CrawlerConfig.

    Unknown keys are silently ignored so adding new YAML fields
    doesn't break older daemon versions.
    """
    raw = load(path)

    crawler_section: dict[str, Any] = raw.get("crawler", raw)

    def _path(key: str, default: Path) -> Path:
        return Path(crawler_section[key]) if key in crawler_section else default

    def _get(key: str, default: Any) -> Any:
        return crawler_section.get(key, default)

    return CrawlerConfig(
        db_path                     = _path("db_path",    CrawlerConfig.db_path),
        raw_dir                     = _path("raw_dir",    CrawlerConfig.raw_dir),
        files_dir                   = _path("files_dir",  CrawlerConfig.files_dir),
        chroma_db_path              = _path("chroma_db_path", CrawlerConfig.chroma_db_path),
        ollama_base_url             = _get("ollama_base_url",             CrawlerConfig.ollama_base_url),
        embedding_model             = _get("embedding_model",             CrawlerConfig.embedding_model),
        llm_model                   = _get("llm_model",                   CrawlerConfig.llm_model),
        crawl_interval_sec          = float(_get("crawl_interval_sec",    CrawlerConfig.crawl_interval_sec)),
        crawl_batch_size            = int(_get("crawl_batch_size",        CrawlerConfig.crawl_batch_size)),
        browser_instances           = int(_get("browser_instances",       CrawlerConfig.browser_instances)),
        max_concurrent_per_instance = int(_get("max_concurrent_per_instance", CrawlerConfig.max_concurrent_per_instance)),
        request_timeout_seconds     = int(_get("request_timeout_seconds", CrawlerConfig.request_timeout_seconds)),
        ingest_interval_sec         = float(_get("ingest_interval_sec",   CrawlerConfig.ingest_interval_sec)),
        ingest_batch_size           = int(_get("ingest_batch_size",       CrawlerConfig.ingest_batch_size)),
        allowed_extensions          = list(_get("allowed_extensions", [".pdf", ".txt", ".md", ".html", ".htm", ".csv", ".json", ".xml", ".docx", ".xlsx"])),
        backpressure_threshold      = _get("backpressure_threshold",      None),
        keep_alive_on_ui_exit       = bool(_get("keep_alive_on_ui_exit",  CrawlerConfig.keep_alive_on_ui_exit)),
    )


# ── Heartbeat loops ───────────────────────────────────────────────────────────

async def _crawl_loop(queue: Any, config: CrawlerConfig, stop: asyncio.Event) -> None:
    """
    Runs crawl_heartbeat() every crawl_interval_sec until stop is set.
    Ticks are non-overlapping: if a tick takes longer than the interval,
    the next tick starts immediately after (no backlog of queued ticks).
    """
    from experimental.crawler.crawler import crawl_heartbeat

    logger.info("[crawl-loop] Starting — interval=%ss", config.crawl_interval_sec)

    while not stop.is_set():
        tick_start = time.monotonic()

        try:
            await crawl_heartbeat(queue, config)
        except Exception:
            logger.exception("[crawl-loop] Unhandled exception in tick")

        elapsed   = time.monotonic() - tick_start
        remaining = config.crawl_interval_sec - elapsed

        if remaining > 0:
            try:
                await asyncio.wait_for(stop.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                pass  # Normal — interval elapsed, run next tick

    logger.info("[crawl-loop] Stopped")


async def _ingest_loop(queue: Any, vector_db: Any, config: CrawlerConfig, stop: asyncio.Event) -> None:
    """
    Runs ingest_heartbeat() every ingest_interval_sec until stop is set.
    Same non-overlapping tick model as _crawl_loop.
    """
    from daemon.ingest import ingest_heartbeat

    logger.info("[ingest-loop] Starting — interval=%ss", config.ingest_interval_sec)

    while not stop.is_set():
        tick_start = time.monotonic()

        try:
            await ingest_heartbeat(queue, vector_db, config)
        except Exception:
            logger.exception("[ingest-loop] Unhandled exception in tick")

        elapsed   = time.monotonic() - tick_start
        remaining = config.ingest_interval_sec - elapsed

        if remaining > 0:
            try:
                await asyncio.wait_for(stop.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                pass

    logger.info("[ingest-loop] Stopped")


# ── Shutdown ──────────────────────────────────────────────────────────────────

def _install_signal_handlers(stop: asyncio.Event, loop: asyncio.AbstractEventLoop) -> None:
    """
    Register SIGINT and SIGTERM handlers that set the stop event.
    Safe to call from the main thread only.
    """
    def _handle(signum: int) -> None:
        sig_name = signal.Signals(signum).name
        logger.info("[heartbeat] Received %s, shutting down...", sig_name)
        loop.call_soon_threadsafe(stop.set)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle, sig)
        except (NotImplementedError, RuntimeError):
            # Windows does not support add_signal_handler on the event loop.
            # Fall back to the standard signal module.
            signal.signal(sig, lambda s, f: loop.call_soon_threadsafe(stop.set))


# ── Entry point ───────────────────────────────────────────────────────────────

async def run(config_path: Path) -> None:
    """
    Full daemon lifecycle:
      1. Load config
      2. Initialise LinkQueue and VectorDatabase
      3. Start crawl and ingest loops concurrently
      4. Wait for stop signal
      5. Flush and close
    """
    from daemon.database import LinkQueue, VectorDatabase

    config = _load_crawler_config(config_path)

    logger.info("[heartbeat] Loaded config from %s", config_path)
    logger.info("[heartbeat] db_path=%s", config.db_path)
    logger.info(
        "[heartbeat] crawl_interval=%ss  ingest_interval=%ss",
        config.crawl_interval_sec,
        config.ingest_interval_sec,
    )
    logger.info("[heartbeat] keep_alive_on_ui_exit=%s", config.keep_alive_on_ui_exit)

    # ── Ensure data directories exist ─────────────────────────────────────────
    for directory in (config.raw_dir, config.files_dir, config.chroma_db_path):
        Path(directory).mkdir(parents=True, exist_ok=True)

    # ── Initialise shared objects ─────────────────────────────────────────────
    logger.info("[heartbeat] Initialising LinkQueue...")
    queue = LinkQueue(db_path=config.db_path)

    logger.info("[heartbeat] Initialising VectorDatabase...")
    vector_db = VectorDatabase(
        base_url=config.ollama_base_url,
        embedding_model=config.embedding_model,
        chroma_db_path=str(config.chroma_db_path),
    )

    # ── Stop event shared between both loops ──────────────────────────────────
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    _install_signal_handlers(stop, loop)

    logger.info("[heartbeat] Daemon running. Press Ctrl+C to stop.")

    # ── Run both loops concurrently ───────────────────────────────────────────
    try:
        await asyncio.gather(
            _crawl_loop(queue, config, stop),
            _ingest_loop(queue, vector_db, config, stop),
        )
    finally:
        logger.info("[heartbeat] Shutting down — flushing queue...")
        # Release any URLs that were claimed but not completed
        # (daemon crashed mid-tick or was stopped cleanly)
        queue.release_claimed(reason="daemon_shutdown")
        logger.info("[heartbeat] Shutdown complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawler daemon")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/crawler.yaml"),
        help="Path to crawler.yaml (default: config/crawler.yaml)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run(args.config))
    except KeyboardInterrupt:
        pass  # Already handled by signal handler — suppress traceback


if __name__ == "__main__":
    main()