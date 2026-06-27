from urllib.parse import urlparse, urlunparse, unquote, urlencode, parse_qsl
from tldextract import extract as tld_extract
from daemon.logger import RichLogManager

log = RichLogManager.get_logger()


def normalize_url(url: str) -> str:
    """
    Normalize a URL for deduplication and storage.

    Rules applied:
    - Lowercase scheme and host
    - Remove default ports (80 for http, 443 for https)
    - Decode percent-encoding on path only (not query string)
    - Collapse redundant path separators (// -> /)
    - Remove trailing slash from path unless path is bare /
    - Sort query parameters for consistent ordering
    - Remove fragment (#section)
    - Reject and return empty string for non-http(s) URLs

    Returns the normalized URL string, or empty string if the URL is invalid
    or uses an unsupported scheme.
    """
    try:
        parsed = urlparse(url.strip())
    except Exception:
        log.error(f"[normalize_url] Failed to parse URL: '{url}'")
        return ""

    # Only handle http and https
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        log.error(f"[normalize_url] Unsupported scheme '{scheme}', dropping: '{url}'")
        return ""

    # Lowercase host, strip leading/trailing whitespace
    netloc = parsed.netloc.lower().strip()
    if not netloc:
        log.error(f"[normalize_url] Missing host, dropping: '{url}'")
        return ""

    # Remove default ports using splitport-safe logic
    # netloc may be host:port or just host
    if ":" in netloc:
        host, _, port = netloc.rpartition(":")
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    # Decode percent-encoding on path only, then collapse // sequences
    path = unquote(parsed.path)
    while "//" in path:
        path = path.replace("//", "/")

    # Remove trailing slash unless path is exactly "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Sort query parameters for consistent deduplication
    # e.g. ?b=2&a=1 and ?a=1&b=2 should be the same URL
    query = ""
    if parsed.query:
        params = parse_qsl(parsed.query, keep_blank_values=True)
        params.sort()
        query = urlencode(params)

    # Always drop fragment
    normalized = urlunparse((scheme, netloc, path, parsed.params, query, ""))

    if normalized != url:
        log.debug(f"[normalize_url] '{url}' -> '{normalized}'")

    return normalized


def strip_query_params(url: str) -> str:
    """
    Return the URL with all query parameters removed.
    Used only on the 404 re-queue path.
    Prints debug showing what was stripped.
    """
    parsed = urlparse(url)
    stripped = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        "",
        ""
    ))
    if stripped != url:
        log.debug(f"[strip_query_params] '{url}' -> '{stripped}'")
    return stripped


def get_root_domain(url: str) -> str:
    """
    Extract the registered root domain from a URL.
    e.g. https://apps.irs.gov/page -> irs.gov
         https://www.treasury.gov/ -> treasury.gov

    Uses tldextract to correctly handle TLDs like .co.uk, .gov, etc.
    Returns empty string if extraction fails.
    """
    extracted = tld_extract(url)
    if extracted.domain and extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}"
    return ""


def is_same_root_domain(url: str, reference_url: str) -> bool:
    """
    Returns True if url shares the same registered root domain as reference_url.
    e.g. apps.irs.gov and www.irs.gov both match irs.gov.
    """
    return get_root_domain(url) == get_root_domain(reference_url)