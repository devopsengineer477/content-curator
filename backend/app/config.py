"""
Central configuration for the Tech Content Curation & Creation platform.

Everything is overridable through environment variables so the same code runs
in local dev, in Docker Compose, and in production.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # /home/user/content-curator
DATA_DIR = ROOT / "data"


@dataclass
class Settings:
    # --- storage ---------------------------------------------------------
    db_path: Path = DATA_DIR / "curator.db"
    # SQLite (dev) -> PostgreSQL + pgvector (prod). See README.
    embed_dim: int = 1024

    # --- ingestion -------------------------------------------------------
    max_entries_per_feed: int = 18
    max_new_per_run: int = 220
    request_timeout: float = 12.0
    user_agent: str = (
        "Mozilla/5.0 (compatible; TechCurator/1.0; +https://example.local/bot)"
    )
    fetch_full_text: bool = os.getenv("FETCH_FULL_TEXT", "1") not in ("0", "false")

    # --- dedupe / similarity --------------------------------------------
    # Composite duplicate score threshold. NOT a raw cosine: see dedupe.py for
    # why (0.92 is the right number for dense embeddings, wrong for sparse
    # TF-IDF). Calibrated on the bundled corpus: positives 0.43-0.81,
    # hardest negative 0.29.
    dup_threshold: float = 0.36
    # body-vector cosine at which two articles count as related coverage
    cluster_threshold: float = 0.25
    # weights of the four duplicate signals - see dedupe.py
    dedup_weights: dict = field(default_factory=lambda: {
        "title": 0.30, "lede": 0.20, "body": 0.20, "entity": 0.30,
    })
    lookback_days: int = 21

    # --- scoring ---------------------------------------------------------
    freshness_half_life_hours: float = 36.0
    weights: dict = field(
        default_factory=lambda: {
            "trending": 0.30,
            "freshness": 0.25,
            "source": 0.15,
            "category": 0.15,
            "novelty": 0.15,
        }
    )
    # Editorial weight per category - tune this to taste.
    category_weights: dict = field(
        default_factory=lambda: {
            "architecture": 1.00,
            "ai-ml": 0.95,
            "devops": 0.90,
            "observability": 0.88,
            "performance": 0.85,
            "security": 0.85,
            "data": 0.80,
            "cloud-aws": 0.78,
            "cloud-gcp": 0.75,
            "cloud-azure": 0.72,
            "containers": 0.78,
            "programming-language": 0.75,
            "design-patterns": 0.75,
            "testing": 0.70,
            "algorithms": 0.68,
            "frontend": 0.62,
            "automation": 0.60,
            "coding": 0.58,
            "mobile": 0.50,
            "career": 0.45,
            "general-dev": 0.40,
        }
    )

    # --- full-text extraction -------------------------------------------
    # Which backend `ingest.fetch_full_text()` uses when a feed ships only a
    # teaser instead of the article body.
    #
    #   urllib      stdlib fetch + HTML-to-text heuristics. Zero dependencies.
    #               Works for most blogs; fails on JS-rendered pages and on
    #               sites that block non-browser user agents.
    #   crawl4ai    Self-hosted Crawl4AI. Headless browser, returns LLM-ready
    #               markdown, handles JS-heavy sites and paywall-ish layouts.
    #               Free, no per-page fees, you run the infrastructure.
    #               Install:  pip install crawl4ai && crawl4ai-setup
    #   firecrawl   Managed web-data API. Clean markdown / structured data.
    #               Needs a FIRECRAWL_API_KEY and costs per page.
    #
    # Every backend falls back to `urllib` if it is missing, unconfigured or
    # errors, so a wrong FETCHER degrades quality instead of breaking ingestion.
    fetcher: str = os.getenv("FETCHER", "urllib").strip().lower()

    # Crawl4AI
    crawl4ai_timeout: float = float(os.getenv("CRAWL4AI_TIMEOUT", "45"))
    crawl4ai_word_threshold: int = int(os.getenv("CRAWL4AI_WORD_THRESHOLD", "10"))

    # Firecrawl
    firecrawl_api_key: str = os.getenv("FIRECRAWL_API_KEY", "")
    firecrawl_api_url: str = os.getenv(
        "FIRECRAWL_API_URL", "https://api.firecrawl.dev/v1")
    firecrawl_formats: str = os.getenv("FIRECRAWL_FORMATS", "markdown")

    # --- LLM (optional) --------------------------------------------------
    # "" = heuristic mode (no keys, no cost, works offline)
    # "openai" | "openrouter" | "ollama" = LLM classification + generation
    #
    # OpenRouter (https://openrouter.ai) is an OpenAI-compatible gateway that
    # fronts many models behind a single key. It speaks the same
    # request/response shape as OpenAI, so supporting it costs no new logic -
    # only a different base URL, key and model id. Model ids are namespaced
    # and may carry a ":variant" suffix, e.g.
    #   inclusionai/ling-3.0-flash-vl:free
    llm_provider: str = os.getenv("LLM_PROVIDER", "").strip().lower()
    # Generic model override: if set it wins over the provider-specific
    # *_model below, so one `LLM_MODEL=x` works with any provider.
    llm_model: str = os.getenv("LLM_MODEL", "").strip()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv(
        "OPENROUTER_MODEL", "inclusionai/ling-3.0-flash-vl:free")
    openrouter_base_url: str = os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    # Optional OpenRouter attribution headers, surfaced on your OpenRouter
    # dashboard. The referer is omitted entirely when blank.
    openrouter_referer: str = os.getenv("OPENROUTER_REFERER", "")
    openrouter_title: str = os.getenv("OPENROUTER_TITLE", "Tech Content Curator")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1")

    # --- server ----------------------------------------------------------
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        if self.llm_provider == "openrouter":
            return bool(self.openrouter_api_key)
        return self.llm_provider == "ollama"

    @property
    def active_llm_model(self) -> str:
        """Model id sent to the active provider.

        A generic LLM_MODEL wins over the per-provider *_model, so a single
        env var works whichever gateway is selected.
        """
        if self.llm_model:
            return self.llm_model
        if self.llm_provider == "openrouter":
            return self.openrouter_model
        if self.llm_provider == "ollama":
            return self.ollama_model
        return self.openai_model


settings = Settings()


# ---------------------------------------------------------------------------
# Runtime-editable settings
#
# Everything here can be changed from the dashboard's Settings panel without a
# restart. Values are persisted to the `settings` table and re-applied on boot,
# so a change made in the UI beats the environment variable that seeded it.
#
# `embedder` is a pseudo-setting: it lives in embedder.py (chosen at import),
# and is swapped via embedder.set_backend() rather than a plain attribute.
# ---------------------------------------------------------------------------
EDITABLE_SETTINGS: dict[str, dict] = {
    # --- full-text extraction ---
    "fetcher": {
        "type": "choice", "choices": ["urllib", "crawl4ai", "firecrawl"],
        "group": "Full-text extraction",
        "label": "Backend",
        "help": "Which extractor runs when a feed ships only a teaser.",
    },
    "fetch_full_text": {
        "type": "bool", "group": "Full-text extraction",
        "label": "Fetch article bodies",
        "help": "Off = trust the feed summary only, never fetch the page.",
    },
    "firecrawl_api_key": {
        "type": "secret", "group": "Full-text extraction",
        "label": "Firecrawl API key", "help": "Required when backend is firecrawl.",
    },
    "firecrawl_api_url": {
        "type": "str", "group": "Full-text extraction",
        "label": "Firecrawl API URL", "help": "Override for self-hosted Firecrawl.",
    },
    "firecrawl_formats": {
        "type": "str", "group": "Full-text extraction",
        "label": "Firecrawl formats", "help": "Comma-separated output formats.",
    },
    "crawl4ai_timeout": {
        "type": "float", "min": 5, "max": 300, "group": "Full-text extraction",
        "label": "Crawl4AI timeout (s)",
    },
    "crawl4ai_word_threshold": {
        "type": "int", "min": 0, "max": 500, "group": "Full-text extraction",
        "label": "Crawl4AI word threshold",
    },

    # --- LLM ---
    "llm_provider": {
        "type": "choice", "choices": ["", "openai", "openrouter", "ollama"],
        "group": "AI engine", "label": "LLM provider",
        "help": "Empty = heuristic classifier and template generator (no key needed).",
    },
    "llm_model": {
        "type": "str", "group": "AI engine", "label": "Model (any provider)",
        "help": "Generic override: wins over the per-provider model below. "
                "Useful for OpenRouter ids such as inclusionai/ling-3.0-flash-vl:free",
    },
    "openai_api_key": {
        "type": "secret", "group": "AI engine",
        "label": "OpenAI API key", "help": "Required when provider is openai.",
    },
    "openai_model": {"type": "str", "group": "AI engine", "label": "OpenAI model"},
    "openrouter_api_key": {
        "type": "secret", "group": "AI engine",
        "label": "OpenRouter API key", "help": "Required when provider is openrouter.",
    },
    "openrouter_model": {
        "type": "str", "group": "AI engine", "label": "OpenRouter model",
        "help": "Namespaced id, optionally with a :free / :beta suffix.",
    },
    "openrouter_base_url": {
        "type": "str", "group": "AI engine", "label": "OpenRouter base URL",
        "help": "Only change this for a proxy or a self-hosted gateway.",
    },
    "openrouter_referer": {
        "type": "str", "group": "AI engine", "label": "OpenRouter referer",
        "help": "Optional attribution header shown on your OpenRouter dashboard.",
    },
    "openrouter_title": {
        "type": "str", "group": "AI engine", "label": "OpenRouter app title",
        "help": "Optional attribution header shown on your OpenRouter dashboard.",
    },
    "ollama_url": {"type": "str", "group": "AI engine", "label": "Ollama URL"},
    "ollama_model": {"type": "str", "group": "AI engine", "label": "Ollama model"},

    # --- embeddings ---
    "embedder": {
        "type": "choice", "choices": ["hashing", "openai", "minilm"],
        "group": "AI engine", "label": "Embedder",
        "help": "hashing = built-in TF-IDF, no dependencies. Switching needs no restart.",
    },

    # --- scoring ---
    "dup_threshold": {
        "type": "float", "min": 0.0, "max": 1.0, "step": 0.01,
        "group": "Scoring", "label": "Duplicate threshold",
        "help": "Composite score above which two articles count as the same story.",
    },
    "cluster_threshold": {
        "type": "float", "min": 0.0, "max": 1.0, "step": 0.01,
        "group": "Scoring", "label": "Related-coverage threshold",
        "help": "Body cosine above which two articles are treated as related.",
    },
    "freshness_half_life_hours": {
        "type": "float", "min": 1, "max": 720, "group": "Scoring",
        "label": "Freshness half-life (h)",
        "help": "Hours for an article's freshness score to halve.",
    },
    "weights": {"type": "json", "group": "Scoring", "label": "Priority weights"},
    "category_weights": {"type": "json", "group": "Scoring", "label": "Category weights"},
    "dedup_weights": {"type": "json", "group": "Scoring", "label": "Duplicate-signal weights"},

    # --- pipeline limits ---
    "max_entries_per_feed": {
        "type": "int", "min": 1, "max": 100, "group": "Pipeline",
        "label": "Max entries per feed",
        "help": "How many of a feed's most recent entries to consider each run.",
    },
    "max_new_per_run": {
        "type": "int", "min": 10, "max": 2000, "group": "Pipeline",
        "label": "Max new articles per run",
        "help": "Cap on how much a single ingestion pass will add.",
    },
    "lookback_days": {
        "type": "int", "min": 1, "max": 365, "group": "Pipeline",
        "label": "Lookback window (days)",
        "help": "How far back to compare embeddings when deduplicating.",
    },
    "request_timeout": {
        "type": "float", "min": 2, "max": 120, "group": "Pipeline",
        "label": "HTTP timeout (s)",
    },
}


def _coerce(spec: dict, value):
    """Validate and coerce an incoming value against its spec."""
    t = spec["type"]
    if t == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() in ("1", "true", "yes", "on"):
                return True
            if value.lower() in ("0", "false", "no", "off"):
                return False
        raise ValueError("expected a boolean")
    if t == "choice":
        v = str(value)
        if v not in spec["choices"]:
            raise ValueError(f"must be one of {spec['choices']}")
        return v
    if t == "int":
        v = int(float(value))
        if "min" in spec and v < spec["min"]:
            raise ValueError(f"must be >= {spec['min']}")
        if "max" in spec and v > spec["max"]:
            raise ValueError(f"must be <= {spec['max']}")
        return v
    if t == "float":
        v = float(value)
        if "min" in spec and v < spec["min"]:
            raise ValueError(f"must be >= {spec['min']}")
        if "max" in spec and v > spec["max"]:
            raise ValueError(f"must be <= {spec['max']}")
        return v
    if t == "json":
        if isinstance(value, (dict, list)):
            return value
        try:
            parsed = json.loads(value)
        except Exception:
            raise ValueError("must be valid JSON")
        if not isinstance(parsed, dict):
            raise ValueError("must be a JSON object")
        return parsed
    # str / secret
    return "" if value is None else str(value)


def apply_overrides(overrides: dict) -> dict:
    """
    Validate and apply a partial settings update to the live `settings` object.

    Returns {"applied": {...}, "errors": {field: message}} - never raises, so a
    bad field can be reported back to the UI instead of 500ing.
    """
    applied, errors = {}, {}
    for key, value in (overrides or {}).items():
        spec = EDITABLE_SETTINGS.get(key)
        if spec is None:
            errors[key] = "not an editable setting"
            continue
        try:
            setattr(settings, key, _coerce(spec, value))
            applied[key] = getattr(settings, key)
        except (ValueError, TypeError) as exc:
            errors[key] = str(exc)
    return {"applied": applied, "errors": errors}

# ---------------------------------------------------------------------------
# Curated source list. Per-feed failures are non-fatal: the pipeline records
# health per source and the dashboard surfaces it, so a dead feed never takes
# the run down.
# ---------------------------------------------------------------------------
SOURCES: list[dict] = [
    # --- general developer news ---
    dict(name="Hacker News · Front Page", url="https://news.ycombinator.com/",
         feed_url="https://hnrss.org/frontpage", category="general-dev", authority=0.95),
    dict(name="Hacker News · 100+ points", url="https://news.ycombinator.com/",
         feed_url="https://hnrss.org/frontpage?points=100", category="general-dev", authority=0.92),
    dict(name="InfoQ", url="https://www.infoq.com/",
         feed_url="https://www.infoq.com/feed/", category="architecture", authority=0.85),
    dict(name="The New Stack", url="https://thenewstack.io/",
         feed_url="https://thenewstack.io/feed/", category="general-dev", authority=0.80),
    dict(name="Stack Overflow Blog", url="https://stackoverflow.blog/",
         feed_url="https://stackoverflow.blog/feed/", category="coding", authority=0.80),
    dict(name="DEV Community", url="https://dev.to/",
         feed_url="https://dev.to/feed/", category="coding", authority=0.65),

    # --- architecture / design ---
    dict(name="ByteByteGo", url="https://blog.bytebytego.com/",
         feed_url="https://blog.bytebytego.com/feed", category="architecture", authority=0.88),
    dict(name="Martin Fowler", url="https://martinfowler.com/",
         feed_url="https://martinfowler.com/feed.atom", category="architecture", authority=0.97),
    dict(name="The Pragmatic Engineer", url="https://www.pragmaticengineer.com/",
         feed_url="https://blog.pragmaticengineer.com/feed", category="general-dev", authority=0.93),

    # --- cloud ---
    dict(name="AWS News Blog", url="https://aws.amazon.com/blogs/aws/",
         feed_url="https://aws.amazon.com/blogs/aws/feed/", category="cloud-aws", authority=0.90),
    dict(name="Google Developers Blog", url="https://developers.googleblog.com/",
         feed_url="https://developers.googleblog.com/feeds/posts/default",
         category="cloud-gcp", authority=0.90),
    dict(name="Cloudflare Blog", url="https://blog.cloudflare.com/",
         feed_url="https://blog.cloudflare.com/rss/", category="performance", authority=0.85),

    # --- devops / infra ---
    dict(name="Kubernetes Blog", url="https://kubernetes.io/blog/",
         feed_url="https://kubernetes.io/feed.xml", category="containers", authority=0.92),
    dict(name="GitHub Blog", url="https://github.blog/",
         feed_url="https://github.blog/feed/", category="coding", authority=0.85),
    dict(name="GitLab Blog", url="https://about.gitlab.com/blog/",
         feed_url="https://about.gitlab.com/atom.xml", category="devops", authority=0.80),

    # --- observability / performance ---
    dict(name="Grafana Labs Blog", url="https://grafana.com/blog/",
         feed_url="https://grafana.com/blog/index.xml", category="observability", authority=0.82),
    dict(name="OpenTelemetry Blog", url="https://opentelemetry.io/blog/",
         feed_url="https://opentelemetry.io/index.xml", category="observability", authority=0.82),

    # --- languages ---
    dict(name="The Go Blog", url="https://go.dev/blog/",
         feed_url="https://go.dev/blog/feed.atom", category="programming-language", authority=0.92),
    dict(name="The Rust Blog", url="https://blog.rust-lang.org/",
         feed_url="https://blog.rust-lang.org/feed.xml", category="programming-language", authority=0.92),
    dict(name="Python Insider", url="https://blog.python.org/",
         feed_url="https://blog.python.org/feeds/posts/default",
         category="programming-language", authority=0.90),
    dict(name="JavaScript Weekly", url="https://javascriptweekly.com/",
         feed_url="https://javascriptweekly.com/rss/", category="frontend", authority=0.82),

    # --- company engineering blogs ---
    dict(name="Netflix TechBlog", url="https://netflixtechblog.com/",
         feed_url="https://netflixtechblog.com/feed", category="architecture", authority=0.90),
    dict(name="Spotify Engineering", url="https://engineering.atspotify.com/",
         feed_url="https://engineering.atspotify.com/feed/", category="architecture", authority=0.88),
    dict(name="Engineering at Meta", url="https://engineering.fb.com/",
         feed_url="https://engineering.fb.com/feed/", category="architecture", authority=0.88),
    dict(name="Dropbox Tech Blog", url="https://blog.dropbox.com/",
         feed_url="https://blog.dropbox.com/feed", category="architecture", authority=0.84),
    dict(name="CNCF Blog", url="https://www.cncf.io/blog/",
         feed_url="https://www.cncf.io/feed/", category="containers", authority=0.85),
    dict(name="Docker Blog", url="https://www.docker.com/blog/",
         feed_url="https://www.docker.com/feed/", category="containers", authority=0.82),
]
