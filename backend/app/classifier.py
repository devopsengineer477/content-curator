"""
Classification layer: category, tags, difficulty, summary, trending score.

Two modes, same output contract:

* heuristic (default) - transparent keyword/scoring model, zero cost, works
  offline. Good enough to demo and to bootstrap a labelled corpus.
* LLM (`LLM_PROVIDER=openai|ollama`) - one structured call per article that
  replaces the heuristic guess. The heuristic still runs first and is used as
  a fallback if the LLM call fails.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .config import settings
from .textutil import clean_text, first_sentences, word_count

# ---------------------------------------------------------------------------
# taxonomy
# ---------------------------------------------------------------------------
CATEGORIES: dict[str, list[str]] = {
    "architecture": [
        "architecture", "architectural", "microservice", "monolith", "monolithic",
        "system design", "distributed system", "scalability", "scalable",
        "domain-driven", "ddd", "event-driven", "cqrs", "event sourcing",
        "sharding", "load balancer", "cap theorem", "consensus", "raft", "paxos",
        "message broker", "service mesh", "modular", "trade-off", "tradeoff",
    ],
    "devops": [
        "devops", "ci/cd", "continuous integration", "continuous delivery",
        "continuous deployment", "pipeline", "jenkins", "github actions",
        "gitlab ci", "argo cd", "gitops", "infrastructure as code", "terraform",
        "ansible", "puppet", "chef", "deployment", "rollback", "blue-green",
        "canary", "sre", "site reliability", "on-call", "incident", "postmortem",
        "runbook", "platform engineering", "provisioning",
    ],
    "containers": [
        "docker", "container", "containers", "kubernetes", "k8s", "helm",
        "podman", "containerd", "oci", "container image", "image registry",
        "kubectl", "operator", "cni", "csi",
    ],
    "cloud-aws": [
        "aws", "amazon web services", "amazon ec2", "s3", "lambda", "dynamodb",
        "eks", "rds", "cloudfront", "sqs", "sns", "fargate", "ecs", "cloudformation",
    ],
    "cloud-azure": [
        "azure", "cosmos db", "aks", "azure functions", "app service",
        "arm template", "bicep", "azure devops",
    ],
    "cloud-gcp": [
        "gcp", "google cloud", "bigquery", "gke", "cloud run", "firebase",
        "spanner", "pub/sub", "cloud functions", "app engine",
    ],
    "testing": [
        "testing", "test suite", "unit test", "integration test", "end-to-end",
        "e2e test", "tdd", "bdd", "test coverage", "flaky test", "mocking",
        "pytest", "jest", "vitest", "playwright", "selenium", "regression test",
        "fuzzing", "quality assurance", "test automation", "assertion",
    ],
    "performance": [
        "performance", "latency", "throughput", "benchmark", "benchmarking",
        "profiling", "optimization", "optimisation", "p99", "p95", "p50",
        "tail latency", "caching", "cache", "bottleneck", "flamegraph",
        "load test", "capacity planning", "cpu", "memory usage", "garbage collection",
    ],
    "automation": [
        "automation", "automate", "automating", "scripting", "bot", "rpa",
        "no-code", "low-code", "cron", "scheduled task", "self-healing",
        "workflow automation", "glue code",
    ],
    "observability": [
        "observability", "monitoring", "metrics", "tracing", "distributed tracing",
        "logging", "log aggregation", "opentelemetry", "otel", "prometheus",
        "grafana", "datadog", "apm", "alerting", "slo", "sli", "error budget",
        "telemetry", "jaeger", "loki", "tempo",
    ],
    "algorithms": [
        "algorithm", "algorithms", "data structure", "big-o", "time complexity",
        "sorting", "graph traversal", "dynamic programming", "greedy",
        "recursion", "binary tree", "hash table", "leetcode", "computational",
        "np-hard", "heuristic",
    ],
    "coding": [
        "code", "coding", "programming", "refactor", "refactoring", "code review",
        "clean code", "readability", "debugging", "bug", "technical debt",
        "editor", "productivity", "linting", "type system", "api design",
    ],
    "programming-language": [
        "rust", "golang", "python", "javascript", "typescript", "java", "kotlin",
        "swift", "c++", "cpp", "zig", "elixir", "haskell", "scala", "ruby",
        "php", "language release", "compiler", "runtime", "language design",
        "syntax", "garbage collector", "borrow checker", "async", "await",
    ],
    "design-patterns": [
        "design pattern", "singleton", "factory pattern", "observer pattern",
        "strategy pattern", "dependency injection", "solid", "clean architecture",
        "hexagonal", "ports and adapters", "anti-pattern", "antipattern",
        "coupling", "cohesion", "abstraction", "interface segregation",
    ],
    "security": [
        "security", "vulnerability", "cve", "exploit", "encryption",
        "authentication", "authorization", "oauth", "oidc", "openid connect",
        "jwt", "zero trust", "supply chain", "supply-chain", "sbom",
        "penetration test", "threat", "malware", "phishing", "secrets management",
        "xss", "csrf", "sandbox escape", "trust policy", "credentials",
        "least privilege", "code signing", "attestation", "incident response",
        "threat model", "attack surface",
    ],
    "ai-ml": [
        "machine learning", "deep learning", "neural network", "llm",
        "large language model", "transformer", "gpt", "claude", "embedding",
        "retrieval augmented", "rag", "fine-tuning", "fine tune", "inference",
        "diffusion model", "computer vision", "nlp", "natural language",
        "reinforcement learning", "model training", "gpu", "cuda",
        "hugging face", "pytorch", "vector database", "vector search",
        "context window", "tokenizer", "prompt engineering", "ai agent",
    ],
    "data": [
        "database", "sql", "postgres", "postgresql", "mysql", "sqlite",
        "mongodb", "redis", "kafka", "stream processing", "etl", "data pipeline",
        "data engineering", "analytics", "warehouse", "olap", "oltp", "schema",
        "index", "query planner", "replication", "sharding", "acid",
    ],
    "frontend": [
        "frontend", "front-end", "react", "vue", "svelte", "angular", "css",
        "html", "browser", "dom", "webassembly", "wasm", "user interface",
        "accessibility", "next.js", "tailwind", "web vitals", "rendering",
    ],
    "mobile": [
        "android", "ios", "flutter", "react native", "mobile app", "swiftui",
        "jetpack compose",
    ],
    "career": [
        "career", "hiring", "interview", "salary", "promotion", "management",
        "leadership", "team culture", "remote work", "burnout", "soft skills",
        "developer experience", "onboarding",
    ],
    "general-dev": [
        "software", "engineering", "developer", "development", "release",
        "open source", "github", "tooling", "framework", "library", "api",
        "version control", "git", "standards",
    ],
}

FALLBACK_CATEGORY = "general-dev"

# Words that, when present, make a category claim much more credible.
_HIGH_SIGNAL = re.compile(r"[a-z0-9][a-z0-9'’\.\+\#/-]*")

_TECH_DICT: list[str] = [
    "kubernetes", "docker", "terraform", "ansible", "jenkins", "github actions",
    "gitlab", "argo cd", "helm", "prometheus", "grafana", "opentelemetry",
    "datadog", "kafka", "redis", "postgresql", "postgres", "mysql", "sqlite",
    "mongodb", "elasticsearch", "clickhouse", "rust", "golang", "python",
    "javascript", "typescript", "react", "vue", "svelte", "angular", "node.js",
    "deno", "bun", "java", "kotlin", "swift", "flutter", "react native",
    "c++", "zig", "elixir", "haskell", "scala", "ruby", "php", "aws", "azure",
    "gcp", "cloudflare", "vercel", "netlify", "fastapi", "django", "flask",
    "rails", "spring boot", "next.js", "graphql", "grpc", "rest", "websocket",
    "webassembly", "openai", "anthropic", "claude", "gpt", "llama",
    "hugging face", "pytorch", "tensorflow", "pandas", "numpy", "spark",
    "snowflake", "databricks", "airflow", "dagster", "prefect", "superset",
    "linux", "nginx", "envoy", "istio", "linkerd", "vault", "snyk", "trivy",
    "falco", "ebpf", "quic", "http/3", "tls", "oauth", "jwt", "saml", "git",
    "vim", "vscode", "jetbrains", "playwright", "cypress", "jest", "vitest",
    "pytest", "junit", "selenium", "k6", "locust", "jmeter", "cuda",
    "copilot", "cursor", "langchain", "llamaindex", "haystack", "pgvector",
    "chromadb", "weaviate", "qdrant", "pinecone", "milvus", "celery",
    "rabbitmq", "nats", "protobuf", "avro", "openapi", "swagger",
    "microservices", "serverless", "cloud functions", "cloud run", "fargate",
    "ecs", "eks", "aks", "gke", "s3", "rds", "dynamodb", "bigquery", "spanner",
    "cockroachdb", "scylladb", "cassandra", "presto", "trino", "sentry",
    "pagerduty", "opsgenie", "loom", "webassembly", "systemd", "bash",
]
_TECH_PATTERNS = [
    (t, re.compile(r"(?<![\w.])" + re.escape(t) + r"(?![\w])", re.I))
    for t in sorted(set(_TECH_DICT), key=len, reverse=True)
]

_ADVANCED_MARKERS = [
    "deep dive", "under the hood", "internals", "how we built", "at scale",
    "anatomy of", "advanced", "in practice", "postmortem", "lessons learned",
    "we migrated", "rewrote", "trade-offs", "tradeoffs", "bottleneck",
    "consistency model", "linearizable", "idempotent", "backpressure",
    "memory model", "lock-free", "zero-copy", "cache invalidation",
    "theorem", "proof", "formally", "complexity", "algorithmic",
]
_BEGINNER_MARKERS = [
    "introduction", "intro to", "getting started", "beginner", "tutorial",
    "101", "what is", "explained simply", "for dummies", "basics",
    "primer", "cheat sheet", "quick start", "first steps", "how to use",
    "step by step", "walkthrough",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _count(text: str, needle: str) -> int:
    if not text or not needle:
        return 0
    if " " in needle or "-" in needle or "/" in needle:
        return text.count(needle)
    return len(re.findall(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", text))


def score_categories(text: str) -> dict[str, float]:
    t = f" {text.lower()} "
    scores: dict[str, float] = {}
    for cat, kws in CATEGORIES.items():
        s = 0.0
        for kw in kws:
            n = _count(t, kw)
            if n:
                # longer / rarer keywords carry more signal
                s += n * (1.0 + min(len(kw), 24) / 24.0)
        if s:
            scores[cat] = round(s, 2)
    return scores


def pick_categories(text: str, max_n: int = 4) -> list[str]:
    scores = score_categories(text)
    if not scores:
        return [FALLBACK_CATEGORY]
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top = ranked[0][1]
    chosen = [c for c, s in ranked if s >= max(2.5, 0.34 * top) and c != FALLBACK_CATEGORY]
    if not chosen:
        return [FALLBACK_CATEGORY]
    return chosen[:max_n]


def extract_tags(text: str, title: str, max_n: int = 8) -> list[str]:
    blob = f"{title}\n{text}".lower()
    tags: list[str] = []
    for tech, pat in _TECH_PATTERNS:
        if pat.search(blob):
            tags.append(tech)
        if len(tags) >= max_n:
            break
    if len(tags) < max_n:
        from collections import Counter

        from .textutil import tokenize

        counts = Counter(tokenize(f"{title} {title} {text}"))
        for term, n in counts.most_common(60):
            if len(term) < 4 or term in tags:
                continue
            tags.append(term)
            if len(tags) >= max_n:
                break
    return tags[:max_n]


def guess_difficulty(text: str, title: str, wc: int) -> str:
    blob = f"{title} {text}".lower()
    adv = sum(1 for m in _ADVANCED_MARKERS if m in blob)
    beg = sum(1 for m in _BEGINNER_MARKERS if m in blob)
    score = adv * 1.6 - beg * 1.3
    if wc > 1400:
        score += 0.8
    if wc < 350:
        score -= 0.6
    if score >= 2.2:
        return "advanced"
    if score <= -0.8:
        return "beginner"
    return "intermediate"


def make_summary(text: str, fallback: str = "", max_chars: int = 380) -> str:
    src = text if len(text) > 120 else f"{fallback} {text}".strip()
    return first_sentences(src, n=2, max_chars=max_chars)


def trending_from_points(points: float | None, authority: float) -> float:
    """Map a raw engagement signal (e.g. HN points) onto 1-10."""
    if points is None:
        return round(3.0 + 5.0 * authority, 1)
    # 50 points ~ 3/10, 500 points ~ 9/10
    raw = 1.0 + 8.0 * (min(points, 600.0) / 600.0) ** 0.6
    return round(min(10.0, raw), 1)


# ---------------------------------------------------------------------------
# LLM path (optional)
# ---------------------------------------------------------------------------
_LLM_SCHEMA_HINT = (
    'Return strict JSON only: {"categories": [...], "tags": [...], '
    '"difficulty": "beginner|intermediate|advanced", "summary": "...", '
    '"trending_score": 1-10}'
)


def _llm_classify(title: str, text: str) -> dict | None:
    if not settings.llm_enabled:
        return None
    from .llm import chat_json

    prompt = (
        "You are a technical editor. Classify the article below.\n"
        f"Allowed categories: {', '.join(sorted(CATEGORIES))}\n"
        f"{_LLM_SCHEMA_HINT}\n\n"
        f"TITLE: {title}\n\nTEXT:\n{text[:6000]}"
    )
    data = chat_json(prompt, settings)
    if not isinstance(data, dict):
        return None
    cats = [c for c in data.get("categories", []) if c in CATEGORIES]
    if not cats:
        return None
    return {
        "categories": cats[:4],
        "tags": [str(t) for t in data.get("tags", [])][:8],
        "difficulty": str(data.get("difficulty", "intermediate")),
        "summary": str(data.get("summary", ""))[:600],
        "trending_score": float(data.get("trending_score", 5) or 5),
    }


def classify_article(title: str, text: str, points: float | None,
                     authority: float) -> dict:
    """Single entry point used by the pipeline."""
    result = {
        "categories": pick_categories(f"{title} {text}"),
        "tags": extract_tags(text, title),
        "difficulty": guess_difficulty(text, title, word_count(text)),
        "summary": make_summary(text, title),
        "trending_score": trending_from_points(points, authority),
        "provider": "heuristic",
    }
    if settings.llm_enabled:
        try:
            llm = _llm_classify(title, text)
        except Exception:
            llm = None
        if llm:
            llm["provider"] = settings.llm_provider
            # keep heuristic tags as a floor so the UI never looks empty
            if not llm.get("tags"):
                llm["tags"] = result["tags"]
            if not llm.get("summary"):
                llm["summary"] = result["summary"]
            llm["difficulty"] = llm.get("difficulty") or result["difficulty"]
            return llm
    return result
