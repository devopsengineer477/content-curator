"""
Deduplication + story clustering.

Two related but different jobs:

* **duplicate** - the *same* story syndicated across outlets. Kept in the DB
  but flagged, so the feed never shows the same story twice. The canonical copy
  is the earliest-published one; the rest point at it via `duplicate_of`.
* **cluster** - genuinely *related* coverage. Drives the "N sources are
  covering this" trending signal and the RAG context used by the generator.

Why a composite score and not a single cosine threshold
-------------------------------------------------------
The architecture sketch this project started from used a single embedding
cosine at 0.92. That number is calibrated for *dense* embedding models
(text-embedding-3-small and friends), where a paraphrase of the same story
lands at 0.85-0.95 and unrelated text at 0.3-0.6.

The default embedder here is a dependency-free hashing TF-IDF (see
`embedder.py`), and on sparse vectors the same-story cosine sits around
0.45-0.57 - permanently below 0.92, so a naive threshold flags nothing. Rather
than fake a threshold, this module scores four cheap, interpretable signals and
combines them. Measured on the bundled corpus (7 known same-story pairs vs 113
unrelated pairs) the composite separates cleanly: positives 0.43-0.81, hardest
negative 0.29. `DUP_THRESHOLD` sits in that gap.

Every component is stored on the article row, so the UI can show *why* a story
was flagged instead of asking the user to trust a black box.
"""
from __future__ import annotations

import re
from collections import Counter

import numpy as np

from . import db as store
from .config import settings
from .embedder import cosine, embed, similarity_matrix
from .prioritizer import parse_dt
from .textutil import tokenize

#: default composite weights - overridable at runtime via settings.dedup_weights
DEFAULT_DUP_WEIGHTS = {"title": 0.30, "lede": 0.20, "body": 0.20, "entity": 0.30}
DUP_WEIGHTS = dict(DEFAULT_DUP_WEIGHTS)
#: fraction of the corpus a term may appear in and still count as "rare"
RARE_DF_RATIO = 0.34
#: sentences from the top of an article used as its "lede" fingerprint
LEDE_SENTENCES = 3


# ---------------------------------------------------------------------------
# fingerprints
# ---------------------------------------------------------------------------
def lede_text(text: str, n: int = LEDE_SENTENCES) -> str:
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if len(s.split()) > 4]
    return " ".join(sents[:n]) or (text or "")[:400]


def rare_terms(tokens: set[str], df: dict[str, int], n_docs: int) -> set[str]:
    """Terms rare enough in the corpus to be identifying (entities, versions)."""
    limit = max(2, int(n_docs * RARE_DF_RATIO))
    return {t for t in tokens if df.get(t, 0) <= limit}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def signals(a: dict, b: dict, df: dict[str, int], n_docs: int) -> dict:
    """The four interpretable similarity components between two articles."""
    ta, tb = set(tokenize(a["title"])), set(tokenize(b["title"]))
    return {
        "title": round(_jaccard(ta, tb), 3),
        "lede": round(cosine(a["lede_vec"], b["lede_vec"]), 3),
        "body": round(cosine(a["vec"], b["vec"]), 3),
        "entity": round(_overlap(a["rare"], b["rare"]), 3),
    }


def _weights() -> dict:
    """Active duplicate-signal weights (settings override the module default)."""
    w = getattr(settings, "dedup_weights", None) or DEFAULT_DUP_WEIGHTS
    return {k: float(v) for k, v in w.items() if k in DEFAULT_DUP_WEIGHTS}


def dup_score(s: dict) -> float:
    w = _weights()
    total = sum(w.values()) or 1.0
    return round(sum(w[k] * s.get(k, 0.0) for k in w) / total, 3)


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------
def load_recent(days: int | None = None) -> list[dict]:
    """Recent articles with their fingerprints attached."""
    days = settings.lookback_days if days is None else days
    with store.db() as conn:
        rows = conn.execute(
            "SELECT a.id, a.url, a.title, a.clean_text, a.embedding, "
            "       a.lede_embedding, a.published_at, a.duplicate_of "
            "FROM articles a WHERE a.embedding IS NOT NULL "
            "AND (a.published_at IS NULL OR a.published_at >= datetime('now', ?))",
            (f"-{days} days",),
        ).fetchall()
        df = {r["term"]: r["df"] for r in conn.execute("SELECT term, df FROM term_df")}
        n_docs = store.get_meta(conn, "doc_count", 0) or 0

    out = []
    for r in rows:
        try:
            toks = set(tokenize(f"{r['title']} {r['clean_text']}"))
            out.append({
                "id": r["id"], "url": r["url"], "title": r["title"],
                "published_at": r["published_at"], "duplicate_of": r["duplicate_of"],
                "vec": np.frombuffer(r["embedding"], dtype=np.float32),
                "lede_vec": (np.frombuffer(r["lede_embedding"], dtype=np.float32)
                             if r["lede_embedding"] else None),
                "rare": rare_terms(toks, df, n_docs),
            })
        except Exception:
            continue
    return out


