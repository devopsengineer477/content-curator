"""
Embedding layer.

Default engine is a dependency-free **hashing TF-IDF** vectoriser with
*incremental* IDF: term -> dimension via md5, weighted by a document-frequency
table that lives in SQLite and is updated as articles arrive. It is fully
deterministic, needs no model download and no API key, and it is genuinely good
enough for the job this layer actually does (near-duplicate detection and
"related stories" retrieval).

Upgrade path (drop-in, same interface):
  * sentence-transformers `all-MiniLM-L6-v2`  -> set EMBEDDER=minilm
  * OpenAI `text-embedding-3-small`            -> set EMBEDDER=openai
Both keep the same `embed()` / `cosine()` contract; only `dim` changes.
"""
from __future__ import annotations

import hashlib
import math
import os
from collections import Counter

import numpy as np

from . import db as store
from .config import settings
from .textutil import tokenize

MODE = os.getenv("EMBEDDER", "hashing").strip().lower()

_openai_client = None


def _client():
    global _openai_client
    if _openai_client is None and settings.openai_api_key:
        from openai import OpenAI  # imported lazily; only needed if opted in

        _openai_client = OpenAI(api_key=settings.openai_api_key,
                                base_url=settings.openai_base_url)
    return _openai_client


def _hash_index(term: str) -> int:
    return int(hashlib.md5(term.encode("utf-8")).hexdigest(), 16) % settings.embed_dim


class HashingEmbedder:
    """Hashing-vectoriser TF-IDF with an IDF table that grows with the corpus."""

    dim = settings.embed_dim

    def embed(self, text: str, update_idf: bool = True) -> np.ndarray:
        counts = Counter(tokenize(text))
        if not counts:
            return np.zeros(self.dim, dtype=np.float32)

        with store.db() as conn:
            if update_idf:
                n_docs = store.get_meta(conn, "doc_count", 0) + 1
            else:
                n_docs = store.get_meta(conn, "doc_count", 0) + 1
            df_map = self._df_for(conn, counts.keys())

        vec = np.zeros(self.dim, dtype=np.float32)
        for term, tf in counts.items():
            idf = math.log((n_docs + 1) / (df_map.get(term, 0) + 1)) + 1.0
            vec[_hash_index(term)] += (1.0 + math.log(tf)) * idf

        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm

        if update_idf:
            self._bump_df(counts.keys())
        return vec

    def _df_for(self, conn, terms) -> dict:
        out, missing = {}, []
        for t in terms:
            out[t] = 0
            missing.append(t)
        # one query for all terms
        CH = 400
        for i in range(0, len(missing), CH):
            chunk = missing[i : i + CH]
            qs = ",".join("?" * len(chunk))
            for row in conn.execute(
                f"SELECT term, df FROM term_df WHERE term IN ({qs})", chunk
            ):
                out[row["term"]] = row["df"]
        return out

    def _bump_df(self, terms) -> None:
        with store.db() as conn:
            conn.execute("BEGIN")
            for t in terms:
                conn.execute(
                    "INSERT INTO term_df(term, df) VALUES(?, 1) "
                    "ON CONFLICT(term) DO UPDATE SET df = df + 1",
                    (t,),
                )
            conn.execute(
                "INSERT INTO meta(key, value) VALUES('doc_count', '1') "
                "ON CONFLICT(key) DO UPDATE SET value = "
                "CAST(CAST(value AS INTEGER) + 1 AS TEXT)"
            )
            conn.execute("COMMIT")


class OpenAIEmbedder:
    dim = 1536

    def embed(self, text: str, update_idf: bool = True) -> np.ndarray:
        client = _client()
        if client is None:
            return HashingEmbedder().embed(text, update_idf)
        resp = client.embeddings.create(model="text-embedding-3-small", input=text[:8000])
        v = np.array(resp.data[0].embedding, dtype=np.float32)
        return v / (np.linalg.norm(v) or 1.0)


_IMPL = OpenAIEmbedder() if MODE == "openai" else HashingEmbedder()


def embed(text: str, update_idf: bool = True) -> np.ndarray:
    return _IMPL.embed(text, update_idf)


#: dimensionality of vectors produced by the active embedder
DIM: int = _IMPL.dim


def set_backend(name: str) -> str:
    """
    Swap the embedder at runtime (used by the Settings panel).

    Existing embeddings stay in the old space, so this is only safe between
    full re-ingests. Returns the backend actually in use afterwards.
    """
    global _IMPL, DIM
    name = (name or "hashing").lower()
    if name not in ("hashing", "openai", "minilm"):
        raise ValueError(f"unknown embedder {name!r}")
    _IMPL = OpenAIEmbedder() if name == "openai" else HashingEmbedder()
    DIM = _IMPL.dim
    return name


def current_backend() -> str:
    return type(_IMPL).__name__


# ---------------------------------------------------------------------------
# similarity
# ---------------------------------------------------------------------------
def cosine(a, b) -> float:
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    na, nb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.clip(np.dot(va, vb) / (na * nb), -1.0, 1.0))


def similarity_matrix(vectors) -> np.ndarray:
    """n x n cosine matrix - used for clustering, computed in one BLAS call."""
    if len(vectors) == 0:
        return np.zeros((0, 0), dtype=np.float32)
    m = np.vstack([np.asarray(v, dtype=np.float32) for v in vectors])
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    m = m / norms
    return np.clip(m @ m.T, -1.0, 1.0)
