"""
Content generation engine (RAG-lite).

Retrieves the article's nearest neighbours for context, then renders a draft in
one of four formats. With `LLM_PROVIDER` set, the same context is handed to an
LLM with a senior-writer prompt; otherwise a deterministic template engine
produces the draft. Templates are intentionally opinionated scaffolds - the
human editor is meant to rewrite them, and the UI tracks that (generated vs
human_edited).
"""
from __future__ import annotations

import re

from .config import settings
from .db import db as store_db
from .db import row_to_dict
from .dedupe import similar_articles
from .textutil import first_sentences, truncate

FORMATS = ["blog", "linkedin", "twitter", "newsletter"]

FORMAT_LABELS = {
    "blog": "Blog post",
    "linkedin": "LinkedIn post",
    "twitter": "X / Twitter thread",
    "newsletter": "Newsletter blurb",
}


# ---------------------------------------------------------------------------
# context assembly
# ---------------------------------------------------------------------------
def build_context(article_id: int) -> dict:
    """Load the article plus its nearest neighbours (the R in RAG)."""
    with store_db() as conn:
        row = conn.execute(
            "SELECT a.*, s.name AS source_name, s.authority FROM articles a "
            "LEFT JOIN sources s ON s.id=a.source_id WHERE a.id=?", (article_id,)
        ).fetchone()
    if row is None:
        raise ValueError(f"article {article_id} not found")
    article = row_to_dict(row) or {}
    article.pop("embedding", None)
    article.pop("lede_embedding", None)
    related = similar_articles(article_id, top_k=5)
    return {"article": article, "related": related}


# ---------------------------------------------------------------------------
# extractive helpers - everything below is derived from the source article
# ---------------------------------------------------------------------------
def _body_sentences(article: dict) -> list[str]:
    """
    Sentences of the article body with the leading title line removed.

    `clean_text` is stored as "<title>\\n\\n<body>", and naively splitting it
    glues the title onto the first sentence - which then shows up as a bullet.
    """
    title = (article.get("title") or "").strip()
    text = article.get("clean_text") or ""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if lines and lines[0].strip() == title:
        lines = lines[1:]
    body = " ".join(lines)
    return [re.sub(r"\s+", " ", s.strip())
            for s in re.split(r"(?<=[.!?])\s+", body) if len(s.split()) > 6]


def _claim(article: dict) -> str:
    """
    Pick the article's most assertive sentence to open with. Prefers sentences
    carrying a number or a measurement - those are the ones worth leading with.
    """
    title = (article.get("title") or "").strip().lower()
    pool = [s for s in _body_sentences(article)]
    pool += [s.strip() for s in re.split(r"(?<=[.!?])\s+", article.get("summary") or "")
             if len(s.split()) > 6]

    seen, cands = set(), []
    for s in pool:
        key = s[:36].lower()
        if key in seen or s.strip().lower() == title:
            continue
        seen.add(key)
        cands.append(re.sub(r"\s+", " ", s))
    if not cands:
        return ""

    def rank(s: str) -> tuple:
        return (bool(re.search(r"\d", s)), -abs(len(s.split()) - 20))

    cands.sort(key=rank, reverse=True)
    return truncate(cands[0], 150)


def _bullets(article: dict, n: int = 3) -> list[str]:
    """
    Extract the n most substantive sentences as bullet points.

    Prefers sentences sharing vocabulary with the article's own tags, and keeps
    document order so the bullets read naturally.
    """
    title = (article.get("title") or "").strip().lower()
    sents = [s for s in _body_sentences(article) if s.lower() != title]
    tags = {t.lower() for t in (article.get("tags") or [])[:8]}

    def rank(s: str) -> tuple:
        return (len(set(s.lower().split()) & tags), -abs(len(s.split()) - 26))

    ranked = sorted(sents, key=rank, reverse=True)
    picked: list[str] = []
    for s in ranked:
        if s not in picked:
            picked.append(s)
        if len(picked) >= n:
            break
    order = {s: i for i, s in enumerate(sents)}
    picked.sort(key=lambda s: order.get(s, 0))

    while len(picked) < n:
        picked.append(f"the practical implication of {truncate(article.get('title', ''), 60)}")
    return [truncate(s, 200) for s in picked[:n]]


def _hook(article: dict) -> str:
    """Opening line for a post - the article's own strongest claim."""
    return _claim(article) or truncate(article.get("title", ""), 120)


def _source_line(article: dict) -> str:
    return f"Source: {article.get('source_name', 'unknown')} - {article.get('url', '')}"


