"""
crawler.py

Crawl heartbeat: claims pending URLs from the queue, routes each to either
the file downloader or the crawl4ai page crawler, writes results to disk,
and updates the queue with success/failure state.

Used by: heartbeat.py
"""

import json
import hashlib
import asyncio
import aiohttp

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple, TYPE_CHECKING

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

from daemon.url_parser.downloader import download_file, is_downloadable_url
from daemon.url_parser.normalizer import strip_query_params

if TYPE_CHECKING:
    from daemon.database import LinkQueue


# ── Retryable HTTP status codes ───────────────────────────────────────────────
# 429 and 5xx are retryable. 4xx (except 429) are permanent failures.
_RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_raw_markdown(url: str, markdown: str, raw_dir: Path) -> str:
    """
    Write crawled markdown to disk as a JSON envelope.

    Path: <raw_dir>/<YYYY-MM-DD>/<url_hash>.json
    Envelope: { url, markdown, crawled_at, content_kind }

    Returns the absolute path string.
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_dir = raw_dir / date_str
    date_dir.mkdir(parents=True, exist_ok=True)

    dest = date_dir / f"{_url_hash(url)}.json"

    payload = {
        "url":          url,
        "markdown":     markdown,
        "crawled_at":   _now_iso(),
        "content_kind": "page",
    }

    with dest.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return str(dest)


def _distribute_urls(
    urls: List[str],
    browser_instances: int,
) -> List[Tuple[int, List[str]]]:
    """
    Split a URL list as evenly as possible across N browser instances.

    Returns a list of (instance_index, url_batch) pairs.
    Instances with no URLs are omitted.

    Example:
        _distribute_urls(["a","b","c","d","e"], 3)
        -> [(0, ["a","b"]), (1, ["c","d"]), (2, ["e"])]
    """
    if browser_instances < 1:
        browser_instances = 1

    batches: List[Tuple[int, List[str]]] = []
    total = len(urls)

    for i in range(browser_instances):
        # Slice: give each instance a roughly equal share
        start = (i * total) // browser_instances
        end   = ((i + 1) * total) // browser_instances
        batch = urls[start:end]
        if batch:
            batches.append((i, batch))

    return batches


async def _crawl_batch(
    instance_index: int,
    urls: List[str],
    browser_config: BrowserConfig,
    crawl_config: CrawlerRunConfig,
    max_concurrent_per_instance: int,
) -> List[Tuple[str, object]]:
    """
    Run one browser instance and crawl its assigned URL batch.
    Processes URLs in sub-batches of max_concurrent_per_instance.

    Returns list of (url, result_or_exception) pairs.
    """
    results: List[Tuple[str, object]] = []

    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.start()

    try:
        for i in range(0, len(urls), max_concurrent_per_instance):
            sub_batch = urls[i: i + max_concurrent_per_instance]

            tasks = [
                crawler.arun(
                    url=url,
                    config=crawl_config,
                    session_id=f"instance_{instance_index}_slot_{i + j}",
                )
                for j, url in enumerate(sub_batch)
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for url, result in zip(sub_batch, batch_results):
                results.append((url, result))

    finally:
        await crawler.close()

    return results


# ── Public API ────────────────────────────────────────────────────────────────

async def crawl_heartbeat(queue: "LinkQueue", config: object) -> None:
    """
    Single crawl heartbeat tick. Called by heartbeat.py on each interval.

    Steps:
      1. Backpressure check — skip crawling if ingest queue is too deep
      2. Claim pending URLs from the queue
      3. Route each URL: downloadable file -> downloader, page -> crawl4ai
      4. Write results to disk, update queue state
      5. Print summary

    Config attributes read:
        config.backpressure_threshold   int | None   — max raw_saved_count before pause
        config.crawl_batch_size         int          — URLs to claim per tick
        config.browser_instances        int          — parallel browser count
        config.max_concurrent_per_instance int       — concurrent tabs per browser
        config.allowed_extensions       List[str]    — for downloader routing
        config.raw_dir                  Path         — where to write markdown JSON
        config.files_dir                Path         — where downloader saves files
        config.request_timeout_seconds  int          — HTTP timeout for downloader
    """

    # ── 1. Backpressure ───────────────────────────────────────────────────────
    threshold = getattr(config, "backpressure_threshold", None)
    if threshold is not None:
        raw_saved_count = queue.get_raw_saved_count()
        if raw_saved_count > threshold:
            print(
                f"[crawler] Backpressure: {raw_saved_count} raw files pending ingest "
                f"(threshold={threshold}). Skipping crawl tick."
            )
            return

    # ── 2. Claim URLs ─────────────────────────────────────────────────────────
    batch_size = getattr(config, "crawl_batch_size", 10)
    rows = queue.claim_pending_crawl(limit=batch_size)

    if not rows:
        print("[crawler] No pending URLs to crawl.")
        return

    print(f"[crawler] Claimed {len(rows)} URLs for crawl tick")

    # ── 3. Route: split into files vs pages ───────────────────────────────────
    allowed_extensions = getattr(config, "allowed_extensions", None)
    file_rows  = [r for r in rows if is_downloadable_url(r["url"], allowed_extensions)]
    page_rows  = [r for r in rows if not is_downloadable_url(r["url"], allowed_extensions)]

    print(f"[crawler] Routing: {len(page_rows)} pages, {len(file_rows)} files")

    # Counters for summary
    crawled_count  = 0
    failed_count   = 0
    skipped_count  = 0
    file_count     = 0

    # ── 4a. Handle file downloads ─────────────────────────────────────────────
    if file_rows:
        files_dir   = Path(getattr(config, "files_dir", "data/files"))
        timeout_sec = getattr(config, "request_timeout_seconds", 60)
        skipped_counter = [0]

        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(
            connector=connector,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as session:
            download_tasks = [
                download_file(
                    url=r["url"],
                    destination_dir=files_dir,
                    allowed_extensions=allowed_extensions,
                    session=session,
                    request_timeout_seconds=timeout_sec,
                    skipped_counter=skipped_counter,
                )
                for r in file_rows
            ]
            download_results = await asyncio.gather(*download_tasks, return_exceptions=True)

        for row, result in zip(file_rows, download_results):
            url = row["url"]
            if isinstance(result, Exception):
                print(f"[crawler] Download exception for {url}: {result}")
                queue.mark_crawl_failed(url, reason=str(result), retryable=True)
                failed_count += 1
            elif result is None:
                # Skipped by downloader (type not allowed or HTTP error)
                queue.mark_crawl_failed(
                    url,
                    reason="downloader_skipped",
                    retryable=False,
                )
                skipped_count += 1
            else:
                queue.mark_crawl_success(url, raw_path=result, content_kind="file")
                file_count += 1

        skipped_count += skipped_counter[0]

    # ── 4b. Handle page crawls ────────────────────────────────────────────────
    if page_rows:
        page_urls = [r["url"] for r in page_rows]

        browser_instances          = getattr(config, "browser_instances", 1)
        max_concurrent_per_instance = getattr(config, "max_concurrent_per_instance", 3)

        browser_config = BrowserConfig(
            headless=True,
            verbose=False,
            extra_args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        crawl_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

        # Distribute URLs across browser instances
        distribution = _distribute_urls(page_urls, browser_instances)

        # Run all browser instances concurrently
        instance_tasks = [
            _crawl_batch(
                instance_index=idx,
                urls=batch,
                browser_config=browser_config,
                crawl_config=crawl_config,
                max_concurrent_per_instance=max_concurrent_per_instance,
            )
            for idx, batch in distribution
        ]
        instance_results = await asyncio.gather(*instance_tasks, return_exceptions=True)

        # Flatten results from all instances into a single list
        all_page_results: List[Tuple[str, object]] = []
        for r in instance_results:
            if isinstance(r, Exception):
                print(f"[crawler] Browser instance error: {r}")
            elif isinstance(r, list):
                all_page_results.extend(r)

        # Build a lookup from url -> crawl4ai result
        result_map = {url: result for url, result in all_page_results}

        raw_dir = Path(getattr(config, "raw_dir", "data/raw"))

        for row in page_rows:
            url    = row["url"]
            result = result_map.get(url)

            if result is None:
                # URL was in a batch that failed at the instance level
                queue.mark_crawl_failed(url, reason="instance_error", retryable=True)
                failed_count += 1
                continue

            if isinstance(result, Exception):
                queue.mark_crawl_failed(url, reason=str(result), retryable=True)
                failed_count += 1
                continue

            # crawl4ai result object
            http_status = getattr(result, "status_code", None)

            if not result.success:
                # ── 404: strip query params and re-queue ──────────────────
                if http_status == 404:
                    stripped = strip_query_params(url)
                    if stripped != url:
                        queue.mark_404_requeue(original_url=url, stripped_url=stripped)
                        print(f"[crawler] 404 requeue: {url} -> {stripped}")
                    else:
                        # No query params to strip — permanent failure
                        queue.mark_crawl_failed(
                            url,
                            reason="404_no_query_params",
                            http_status=404,
                            retryable=False,
                        )
                    failed_count += 1
                    continue

                # ── Retryable HTTP errors ─────────────────────────────────
                if http_status in _RETRYABLE_HTTP_STATUSES:
                    queue.mark_crawl_failed(
                        url,
                        reason=f"http_{http_status}",
                        http_status=http_status,
                        retryable=True,
                    )
                    failed_count += 1
                    continue

                # ── Permanent failure ─────────────────────────────────────
                reason = getattr(result, "error_message", None) or f"http_{http_status}"
                queue.mark_crawl_failed(
                    url,
                    reason=reason,
                    http_status=http_status,
                    retryable=False,
                )
                failed_count += 1
                continue

            # ── Success: extract markdown ─────────────────────────────────
            markdown = None
            try:
                markdown = str(result.markdown) if getattr(result, "markdown", None) else None
            except Exception:
                markdown = None

            if not markdown:
                markdown = (
                    getattr(result, "extracted_content", None)
                    or getattr(result, "html", None)
                    or ""
                )

            raw_path = _write_raw_markdown(url, markdown, raw_dir)
            queue.mark_crawl_success(url, raw_path=raw_path, content_kind="page")
            crawled_count += 1

    # ── 5. Summary ────────────────────────────────────────────────────────────
    print(
        f"[crawler] Tick complete — "
        f"crawled={crawled_count}, "
        f"files={file_count}, "
        f"failed={failed_count}, "
        f"skipped={skipped_count}"
    )