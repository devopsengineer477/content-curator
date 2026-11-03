"""
Data ingestion layer.

RSS/Atom via `feedparser` (the default path - nearly every engineering blog
supports a feed), plus an optional full-text fetch for the cases where the feed
only ships a teaser. Crawl4AI / Firecrawl slot in here unchanged: they replace
`fetch_full_text()` and return the same clean markdown.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone

import feedparser

from .config import SOURCES, settings
from .textutil import clean_text, strip_html

logger = logging.getLogger("curator.ingest")

_POINTS = re.compile(r"Points:\s*(\d+)", re.I)
_COMMENTS = re.compile(r"Comments:\s*(\d+)", re.I)


def _struct_to_iso(st) -> str | None:
    if not st:
        return None
    try:
        dt = datetime(*st[:6], tzinfo=timezone.utc)
    except Exception:
        return None
    # Some feeds ship a zeroed struct_time (year 1) for entries that have no
    # real date - OpenTelemetry's does. datetime() accepts year 1 without
    # complaint, which would sink those articles to the bottom of any
    # "newest first" list forever. Treat pre-1970 as unknown so the caller
    # falls back to updated_parsed and then to scraped_at.
    if dt.year < 1970:
        return None
    return dt.isoformat()


def _entry_text(entry) -> str:
    """Best-effort body text from a feed entry."""
    if entry.get("content"):
        try:
            return strip_html(entry["content"][0].get("value", ""))
        except Exception:
            pass
    for key in ("summary", "description"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return strip_html(val)
    return ""


def _fetch(url: str) -> bytes:
    """Fetch a URL with a real timeout, then hand the bytes to feedparser."""
    req = urllib.request.Request(url, headers={"User-Agent": settings.user_agent})
    with urllib.request.urlopen(req, timeout=settings.request_timeout) as resp:
        return resp.read(3_000_000)


def fetch_feed(source: dict) -> tuple[list[dict], str | None]:
    """Returns (entries, error). Never raises."""
    feed_url = source["feed_url"]
    try:
        # fetch ourselves so we control the timeout, then let feedparser parse
        raw = _fetch(feed_url)
        parsed = feedparser.parse(raw, request_headers={"User-Agent": settings.user_agent})
    except Exception as exc:  # noqa: BLE001
        return [], f"fetch error: {exc}"

    if parsed.get("bozo") and not parsed.entries:
        return [], f"feed error: {parsed.get('bozo_exception', 'unknown')}"

    entries: list[dict] = []
    for e in parsed.entries[: settings.max_entries_per_feed]:
        raw = _entry_text(e)
        link = (e.get("link") or "").strip()
        title = strip_html(e.get("title") or "").strip()
        if not link or not title:
            continue

        points = comments = None
        m = _POINTS.search(raw)
        if m:
            points = float(m.group(1))
        m = _COMMENTS.search(raw)
        if m:
            comments = float(m.group(1))

        published = _struct_to_iso(e.get("published_parsed")) or \
            _struct_to_iso(e.get("updated_parsed"))

        entries.append({
            "title": title,
            "url": link,
            "author": strip_html(e.get("author") or ""),
            "raw_text": raw,
            "published_at": published,
            "points": points,
            "comments": comments,
        })
    return entries, None


# ---------------------------------------------------------------------------
# full-text extraction backends
# ---------------------------------------------------------------------------
def _fetch_urllib(url: str, max_chars: int) -> str:
    """Default backend: stdlib fetch + readability heuristics. No dependencies."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": settings.user_agent})
        with urllib.request.urlopen(req, timeout=settings.request_timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "html" not in ctype and "text" not in ctype:
                return ""
            body = resp.read(1_500_000).decode("utf-8", "ignore")
    except (urllib.error.URLError, socket.timeout, TimeoutError, ValueError, OSError):
        return ""
    except Exception:  # noqa: BLE001
        return ""

    try:
        import trafilatura  # type: ignore

        extracted = trafilatura.extract(body, include_comments=False,
                                        include_tables=True, favor_recall=True)
        if extracted and len(extracted) > 200:
            return clean_text(extracted, max_chars)
    except Exception:  # noqa: BLE001
        pass

    return clean_text(body, max_chars)


def _fetch_firecrawl(url: str, max_chars: int) -> str:
    """Firecrawl managed API - POST /v1/scrape, returns markdown."""
    if not settings.firecrawl_api_key:
        raise RuntimeError("FIRECRAWL_API_KEY is not set")
    payload = json.dumps({
        "url": url,
        "formats": [f.strip() for f in settings.firecrawl_formats.split(",") if f.strip()],
        "onlyMainContent": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{settings.firecrawl_api_url.rstrip('/')}/scrape",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.firecrawl_api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=settings.crawl4ai_timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", "ignore"))
    inner = data.get("data") or {}
    md = inner.get("markdown") or inner.get("content") or inner.get("html") or ""
    return clean_text(md, max_chars)


class _AsyncRunner:
    """
    Runs coroutines on one dedicated event loop in a background thread.

    The pipeline is synchronous and Crawl4AI is async, and the browser has to
    stay bound to a single loop to be reusable across calls - so we own one
    loop instead of calling asyncio.run() per article.
    """

    def __init__(self) -> None:
        self._loop = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def run(self, coro, timeout: float):
        with self._lock:
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(
                    target=self._loop.run_forever, daemon=True, name="crawl4ai-loop")
                self._thread.start()
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    def stop(self) -> None:
        with self._lock:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._loop = None
                self._thread = None


_async = _AsyncRunner()
_crawler = None


async def _get_crawler():
    """Lazily start (and then reuse) one browser for the whole process."""
    global _crawler
    if _crawler is None:
        from crawl4ai import AsyncWebCrawler

        _crawler = AsyncWebCrawler()
        await _crawler.start()
    return _crawler


def _fetch_crawl4ai(url: str, max_chars: int) -> str:
    """Crawl4AI - headless browser, returns LLM-ready markdown."""
    import crawl4ai  # noqa: F401  (raises ImportError if not installed)

    async def _run():
        crawler = await _get_crawler()
        return await crawler.arun(
            url=url,
            word_count_threshold=settings.crawl4ai_word_threshold,
            bypass_cache=True,
        )

    result = _async.run(_run(), timeout=settings.crawl4ai_timeout)
    md = getattr(result, "markdown", "") or ""
    # crawl4ai >= 0.4 returns a MarkdownGenerationResult rather than a str
    if not isinstance(md, str):
        md = getattr(md, "raw_markdown", "") or getattr(md, "markdown_with_citations", "")
    if not md or not getattr(result, "success", True):
        return ""
    return clean_text(md, max_chars)


def close_fetcher() -> None:
    """Shut down the shared browser/loop. Called from the app shutdown hook."""
    global _crawler
    if _crawler is not None:
        try:
            _async.run(_crawler.close(), timeout=15)
        except Exception:  # noqa: BLE001
            pass
        _crawler = None
    _async.stop()


def fetch_full_text(url: str, max_chars: int = 14000) -> str:
    """
    Fetch the article body for a URL using `settings.fetcher`.

    Falls back to the stdlib fetcher if the configured backend is missing,
    unconfigured or errors - so a bad FETCHER value costs extraction quality,
    never the ingestion run.
    """
    if not url or not settings.fetch_full_text:
        return ""
    backend = (settings.fetcher or "urllib").lower()
    if backend not in ("urllib", "crawl4ai", "firecrawl"):
        logger.warning("unknown FETCHER=%r, using urllib", settings.fetcher)
        backend = "urllib"

    if backend != "urllib":
        try:
            fn = {"crawl4ai": _fetch_crawl4ai, "firecrawl": _fetch_firecrawl}[backend]
            text = fn(url, max_chars)
            if text:
                return text
            logger.info("%s returned nothing for %s, falling back", backend, url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s fetch failed for %s (%s), falling back to urllib",
                           backend, url, exc)
    return _fetch_urllib(url, max_chars)


def fetcher_status() -> dict:
    """Report which backend is active and whether it is actually usable."""
    backend = (settings.fetcher or "urllib").lower()
    if backend not in ("urllib", "crawl4ai", "firecrawl"):
        return {"backend": backend, "usable": False,
                "detail": "unknown backend - expected urllib|crawl4ai|firecrawl",
                "effective": "urllib"}
    if backend == "urllib":
        return {"backend": backend, "usable": True, "detail": "ready",
                "effective": "urllib"}
    if backend == "crawl4ai":
        try:
            import crawl4ai  # noqa: F401

            detail = f"crawl4ai {getattr(crawl4ai, '__version__', '?')}"
        except ImportError:
            return {"backend": backend, "usable": False,
                    "detail": "not installed - pip install crawl4ai",
                    "effective": "urllib"}
        return {"backend": backend, "usable": True, "detail": detail,
                "effective": "crawl4ai"}
    # firecrawl
    if not settings.firecrawl_api_key:
        return {"backend": backend, "usable": False,
                "detail": "FIRECRAWL_API_KEY not set", "effective": "urllib"}
    return {"backend": backend, "usable": True, "detail": "api key set",
            "effective": "firecrawl"}


def ensure_sources(conn) -> int:
    """
    Upsert the curated source list.

    Rows the user has touched in the dashboard (`managed=1`) are left alone, so
    a feed you removed or renamed there does not get resurrected by the next
    ingestion run. `is_active` is never written here for the same reason.
    """
    n = 0
    for s in SOURCES:
        cur = conn.execute(
            "INSERT INTO sources(name, url, feed_url, category, authority) "
            "VALUES(?,?,?,?,?) ON CONFLICT(feed_url) DO UPDATE SET "
            "name=excluded.name, url=excluded.url, category=excluded.category, "
            "authority=excluded.authority WHERE sources.managed=0",
            (s["name"], s["url"], s["feed_url"], s["category"], s["authority"]),
        )
        n += cur.rowcount or 0
    return n


def add_source(conn, name: str, feed_url: str, category: str = "general-dev",
               authority: float = 0.7) -> int:
    """Add a source from the UI. Marked managed so config.py never overwrites it."""
    cur = conn.execute(
        "INSERT INTO sources(name, url, feed_url, category, authority, managed) "
        "VALUES(?,?,?,?,?,1) ON CONFLICT(feed_url) DO UPDATE SET "
        "name=excluded.name, category=excluded.category, "
        "authority=excluded.authority, is_active=1, managed=1",
        (name, feed_url, feed_url, category, authority),
    )
    return cur.lastrowid