def _related_block(related: list[dict]) -> str:
    if not related:
        return ""
    lines = ["**Related coverage worth reading:**"]
    for r in related[:3]:
        lines.append(f"- {truncate(r['title'], 80)} ({r['similarity']:.0%} match)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# template renderers
# ---------------------------------------------------------------------------
def tpl_blog(a: dict, related: list[dict]) -> str:
    tags = a.get("tags") or []
    cat = (a.get("categories") or ["tech"])[0]
    b = _bullets(a, 3)

    return f"""# {a.get('title', '').strip()}

> {_hook(a)}

**TL;DR** - {first_sentences(a.get('summary', ''), 1, 240)}

*Category: {cat} · Difficulty: {a.get('difficulty', 'intermediate')} · Tags: {', '.join(tags[:5]) or 'n/a'}*

## Why this matters

{truncate(a.get('summary', ''), 420)}

{_related_block(related)}

## The key points

1. {b[0]}
2. {b[1]}
3. {b[2]}

## The practical angle

Here is how I would apply this on a real project:

- Start from the failure mode, not the tool. {truncate(a.get('title', ''), 60)} is worth reading because it names a specific failure mode rather than a trend.
- Reproduce it small before adopting it broadly. The smallest version of the problem usually exposes the real constraint, and it is the cheapest place to discover you were wrong.
- Write down the trade-off you are accepting. If you cannot name what you gave up, you have not understood the change yet.

```python
# TODO: replace with a runnable example drawn from the source
# (the source article's own snippet, trimmed to the essential lines)
```

## What I would watch next

The interesting question is not whether this works, it is what breaks at 10x. That is usually where the follow-up post comes from.

---

*Draft generated from {truncate(a.get('source_name', 'a feed'), 40)}. {_source_line(a)}*
"""


def tpl_linkedin(a: dict, related: list[dict]) -> str:
    b = _bullets(a, 3)
    tags = a.get("tags") or []
    hashtags = " ".join(f"#{re.sub(r'[^A-Za-z0-9]', '', t)}" for t in tags[:4]) \
        or "#softwareengineering"

    return f"""{_hook(a)}

I spent the morning on {truncate(a.get('title', ''), 80)} from {a.get('source_name', 'a blog I follow')}.

Three things that stuck:

→ {b[0]}

→ {b[1]}

→ {b[2]}

Where have you seen this pattern bite? Curious whether it matches your experience.

{('Full piece: ' + a.get('url', '')) if a.get('url') else ''}

{hashtags}
"""


def tpl_twitter(a: dict, related: list[dict]) -> str:
    b = _bullets(a, 4)
    rel = related[0]["title"] if related else None
    tweets = [
        f"1/ {_hook(a)}\n\nA thread on {truncate(a.get('title', ''), 90)}",
        f"2/ The setup:\n\n{truncate(first_sentences(a.get('summary', ''), 1, 200), 200)}",
        f"3/ Point one:\n\n{b[0]}",
        f"4/ Point two:\n\n{b[1]}",
        f"5/ Point three:\n\n{b[2]}",
    ]
    if len(b) > 3:
        tweets.append(f"6/ And the one people skip:\n\n{b[3]}")
    if rel:
        tweets.append(
            f"{len(tweets) + 1}/ If you read one more thing on this: {truncate(rel, 120)}")
    tweets.append(
        f"{len(tweets) + 1}/ The meta-lesson: the leverage is almost always in the "
        f"boring fundamentals, not the new thing.\n\nFull piece: {a.get('url', '')}"
    )
    return "\n\n---\n\n".join(tweets)


def tpl_newsletter(a: dict, related: list[dict]) -> str:
    b = _bullets(a, 3)
    cat = (a.get("categories") or ["tech"])[0]
    rel_lines = "\n".join(
        f"  - {truncate(r['title'], 70)} - {r['url']}" for r in related[:3]
    ) or "  - (no related coverage found)"

    return f"""Subject line options:
  A) {truncate(a.get('title', ''), 58)}
  B) {truncate(_hook(a), 58)}
  C) The {cat} story everyone will be arguing about this week

Body:

{_hook(a)}

{first_sentences(a.get('summary', ''), 2, 300)}

Why it made this week's cut:
  - {truncate(b[0], 120)}
  - {truncate(b[1], 120)}
  - {truncate(b[2], 120)}

**Worth your time (related):**
{rel_lines}

---
{_source_line(a)}
"""


TEMPLATES = {
    "blog": tpl_blog,
    "linkedin": tpl_linkedin,
    "twitter": tpl_twitter,
    "newsletter": tpl_newsletter,
}


# ---------------------------------------------------------------------------
# LLM renderer (optional)
# ---------------------------------------------------------------------------
_LLM_PROMPT = """You are a senior tech content creator with an engineering background.

Write a {fmt} based on the source article below. Use the related coverage as
extra context - do not simply restate it, add analysis.

Hard requirements:
- Have a point of view. Do not summarise neutrally.
- Include at least one concrete, practical example or implication.
- Be specific about trade-offs.
- No filler, no "in today's fast-paced world", no emoji spam.
- Format for the target platform (markdown for blog, short lines for LinkedIn,
  numbered tweets for Twitter).

SOURCE TITLE: {title}
SOURCE: {summary}
{related}

Return only the finished {fmt}."""


def llm_render(fmt: str, article: dict, related: list[dict]) -> str:
    from .llm import chat

    related_txt = "\n".join(
        f"- {r['title']} ({r['url']})" for r in related[:3]
    ) or "- (none)"
    prompt = _LLM_PROMPT.format(
        fmt=FORMAT_LABELS.get(fmt, fmt),
        title=article.get("title", ""),
        summary=truncate(article.get("summary", ""), 1200),
        related=related_txt,
    )
    return chat(prompt, settings, max_tokens=1800)


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def generate(article_id: int, fmt: str) -> dict:
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; expected one of {FORMATS}")

    ctx = build_context(article_id)
    article, related = ctx["article"], ctx["related"]

    provider = f"template:{fmt}"
    try:
        if settings.llm_enabled:
            content = llm_render(fmt, article, related)
            provider = f"llm:{settings.llm_provider}"
        else:
            content = TEMPLATES[fmt](article, related)
    except Exception:
        content = TEMPLATES[fmt](article, related)
        provider = f"template:{fmt}"

    return {
        "article_id": article_id,
        "draft_type": fmt,
        "generated_content": content,
        "provider": provider,
        "related_count": len(related),
    }


def generate_all(article_id: int) -> list[dict]:
    return [generate(article_id, f) for f in FORMATS]
