"""
Pipeline orchestration: fetch -> clean -> embed -> classify -> dedupe -> score.

Mirrors the AI processing layer in the architecture doc. Celery + Redis would
wrap `run_ingestion()` as a periodic task; the function itself is unchanged.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from . import db as store
from . import ingest
from .classifier import classify_article
from .config import settings
from .dedupe import evaluate_candidate, lede_text, recompute_clusters
from .embedder import cosine, embed
from .prioritizer import parse_dt, priority_score
from .textutil import clean_text, word_count

_lock = threading.Lock()
_state: dict = {"running": False, "started_at": None, "finished_at": None,
                "log": [], "stats": {}}


def job_state() -> dict:
    return dict(_state)


def _log(msg: str) -> None:
    _state["log"].append(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} {msg}")
    _state["log"] = _state["log"][-200:]


def run_ingestion(progress: bool = True) -> dict:
    """One full pass over every active source. Safe to call repeatedly."""
    if not _lock.acquire(blocking=False):
        return {"ok": False, "error": "ingestion already running"}

    _state.update(running=True, started_at=datetime.now(timezone.utc).isoformat(),
                  finished_at=None, log=[], stats={})
    stats = {"sources_ok": 0, "sources_failed": 0, "fetched": 0,
             "new": 0, "duplicates": 0, "skipped": 0, "errors": []}
    try:
        with store.db() as conn:
            ingest.ensure_sources(conn)
            sources = conn.execute(
                "SELECT * FROM sources WHERE is_active=1 ORDER BY id"
            ).fetchall()
            known_urls = {
                r["url"] for r in conn.execute("SELECT url FROM articles")
            }

        for src in sources:
            src = dict(src)
            if progress:
                _log(f"fetching {src['name']} …")
            entries, err = ingest.fetch_feed(src)
            now = datetime.now(timezone.utc).isoformat()

            if err:
                stats["sources_failed"] += 1
                stats["errors"].append(f"{src['name']}: {err}")
                _log(f"  ✗ {err}")
            else:
                stats["sources_ok"] += 1
                _log(f"  ✓ {len(entries)} entries")

            with store.db() as conn:
                conn.execute(
                    "UPDATE sources SET last_fetched_at=?, last_status=?, "
                    "last_error=?, items_last_fetch=? WHERE id=?",
                    (now, "ok" if not err else "error", err, len(entries), src["id"]),
                )

            stats["fetched"] += len(entries)
            fresh = [e for e in entries if e["url"] not in known_urls]
            stats["skipped"] += len(entries) - len(fresh)

            if len(fresh) > settings.max_new_per_run:
                fresh = fresh[: settings.max_new_per_run]

            for entry in fresh:
                try:
                    _process(source=src, entry=entry, stats=stats)
                    known_urls.add(entry["url"])
                except Exception as exc:  # noqa: BLE001
                    stats["errors"].append(f"{entry['url'][:70]}: {exc}")

        cluster_stats = recompute_clusters()
        _rescore()
        stats["duplicates"] = cluster_stats.get("duplicates", 0)
        stats.update({"clusters": cluster_stats.get("clusters", 0)})

        _state["stats"] = stats
        _log(f"done: {stats['new']} new, {stats['duplicates']} duplicates, "
             f"{stats['sources_ok']}/{stats['sources_ok'] + stats['sources_failed']} feeds ok")
        return {"ok": True, "stats": stats}
    except Exception as exc:  # noqa: BLE001
        stats["errors"].append(str(exc))
        _state["stats"] = stats
        return {"ok": False, "error": str(exc), "stats": stats}
    finally:
        _state.update(running=False, finished_at=datetime.now(timezone.utc).isoformat())
        _lock.release()


def _process(source: dict, entry: dict, stats: dict) -> None:
    """Clean, embed, classify, dedupe and store a single article."""
    body = entry.get("raw_text") or ""
    if word_count(body) < 60:
        body = (body + " " + ingest.fetch_full_text(entry["url"])).strip()
    # NOTE: the title is deliberately NOT prefixed onto the body. It has its own
    # column, and prefixing it glues "title first-sentence" together, which then
    # leaks into summaries and generated bullets.
    text = clean_text(body)
    if word_count(text) < 25:
        stats["skipped"] += 1
        return

    # --- fingerprints ---------------------------------------------------
    vec = embed(text, update_idf=True)
    lede = lede_text(text)
    lede_vec = embed(lede, update_idf=False) if lede else vec

    # --- duplicate / related scoring against the recent corpus ----------
    ev = evaluate_candidate(entry["title"], text, vec, lede_vec)
    novelty = max(0.0, 1.0 - ev["body_sim"])

    # --- classify -------------------------------------------------------
    cls = classify_article(entry["title"], text, entry.get("points"),
                           float(source.get("authority") or 0.7))

    # --- score ----------------------------------------------------------
    published = parse_dt(entry.get("published_at")) or datetime.now(timezone.utc)
    age_hours = max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600)
    score = priority_score(
        trending=cls["trending_score"],
        age_hours=age_hours,
        authority=float(source.get("authority") or 0.7),
        categories=cls["categories"],
        novelty=novelty,
        cluster_size=1 + len(ev.get("related", [])),
    )

    with store.db() as conn:
        conn.execute(
            """
            INSERT INTO articles(
                source_id, title, url, author, summary, clean_text, categories,
                tags, difficulty, trending_score, priority_score, novelty,
                max_similarity, dup_score, word_count, embedding, lede_embedding,
                published_at, scraped_at, duplicate_of, status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'new')
            ON CONFLICT(url) DO NOTHING
            """,
            (
                source["id"], entry["title"], entry["url"], entry.get("author", ""),
                cls["summary"], text, json.dumps(cls["categories"]),
                json.dumps(cls["tags"]), cls["difficulty"], cls["trending_score"],
                score, round(novelty, 3), ev["body_sim"], ev["dup_score"],
                word_count(text), store.pack(vec.tolist()),
                store.pack(lede_vec.tolist()), entry.get("published_at"),
                datetime.now(timezone.utc).isoformat(), ev["duplicate_of"],
            ),
        )
        stats["new"] += 1


def _rescore() -> int:
    """Re-derive priority scores (freshness decays, cluster sizes grow)."""
    with store.db() as conn:
        rows = conn.execute(
            "SELECT a.id, a.published_at, a.scraped_at, a.novelty, a.categories, "
            "       a.trending_score, a.cluster_size, s.authority "
            "FROM articles a LEFT JOIN sources s ON s.id=a.source_id"
        ).fetchall()
        now = datetime.now(timezone.utc)
        conn.execute("BEGIN")
        for r in rows:
            published = parse_dt(r["published_at"]) or parse_dt(r["scraped_at"]) or now
            age_hours = max(0.0, (now - published).total_seconds() / 3600)
            try:
                cats = json.loads(r["categories"] or "[]")
            except Exception:
                cats = []
            score = priority_score(
                trending=r["trending_score"] or 0,
                age_hours=age_hours,
                authority=float(r["authority"] or 0.7),
                categories=cats,
                novelty=r["novelty"] if r["novelty"] is not None else 1.0,
                cluster_size=r["cluster_size"] or 1,
            )
            conn.execute("UPDATE articles SET priority_score=? WHERE id=?",
                         (score, r["id"]))
        conn.execute("COMMIT")
        return len(rows)


def run_in_background() -> None:
    t = threading.Thread(target=run_ingestion, daemon=True)
    t.start()
