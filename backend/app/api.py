"""
FastAPI application layer.

Serves the JSON API plus the single-page dashboard. In production this is the
same app; the Next.js frontend in the architecture doc consumes the identical
endpoints, so the dashboard here is a drop-in reference client.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import db as store
from . import ingest
from .config import settings
from .dashboard import DASHBOARD_HTML
from .dedupe import recompute_clusters, similar_articles
from .embedder import MODE as EMBEDDER_MODE
from .embedder import embed
from .pipeline import _rescore, job_state, run_in_background, run_ingestion

app = FastAPI(title="Tech Content Curator", version="1.0.0")

STATUSES = ["new", "reviewing", "drafted", "published"]
VALID_TRANSITIONS = {
    "new": ["reviewing", "drafted", "published"],
    "reviewing": ["drafted", "published", "new"],
    "drafted": ["published", "reviewing", "new"],
    "published": ["reviewing", "new"],
}


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------
@app.on_event("shutdown")
def _shutdown() -> None:
    from .ingest import close_fetcher

    close_fetcher()


@app.on_event("startup")
def _startup() -> None:
    store.init_db()
    _load_stored_settings()
    # Make the 27 curated feeds visible in the Sources panel straight away,
    # before the first ingestion has ever run.
    from .ingest import ensure_sources

    with store.db() as conn:
        ensure_sources(conn)


def _load_stored_settings() -> None:
    """
    Re-apply settings changed from the dashboard in a previous run.

    The database is the source of truth once a value has been overridden there;
    environment variables only supply the initial value.
    """
    from . import embedder
    from .config import EDITABLE_SETTINGS, apply_overrides

    with store.db() as conn:
        stored = store.all_settings(conn)
    if not stored:
        return

    overrides: dict = {}
    for key, raw in stored.items():
        if key in ("embedder",) or key not in EDITABLE_SETTINGS:
            continue
        spec = EDITABLE_SETTINGS[key]
        try:
            if spec["type"] == "json":
                overrides[key] = json.loads(raw)
            elif spec["type"] == "bool":
                overrides[key] = raw == "true"
            else:
                overrides[key] = raw
        except Exception:
            continue
    apply_overrides(overrides)

    if stored.get("embedder"):
        try:
            embedder.set_backend(stored["embedder"])
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)


# ---------------------------------------------------------------------------
# ingestion
# ---------------------------------------------------------------------------
@app.post("/api/ingest")
def api_ingest(background: BackgroundTasks):
    if job_state().get("running"):
        return {"ok": False, "error": "already running"}
    background.add_task(run_ingestion)
    return {"ok": True, "started": True}


@app.get("/api/job")
def api_job():
    return job_state()


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------
@app.get("/api/stats")
def api_stats():
    with store.db() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()["n"]
        by_status = {
            r["status"]: r["n"] for r in conn.execute(
                "SELECT status, COUNT(*) AS n FROM articles GROUP BY status")
        }
        dupes = conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE duplicate_of IS NOT NULL"
        ).fetchone()["n"]
        avg_priority = conn.execute(
            "SELECT AVG(priority_score) AS a FROM articles WHERE duplicate_of IS NULL"
        ).fetchone()["a"] or 0

        categories = [
            {"category": r["c"], "n": r["n"]}
            for r in conn.execute(
                "SELECT value AS c, COUNT(*) AS n FROM articles, json_each(articles.categories) "
                "WHERE duplicate_of IS NULL GROUP BY c ORDER BY n DESC LIMIT 12")
        ]

        sources = [
            dict(r) for r in conn.execute(
                "SELECT s.id, s.name, s.category, s.authority, s.last_status, "
                "       s.last_error, s.items_last_fetch, s.last_fetched_at, "
                "       (SELECT COUNT(*) FROM articles a WHERE a.source_id=s.id) AS articles "
                "FROM sources s ORDER BY s.id")
        ]

        drafts = conn.execute("SELECT COUNT(*) AS n FROM drafts").fetchone()["n"]

        # articles per day for the last 14 days
        days = []
        for i in range(13, -1, -1):
            day = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM articles WHERE substr(COALESCE(published_at,"
                "scraped_at),1,10)=?", (day,)).fetchone()["n"]
            days.append({"day": day, "n": n})

    return {
        "total": total,
        "by_status": {s: by_status.get(s, 0) for s in STATUSES},
        "duplicates": dupes,
        "avg_priority": round(float(avg_priority), 1),
        "categories": categories,
        "sources": sources,
        "sources_ok": sum(1 for s in sources if s["last_status"] == "ok"),
        "drafts": drafts,
        "timeline": days,
        "llm": settings.llm_provider or "heuristic",
        "llm_enabled": settings.llm_enabled,
        "embedder": EMBEDDER_MODE,
        "job": job_state(),
    }


# ---------------------------------------------------------------------------
# articles
# ---------------------------------------------------------------------------
@app.get("/api/articles")
def api_articles(
    status: str | None = None,
    category: str | None = None,
    source: int | None = None,
    q: str | None = None,
    difficulty: str | None = None,
    sort: str = Query("newest", pattern="^(priority|newest|trending|relevance)$"),
    include_duplicates: bool = False,
    limit: int = Query(60, le=200),
    offset: int = 0,
):
    where, params = ["1=1"], []
    if not include_duplicates:
        where.append("a.duplicate_of IS NULL")
    if status and status != "all":
        where.append("a.status=?")
        params.append(status)
    if category:
        where.append("EXISTS (SELECT 1 FROM json_each(a.categories) WHERE value=?)")
        params.append(category)
    if source:
        where.append("a.source_id=?")
        params.append(source)
    if difficulty:
        where.append("a.difficulty=?")
        params.append(difficulty)
    if q:
        # term-based AND: every word must appear somewhere in title/summary/tags
        for term in q.split():
            where.append("(a.title LIKE ? OR a.summary LIKE ? OR a.tags LIKE ?)")
            like = f"%{term}%"
            params += [like, like, like]

    sql_where = " AND ".join(where)
    # Newest first is the default: an unknown publish date falls back to the
    # scrape time, and `id DESC` breaks ties so the order is deterministic
    # (articles ingested in the same second otherwise come back in an
    # arbitrary, unstable order).
    order = {
        "priority": "a.priority_score DESC, a.id DESC",
        "newest": "COALESCE(a.published_at, a.scraped_at) DESC, a.id DESC",
        "trending": "a.trending_score DESC, a.priority_score DESC, a.id DESC",
        "relevance": "a.priority_score DESC, a.id DESC",
    }[sort]

    with store.db() as conn:
        rows = conn.execute(
            f"SELECT a.*, s.name AS source_name FROM articles a "
            f"LEFT JOIN sources s ON s.id=a.source_id WHERE {sql_where} "
            f"ORDER BY {order} LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM articles a WHERE {sql_where}", params
        ).fetchone()["n"]

    items = [store.row_to_dict(r) for r in rows]

    # semantic re-ranking for free-text queries
    if q and items:
        try:
            qv = embed(q, update_idf=False)
            for it in items:
                if it.get("embedding"):
                    from .embedder import cosine

                    vec = store.unpack(it["embedding"])
                    it["relevance"] = round(cosine(qv, vec), 3)
            items.sort(key=lambda i: -(i.get("relevance") or 0))
        except Exception:
            pass

    for it in items:
        it.pop("embedding", None)
        it.pop("clean_text", None)

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/articles/{article_id}")
def api_article(article_id: int):
    with store.db() as conn:
        row = conn.execute(
            "SELECT a.*, s.name AS source_name, s.authority FROM articles a "
            "LEFT JOIN sources s ON s.id=a.source_id WHERE a.id=?", (article_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "article not found")
        art = store.row_to_dict(row)
        drafts = [store.row_to_dict(d) for d in conn.execute(
            "SELECT * FROM drafts WHERE article_id=? ORDER BY id DESC", (article_id,))]
        dupes = [store.row_to_dict(d) for d in conn.execute(
            "SELECT id, title, url FROM articles WHERE duplicate_of=?", (article_id,))]

    art.pop("embedding", None)
    return {"article": art, "drafts": drafts, "duplicates": dupes,
            "related": similar_articles(article_id, top_k=5)}


class StatusPatch(BaseModel):
    status: str


@app.patch("/api/articles/{article_id}")
def api_patch_article(article_id: int, body: StatusPatch):
    if body.status not in STATUSES:
        raise HTTPException(400, f"status must be one of {STATUSES}")
    with store.db() as conn:
        cur = conn.execute("UPDATE articles SET status=? WHERE id=?",
                           (body.status, article_id))
    if cur.rowcount == 0:
        raise HTTPException(404, "article not found")
    return {"ok": True, "id": article_id, "status": body.status}


# ---------------------------------------------------------------------------
# drafts
# ---------------------------------------------------------------------------
class GenerateRequest(BaseModel):
    format: str = "blog"
    all: bool = False


@app.post("/api/articles/{article_id}/generate")
def api_generate(article_id: int, body: GenerateRequest):
    from .content_gen import FORMATS, generate, generate_all

    with store.db() as conn:
        exists = conn.execute("SELECT id FROM articles WHERE id=?", (article_id,)).fetchone()
    if not exists:
        raise HTTPException(404, "article not found")

    if body.all:
        results = generate_all(article_id)
    else:
        if body.format not in FORMATS:
            raise HTTPException(400, f"format must be one of {FORMATS}")
        results = [generate(article_id, body.format)]

    with store.db() as conn:
        for r in results:
            conn.execute(
                "INSERT INTO drafts(article_id, draft_type, generated_content, provider) "
                "VALUES(?,?,?,?)",
                (article_id, r["draft_type"], r["generated_content"], r["provider"]),
            )
    return {"ok": True, "drafts": results}


@app.get("/api/drafts")
def api_drafts(article_id: int | None = None, limit: int = 50):
    sql = ("SELECT d.*, a.title AS article_title FROM drafts d "
           "JOIN articles a ON a.id=d.article_id")
    params: list = []
    if article_id:
        sql += " WHERE d.article_id=?"
        params.append(article_id)
    sql += " ORDER BY d.id DESC LIMIT ?"
    params.append(limit)
    with store.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"items": [store.row_to_dict(r) for r in rows]}


class DraftPatch(BaseModel):
    human_edited_content: str | None = None
    status: str | None = None


@app.patch("/api/drafts/{draft_id}")
def api_patch_draft(draft_id: int, body: DraftPatch):
    sets, params = [], []
    if body.human_edited_content is not None:
        sets.append("human_edited_content=?")
        params.append(body.human_edited_content)
    if body.status is not None:
        sets.append("status=?")
        params.append(body.status)
    if not sets:
        raise HTTPException(400, "nothing to update")
    sets.append("updated_at=?")
    params.append(datetime.now(timezone.utc).isoformat())
    params.append(draft_id)
    with store.db() as conn:
        cur = conn.execute(f"UPDATE drafts SET {', '.join(sets)} WHERE id=?", params)
    if cur.rowcount == 0:
        raise HTTPException(404, "draft not found")
    return {"ok": True, "id": draft_id}


# ---------------------------------------------------------------------------
# settings (runtime-editable, persisted)
# ---------------------------------------------------------------------------
@app.get("/api/settings")
def api_get_settings():
    """Current values, which fields are editable, and live backend health."""
    from . import embedder
    from .config import EDITABLE_SETTINGS
    from .ingest import fetcher_status

    with store.db() as conn:
        stored = store.all_settings(conn)

    fields = []
    for key, spec in EDITABLE_SETTINGS.items():
        # `embedder` lives in embedder.py (chosen at import), not on `settings`
        value = embedder.MODE if key == "embedder" else getattr(settings, key, None)
        if spec["type"] == "secret" and value:
            value = "set (" + str(value)[-4:] + ")"
        fields.append({
            "key": key, "group": spec.get("group", "Other"),
            "label": spec.get("label", key), "type": spec["type"],
            "help": spec.get("help", ""), "value": value,
            "choices": spec.get("choices"),
            "min": spec.get("min"), "max": spec.get("max"),
            "step": spec.get("step"), "overridden": key in stored,
        })
    groups: dict[str, list] = {}
    for f in fields:
        groups.setdefault(f["group"], []).append(f)

    return {
        "groups": groups,
        "fetcher": fetcher_status(),
        "embedder": {"backend": embedder.MODE, "dim": embedder.DIM,
                     "impl": embedder.current_backend()},
        "llm_enabled": settings.llm_enabled,
        "env_note": ("Values changed here are stored in the database and survive a "
                     "restart. An environment variable only sets the initial value."),
    }


@app.patch("/api/settings")
def api_patch_settings(body: dict):
    """Apply a partial settings update; persists and re-applies on next boot."""
    from . import embedder
    from .config import EDITABLE_SETTINGS, apply_overrides

    unknown = [k for k in body if k not in EDITABLE_SETTINGS and k != "embedder"]
    if unknown:
        raise HTTPException(400, f"not editable: {', '.join(unknown)}")

    result = apply_overrides({k: v for k, v in body.items() if k != "embedder"})

    if "embedder" in body:
        try:
            embedder.set_backend(body["embedder"])
        except ValueError as exc:
            result["errors"]["embedder"] = str(exc)

    if result["applied"] or ("embedder" in body and "embedder" not in result["errors"]):
        with store.db() as conn:
            conn.execute("BEGIN")
            for key, value in result["applied"].items():
                store.set_setting(conn, key, json.dumps(value)
                                  if isinstance(value, (dict, list, bool)) else str(value))
            if "embedder" in body and "embedder" not in result["errors"]:
                store.set_setting(conn, "embedder", str(embedder.MODE))
            conn.execute("COMMIT")

    if result["errors"]:
        raise HTTPException(422, detail=result["errors"])
    return {"ok": True, "applied": list(result["applied"])}


@app.post("/api/settings/reset")
def api_reset_settings():
    """Drop every stored override and return to environment-variable defaults."""
    from . import embedder, config
    from .config import EDITABLE_SETTINGS

    with store.db() as conn:
        stored = store.all_settings(conn)
        conn.execute("DELETE FROM settings")

    # a fresh Settings() re-reads the environment, giving us the pristine defaults
    fresh = config.Settings()
    for key in EDITABLE_SETTINGS:
        try:
            setattr(settings, key, getattr(fresh, key))
        except Exception:
            pass
    embedder.set_backend(embedder.MODE)
    return {"ok": True, "cleared": sorted(stored)}


# ---------------------------------------------------------------------------
# sources / maintenance
# ---------------------------------------------------------------------------
class SourceIn(BaseModel):
    name: str
    feed_url: str
    category: str = "general-dev"
    authority: float = 0.7


class SourcePatch(BaseModel):
    name: str | None = None
    feed_url: str | None = None
    category: str | None = None
    authority: float | None = None
    is_active: bool | None = None


@app.get("/api/sources")
def api_sources():
    with store.db() as conn:
        rows = conn.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM articles a WHERE a.source_id=s.id) "
            "AS articles FROM sources s ORDER BY s.managed DESC, s.id DESC"
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@app.post("/api/sources")
def api_add_source(body: SourceIn):
    if not body.feed_url.startswith(("http://", "https://")):
        raise HTTPException(400, "feed_url must start with http:// or https://")
    with store.db() as conn:
        ingest.add_source(conn, body.name, body.feed_url, body.category, body.authority)
    run_in_background()
    return {"ok": True}


@app.patch("/api/sources/{source_id}")
def api_patch_source(source_id: int, body: SourcePatch):
    """Edit or enable/disable a source. Marks it user-managed."""
    with store.db() as conn:
        row = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "source not found")
        sets, params = [], []
        for field in ("name", "feed_url", "category", "authority"):
            v = getattr(body, field)
            if v is not None:
                sets.append(f"{field}=?")
                params.append(v)
        if body.is_active is not None:
            sets.append("is_active=?")
            params.append(1 if body.is_active else 0)
        if not sets:
            raise HTTPException(400, "nothing to update")
        sets.append("managed=1")
        params.append(source_id)
        conn.execute(f"UPDATE sources SET {', '.join(sets)} WHERE id=?", params)
    if body.is_active is not False:
        run_in_background()
    return {"ok": True, "id": source_id}


@app.delete("/api/sources/{source_id}")
def api_delete_source(source_id: int):
    """
    Remove a source.

    Config-listed feeds are soft-deleted (deactivated + marked managed) because
    `ensure_sources` would otherwise re-add them on the next run. Sources the
    user added themselves are removed outright.
    """
    from .config import SOURCES

    with store.db() as conn:
        row = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "source not found")
        if row["feed_url"] in {s["feed_url"] for s in SOURCES}:
            conn.execute("UPDATE sources SET is_active=0, managed=1 WHERE id=?",
                         (source_id,))
            action = "deactivated"
        else:
            conn.execute("DELETE FROM sources WHERE id=?", (source_id,))
            action = "deleted"
    return {"ok": True, "action": action}


@app.post("/api/rescore")
def api_rescore():
    n = _rescore()
    recompute_clusters()
    _rescore()
    return {"ok": True, "rescored": n}


@app.get("/api/config")
def api_config():
    from .ingest import fetcher_status

    return {
        "llm_provider": settings.llm_provider or "heuristic",
        "llm_enabled": settings.llm_enabled,
        "embedder": EMBEDDER_MODE,
        "dup_threshold": settings.dup_threshold,
        "cluster_threshold": settings.cluster_threshold,
        "freshness_half_life_hours": settings.freshness_half_life_hours,
        "weights": settings.weights,
        "fetch_full_text": settings.fetch_full_text,
        "fetcher": fetcher_status(),
        "db": str(settings.db_path),
    }
