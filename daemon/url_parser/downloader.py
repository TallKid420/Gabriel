"""
downloader.py

Inputs:  url, destination_dir, allowed_extensions
Outputs: local file path (str), or None if skipped/failed

Rules:
- detect file type from Content-Type header first, URL extension as fallback
- if extension not in allowed_extensions: return None (silent skip)
- stream download in chunks to avoid loading full file into memory
- save to: <destination_dir>/<YYYY-MM-DD>/<url_hash>.<ext>
- return local path on success, None on skip or failure

Used by: crawler.py
"""

import hashlib
import aiohttp
import asyncio

from datetime import datetime, timezone
from pathlib import Path
from typing import List
from urllib.parse import urlparse


# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_ALLOWED_EXTENSIONS: List[str] = [
    ".pdf", ".txt", ".md", ".html", ".htm",
    ".csv", ".json", ".xml", ".docx", ".xlsx",
]

# Chunk size for streaming download (64 KB)
_STREAM_CHUNK_BYTES = 64 * 1024

# Fallback extension when neither Content-Type nor URL gives us one
_FALLBACK_EXT = ".bin"

# Maps common Content-Type values to file extensions.
# mimetypes.guess_extension() exists but returns inconsistent results
# across platforms (.jpe vs .jpeg, etc.) so we maintain our own short list
# for the types we actually care about.
_CONTENT_TYPE_MAP: dict[str, str] = {
    "application/pdf":                                                  ".pdf",
    "text/plain":                                                       ".txt",
    "text/markdown":                                                    ".md",
    "text/html":                                                        ".html",
    "text/csv":                                                         ".csv",
    "application/json":                                                 ".json",
    "application/xml":                                                  ".xml",
    "text/xml":                                                         ".xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":       ".xlsx",
    "application/msword":                                               ".doc",
    "application/vnd.ms-excel":                                        ".xls",
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _url_hash(url: str) -> str:
    """Short SHA-256 hex digest of the URL — used as the filename stem."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _ext_from_content_type(content_type: str) -> str | None:
    """
    Extract a normalised file extension from a Content-Type header value.
    Strips parameters (e.g. '; charset=utf-8') before lookup.
    Returns None if the type is not in our map.
    """
    if not content_type:
        return None
    mime = content_type.split(";")[0].strip().lower()
    return _CONTENT_TYPE_MAP.get(mime)


def _ext_from_url(url: str) -> str | None:
    """
    Extract the file extension from the URL path.
    Returns lowercase extension including the dot, or None if absent.
    e.g. https://example.com/report.PDF -> '.pdf'
    """
    path = urlparse(url).path
    suffix = Path(path).suffix
    return suffix.lower() if suffix else None


def _build_dest_path(destination_dir: Path, url: str, ext: str) -> Path:
    """
    Build the full destination path:
      <destination_dir>/<YYYY-MM-DD>/<url_hash><ext>
    Creates the date subdirectory if it does not exist.
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_dir = destination_dir / date_str
    date_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_url_hash(url)}{ext}"
    return date_dir / filename


# ── Public API ────────────────────────────────────────────────────────────────

async def download_file(
    url: str,
    destination_dir: Path | str,
    allowed_extensions: List[str] | None = None,
    session: aiohttp.ClientSession | None = None,
    request_timeout_seconds: int = 60,
    skipped_counter: list | None = None,
) -> str | None:
    """
    Download a file from `url` to `destination_dir` if its type is allowed.

    Args:
        url:
            The URL to download.
        destination_dir:
            Root directory for downloads. Files are saved under a date
            subdirectory: <destination_dir>/<YYYY-MM-DD>/<hash>.<ext>
        allowed_extensions:
            List of lowercase extensions to accept, e.g. ['.pdf', '.txt'].
            Defaults to DEFAULT_ALLOWED_EXTENSIONS.
        session:
            Optional existing aiohttp.ClientSession. If None, a temporary
            session is created for this call. Pass a session when calling
            from a long-lived context (crawler.py) to reuse connections.
        request_timeout_seconds:
            Total timeout for the HTTP request.
        skipped_counter:
            Optional single-element list used as a mutable counter for
            silent skips. Pass [0] and the caller can read skipped_counter[0]
            after the call. e.g. skipped_counter[0] += 1 on skip.

    Returns:
        Absolute path string of the saved file, or None if skipped/failed.
    """
    destination_dir = Path(destination_dir)
    allowed_extensions = [e.lower() for e in (allowed_extensions or DEFAULT_ALLOWED_EXTENSIONS)]

    async def _do_download(sess: aiohttp.ClientSession) -> str | None:
        timeout = aiohttp.ClientTimeout(total=request_timeout_seconds)

        try:
            async with sess.get(url, timeout=timeout, allow_redirects=True) as response:
                if response.status != 200:
                    print(f"[downloader] HTTP {response.status} for {url}, skipping")
                    return None

                # ── Determine file extension ──────────────────────────────
                content_type = response.headers.get("Content-Type", "")
                ext = _ext_from_content_type(content_type) or _ext_from_url(url)

                if ext is None:
                    # Neither header nor URL gave us an extension — skip
                    print(f"[downloader] Cannot determine file type for {url}, skipping")
                    if skipped_counter is not None:
                        skipped_counter[0] += 1
                    return None

                if ext not in allowed_extensions:
                    print(f"[downloader] Extension '{ext}' not allowed for {url}, skipping")
                    if skipped_counter is not None:
                        skipped_counter[0] += 1
                    return None

                # ── Stream to disk ────────────────────────────────────────
                dest_path = _build_dest_path(destination_dir, url, ext)

                # If already downloaded (e.g. daemon restart), skip re-download
                if dest_path.exists():
                    print(f"[downloader] Already exists, skipping download: {dest_path}")
                    return str(dest_path)

                bytes_written = 0
                with dest_path.open("wb") as f:
                    async for chunk in response.content.iter_chunked(_STREAM_CHUNK_BYTES):
                        f.write(chunk)
                        bytes_written += len(chunk)

                print(
                    f"[downloader] Saved {bytes_written / 1024:.1f} KB "
                    f"({ext}) -> {dest_path}"
                )
                return str(dest_path)

        except asyncio.TimeoutError:
            print(f"[downloader] Timeout downloading {url}")
            return None
        except aiohttp.ClientError as e:
            print(f"[downloader] Client error downloading {url}: {e}")
            return None
        except OSError as e:
            print(f"[downloader] Filesystem error saving {url}: {e}")
            return None

    if session is not None:
        return await _do_download(session)

    # No session provided — create a temporary one
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(
        connector=connector,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as temp_session:
        return await _do_download(temp_session)


def is_downloadable_url(
    url: str,
    allowed_extensions: List[str] | None = None,
) -> bool:
    """
    Quick pre-flight check: does the URL path end with an allowed extension?
    Used by crawler.py to decide whether to route a URL to the downloader
    before making any HTTP request.

    Note: this only checks the URL path — Content-Type is not available
    until the request is made. Use this as a fast early filter only.
    """
    allowed_extensions = [e.lower() for e in (allowed_extensions or DEFAULT_ALLOWED_EXTENSIONS)]
    ext = _ext_from_url(url)
    return ext is not None and ext in allowed_extensions