def evaluate_candidate(title: str, text: str, vec, lede_vec) -> dict:
    """
    Score a not-yet-stored article against the recent corpus.

    Returns the composite duplicate score, the best body cosine, the id of the
    article it duplicates (if any) and the ids of merely-related articles.
    """
    cand = {
        "title": title, "vec": vec, "lede_vec": lede_vec,
        "rare": None,  # filled below
    }
    items = load_recent()
    if not items:
        return {"dup_score": 0.0, "body_sim": 0.0, "duplicate_of": None,
                "related": [], "components": {}}

    with store.db() as conn:
        df = {r["term"]: r["df"] for r in conn.execute("SELECT term, df FROM term_df")}
        n_docs = store.get_meta(conn, "doc_count", 0) or 0
    cand["rare"] = rare_terms(set(tokenize(f"{title} {text}")), df, n_docs)

    best = {"dup_score": 0.0, "body_sim": 0.0, "duplicate_of": None,
            "components": {}}
    related: list[tuple[float, int]] = []

    for it in items:
        comp = signals(cand, it, df, n_docs)
        score = dup_score(comp)
        if score > best["dup_score"]:
            best.update(dup_score=score, components=comp,
                        duplicate_of=it["id"] if score >= settings.dup_threshold else None)
        if comp["body"] >= settings.cluster_threshold:
            related.append((comp["body"], it["id"]))
        best["body_sim"] = max(best["body_sim"], comp["body"])

    best["related"] = [i for _, i in sorted(related, reverse=True)]
    best["dup_score"] = round(best["dup_score"], 3)
    best["body_sim"] = round(best["body_sim"], 3)
    return best


# ---------------------------------------------------------------------------
# RAG retrieval
# ---------------------------------------------------------------------------
def similar_articles(article_id: int, top_k: int = 5,
                     threshold: float | None = None) -> list[dict]:
    """Nearest neighbours of an article by body-vector cosine."""
    threshold = settings.cluster_threshold if threshold is None else threshold
    items = load_recent()
    target = next((i for i in items if i["id"] == article_id), None)
    if target is None:
        return []
    scored = sorted(
        ((cosine(target["vec"], it["vec"]), it) for it in items if it["id"] != article_id),
        key=lambda t: -t[0],
    )
    return [
        {"id": it["id"], "title": it["title"], "url": it["url"],
         "similarity": round(sim, 3)}
        for sim, it in scored if sim >= threshold
    ][:top_k]


# ---------------------------------------------------------------------------
# clustering pass
# ---------------------------------------------------------------------------
def _union_find(items: list[dict]) -> dict[int, int]:
    """Group articles whose body-vector cosine >= cluster_threshold."""
    n = len(items)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    if n > 1:
        mat = similarity_matrix([it["vec"] for it in items])
        for i, j in np.argwhere(mat >= settings.cluster_threshold):
            i, j = int(i), int(j)
            if i < j:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    out: dict[int, int] = {}
    for members in groups.values():
        rep = min(members, key=lambda i: items[i]["id"])
        for i in members:
            out[items[i]["id"]] = items[rep]["id"]
    return out


def recompute_clusters() -> dict:
    """Re-derive duplicate flags, cluster ids and cluster sizes."""
    items = load_recent()
    if not items:
        return {"articles": 0, "clusters": 0, "duplicates": 0}

    with store.db() as conn:
        df = {r["term"]: r["df"] for r in conn.execute("SELECT term, df FROM term_df")}
        n_docs = store.get_meta(conn, "doc_count", 0) or 0

    # --- pairwise composite scores -------------------------------------
    n = len(items)
    comp = np.zeros((n, n), dtype=np.float32)
    body = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        for j in range(i + 1, n):
            s = signals(items[i], items[j], df, n_docs)
            comp[i, j] = comp[j, i] = dup_score(s)
            body[i, j] = body[j, i] = s["body"]

    dup_of: dict[int, int] = {}
    for i, it in enumerate(items):
        order = np.argsort(-comp[i])
        for j in order:
            j = int(j)
            if j == i:
                continue
            if comp[i, j] < settings.dup_threshold:
                break
            other = items[j]
            # the earliest-published copy stays canonical
            if (it["published_at"] or "9999") <= (other["published_at"] or "9999"):
                dup_of[other["id"]] = it["id"]
            else:
                dup_of[it["id"]] = other["id"]
            break

    clusters = _union_find(items)
    sizes: dict[int, int] = {}
    for root in clusters.values():
        sizes[root] = sizes.get(root, 0) + 1

    conn = store.connect()
    try:
        conn.execute("BEGIN")
        for i, it in enumerate(items):
            conn.execute(
                "UPDATE articles SET cluster_id=?, duplicate_of=?, cluster_size=?, "
                "dup_score=?, max_similarity=? WHERE id=?",
                (clusters[it["id"]], dup_of.get(it["id"]), sizes[clusters[it["id"]]],
                 round(float(comp[i].max()), 3), round(float(body[i].max()), 3), it["id"]),
            )
        conn.execute("COMMIT")
    finally:
        conn.close()

    return {"articles": n, "clusters": len(sizes), "duplicates": len(dup_of)}
