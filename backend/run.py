#!/usr/bin/env python3
"""Entrypoint: python backend/run.py  (or: uvicorn app.api:app --port 8000)"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

import uvicorn  # noqa: E402

from app import db  # noqa: E402
from app.config import settings  # noqa: E402


def main() -> None:
    db.init_db()
    print(f"""
┌──────────────────────────────────────────────────────────────┐
│  Tech Content Curator                                        │
├──────────────────────────────────────────────────────────────┤
│  API         http://{settings.host}:{settings.port}/api/docs            │
│  Dashboard   http://{settings.host}:{settings.port}/                     │
│  Database    {str(settings.db_path):<48}
│  LLM         {(settings.llm_provider or 'heuristic (no key needed)'):<48}
│  Embedder    {('hashing-tfidf' if settings.llm_provider == '' else 'openai'):<48}
└──────────────────────────────────────────────────────────────┘
""".replace("  \n", "\n"))
    uvicorn.run("app.api:app", host=settings.host, port=settings.port,
                log_level="info", access_log=False)


if __name__ == "__main__":
    main()
