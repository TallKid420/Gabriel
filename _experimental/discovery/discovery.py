import re
import asyncio
import aiohttp

from xml.etree import ElementTree
from urllib.parse import urlparse
from typing import List, TYPE_CHECKING

from ddgs import DDGS
from daemon.crawler.normalizer import normalize_url, is_same_root_domain

if TYPE_CHECKING:
    from daemon.database import LinkQueue

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# Semaphore for sitemap child fetches — prevents opening hundreds of
# simultaneous connections on large sitemap indexes (e.g. IRS)
_SITEMAP_CONCURRENCY = 20


# ─── Internal HTTP helpers ────────────────────────────────────────────────────

async def _fetch_text(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.text()
    except Exception:
        pass
    return None


async def _fetch_bytes(session: aiohttp.ClientSession, url: str) -> bytes | None:
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.read()
    except Exception:
        pass
    return None


# ─── Internal URL helpers ─────────────────────────────────────────────────────

def _matches_exclude_patterns(url: str, patterns: List[str]) -> bool:
    """Return True if the URL matches any of the configured exclude patterns."""
    for pattern in patterns:
        try:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        except re.error:
            print(f"[discovery] Invalid exclude pattern '{pattern}', skipping")
    return False


def _get_base_origin(url: str) -> str:
    """
    Extract scheme + host only from a URL.
    e.g. https://www.irs.gov/some/path -> https://www.irs.gov
    Needed so robots.txt and sitemap fallback paths are constructed correctly.
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


# ─── Sitemap fetching ─────────────────────────────────────────────────────────

async def _get_sitemap_candidates(session: aiohttp.ClientSession, base_origin: str) -> List[str]:
    """
    Build a deduplicated list of candidate sitemap URLs for a given origin.
    Checks robots.txt first, then falls back to common sitemap paths.
    """
    candidates = []

    robots = await _fetch_text(session, f"{base_origin}/robots.txt")
    if robots:
        for line in robots.splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                candidates.append(sitemap_url)
                print(f"[discovery] Found sitemap in robots.txt: {sitemap_url}")

    # Always try common fallback paths — deduplicated below
    candidates.extend([
        f"{base_origin}/sitemap.xml",
        f"{base_origin}/sitemap_index.xml",
        f"{base_origin}/sitemap-index.xml",
        f"{base_origin}/sitemapindex.xml",
    ])

    return list(dict.fromkeys(candidates))


async def _parse_sitemap(
    session: aiohttp.ClientSession,
    sitemap_url: str,
    visited: set,
    semaphore: asyncio.Semaphore,
    reference_url: str,
    exclude_patterns: List[str],
    queue: "LinkQueue",
    source_value: str,
) -> int:
    """
    Recursively parse a sitemap or sitemap index.
    Streams discovered URLs directly into the queue as they are found.
    Returns count of new URLs added to the queue.
    """
    if sitemap_url in visited:
        return 0
    visited.add(sitemap_url)

    async with semaphore:
        xml_data = await _fetch_bytes(session, sitemap_url)

    if not xml_data:
        print(f"[discovery] Could not fetch sitemap: {sitemap_url}")
        return 0

    try:
        root = ElementTree.fromstring(xml_data)
    except ElementTree.ParseError as e:
        print(f"[discovery] XML parse error for {sitemap_url}: {e}")
        return 0

    namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    added = 0

    # urlset: leaf sitemap containing actual page URLs
    if root.tag.endswith("urlset"):
        raw_urls = [
            loc.text.strip()
            for loc in root.findall(".//ns:loc", namespace)
            if loc.text and loc.text.strip()
        ]
        print(f"[discovery] Sitemap {sitemap_url}: found {len(raw_urls)} raw URLs")

        for raw_url in raw_urls:
            # Domain filter: only keep URLs on the same root domain as the input
            if not is_same_root_domain(raw_url, reference_url):
                continue

            # Exclude pattern filter
            if _matches_exclude_patterns(raw_url, exclude_patterns):
                continue

            normalized = normalize_url(raw_url)
            if not normalized:
                continue

            # Stream directly into SQLite — deduplication handled inside add_urls
            n = queue.add_urls(
                [normalized],
                source_type="sitemap",
                source_value=source_value
            )
            added += n

        return added

    # sitemapindex: contains references to child sitemaps
    if root.tag.endswith("sitemapindex"):
        child_urls = [
            loc.text.strip()
            for loc in root.findall(".//ns:loc", namespace)
            if loc.text and loc.text.strip()
        ]
        print(f"[discovery] Sitemap index {sitemap_url}: found {len(child_urls)} child sitemaps")

        tasks = [
            _parse_sitemap(
                session,
                child,
                visited,
                semaphore,
                reference_url,
                exclude_patterns,
                queue,
                source_value,
            )
            for child in child_urls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                print(f"[discovery] Error parsing child sitemap: {r}")
            elif isinstance(r, int):
                added += r

        return added

    print(f"[discovery] Unrecognised sitemap root tag '{root.tag}' at {sitemap_url}")
    return 0


# ─── Public API ───────────────────────────────────────────────────────────────

def discover_from_query(
    query: str,
    queue: "LinkQueue",
    max_results: int = 10,
    exclude_patterns: List[str] | None = None,
) -> int:
    """
    Run a DDGS search, normalize results, and add them to the queue.
    Returns count of new URLs added.

    Args:
        query:            Search query string.
        queue:            LinkQueue instance for deduplication and storage.
        max_results:      Maximum number of DDGS results to request.
        exclude_patterns: URL patterns to drop (from config).
    """
    if not query.strip():
        raise ValueError("Query must not be empty.")

    exclude_patterns = exclude_patterns or []
    raw_urls = []

    with DDGS() as ddgs:
        for result in ddgs.text(query, max_results=max_results):
            href = result.get("href")
            if href:
                raw_urls.append(href)

    print(f"[discovery] DDGS returned {len(raw_urls)} raw URLs for query '{query}'")

    valid = []
    for raw in raw_urls:
        if _matches_exclude_patterns(raw, exclude_patterns):
            continue
        normalized = normalize_url(raw)
        if normalized:
            valid.append(normalized)

    added = queue.add_urls(valid, source_type="query", source_value=query)
    print(f"[discovery] discover_from_query: added={added}, skipped={len(valid) - added}")
    return added


async def expand_sitemaps(
    urls: List[str],
    queue: "LinkQueue",
    exclude_patterns: List[str] | None = None,
    sitemap_concurrency: int = _SITEMAP_CONCURRENCY,
    request_timeout_seconds: int = 15,
) -> int:
    """
    For each input URL, derive the base origin, fetch and parse all sitemaps
    recursively, and stream discovered URLs into the queue.

    Only URLs sharing the same root domain as the input URL are kept.
    Deduplication is handled inside queue.add_urls().

    Returns total count of new URLs added across all input URLs.
    """
    exclude_patterns = exclude_patterns or []
    total_added = 0

    timeout = aiohttp.ClientTimeout(total=request_timeout_seconds)
    connector = aiohttp.TCPConnector(limit=100, ssl=False)
    semaphore = asyncio.Semaphore(sitemap_concurrency)

    async with aiohttp.ClientSession(
        connector=connector,
        headers=HEADERS,
        timeout=timeout,
    ) as session:
        for input_url in urls:
            base_origin = _get_base_origin(input_url)
            if not base_origin or "://" not in base_origin:
                print(f"[discovery] Could not derive base origin from '{input_url}', skipping")
                continue

            print(f"[discovery] Expanding sitemaps for: {base_origin}")
            candidates = await _get_sitemap_candidates(session, base_origin)
            print(f"[discovery] {len(candidates)} sitemap candidates for {base_origin}")

            visited: set = set()
            tasks = [
                _parse_sitemap(
                    session,
                    candidate,
                    visited,
                    semaphore,
                    reference_url=input_url,
                    exclude_patterns=exclude_patterns,
                    queue=queue,
                    source_value=input_url,
                )
                for candidate in candidates
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, Exception):
                    print(f"[discovery] Sitemap expansion error for {base_origin}: {r}")
                elif isinstance(r, int):
                    total_added += r

            print(f"[discovery] {base_origin}: {total_added} new URLs added so far")

    print(f"[discovery] expand_sitemaps complete: {total_added} total new URLs added")
    return total_added


def discover_from_urls(
    urls: List[str],
    queue: "LinkQueue",
    deep: bool = False,
    exclude_patterns: List[str] | None = None,
    sitemap_concurrency: int = _SITEMAP_CONCURRENCY,
    request_timeout_seconds: int = 15,
) -> int:
    """
    Add a list of explicit URLs to the queue.
    If deep=True, expands each URL's sitemap and adds all discovered URLs.
    If deep=False, normalizes and adds only the provided URLs.

    Returns count of new URLs added.
    """
    exclude_patterns = exclude_patterns or []

    if not deep:
        valid = []
        for raw in urls:
            if _matches_exclude_patterns(raw, exclude_patterns):
                continue
            normalized = normalize_url(raw)
            if normalized:
                valid.append(normalized)
        added = queue.add_urls(valid, source_type="direct_url", source_value=",".join(urls))
        print(f"[discovery] discover_from_urls (shallow): added={added}, skipped={len(valid) - added}")
        return added

    # Deep: run sitemap expansion in an event loop
    # If already inside a running loop (e.g. daemon heartbeat), use await instead
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Caller is async — they should await expand_sitemaps directly.
        # This path should not be hit in normal daemon operation.
        raise RuntimeError(
            "discover_from_urls with deep=True called from a running event loop. "
            "Await expand_sitemaps() directly instead."
        )

    return asyncio.run(
        expand_sitemaps(
            urls,
            queue,
            exclude_patterns=exclude_patterns,
            sitemap_concurrency=sitemap_concurrency,
            request_timeout_seconds=request_timeout_seconds,
        )
    )