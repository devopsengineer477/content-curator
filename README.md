# Tech Content Curator

An AI-powered pipeline that **collects** tech articles from 27 engineering feeds,
**classifies and scores** them, **deduplicates** the same story across outlets,
and **generates drafts** in four formats — with a Kanban dashboard for the
human in the loop.

Everything runs locally with **no API keys and no external services**.

---

## Running the application

### Python only — no Node, no build step

**Yes, Python alone serves the dashboard.** The UI lives in `app/dashboard.py`
as a single self-contained page (inline CSS + JS, ~28 KB) that FastAPI returns
from `GET /`. There is no `npm install`, no bundler, and no separate frontend
process.

The Next.js frontend described in the architecture notes would be a *replacement*
UI consuming the same `/api/*` endpoints — not a prerequisite.

You need exactly four packages:

```
feedparser · fastapi · uvicorn · numpy
```

### Requirements

- **Python 3.11 or newer** — numpy 2.x requires it (on 3.10 the install fails
  with a confusing resolver error, not a clear version message)
- The four packages above; nothing else
- Internet access for the live feed fetch — **optional**. Without it the 27
  feeds report errors in the dashboard; the board simply stays empty until a
  fetch succeeds. Nothing else in the pipeline needs the network.

### Quick start

```bash
cd content-curator/backend
python3 run.py
```

Then open **http://localhost:8000**.

### On a fresh machine

```bash
cd content-curator/backend
pip install -r requirements.txt     # only the 4 required packages are uncommented
python3 run.py
```

`requirements.txt` keeps everything optional (Crawl4AI, Celery, OpenAI,
sentence-transformers…) commented out with a note on when you'd need it. The app
runs fine with all of those absent.

### Other ways to start it

```bash
# auto-reload on code changes (development)
cd content-curator/backend && uvicorn app.api:app --reload --port 8000

# different port / host
PORT=3000 python3 run.py
HOST=127.0.0.1 python3 run.py
```

### On Windows

`FETCHER=crawl4ai python3 run.py` is Unix syntax. Use one of these instead.

**Command Prompt (cmd.exe):**

```cmd
cd content-curator\backend
set FETCHER=crawl4ai
python run.py
```

Or on one line — note the `&&`:

```cmd
cd content-curator\backend && set FETCHER=crawl4ai&& python run.py
```

**PowerShell:**

```powershell
cd content-curator\backend
$env:FETCHER = "crawl4ai"
python run.py
```

**Git Bash / WSL** (if you have it) accepts the original Unix form unchanged.

Notes for Windows:

- Use `python`, not `python3` — the `python3` alias is often a Microsoft Store
  stub that opens the Store instead of running Python. `py -3 run.py` also works.
- `set` applies to that Command Prompt window only, which is what you want here.
- For Crawl4AI, `python -m playwright install chromium` is enough —
  `python -m playwright install-deps` is Linux-only (it shells out to `apt-get`).
- **You can skip the env var entirely** and pick the backend from the dashboard's
  Settings panel instead. It is saved to the database and survives a restart,
  and the panel tells you whether the backend is actually usable.

### What happens on first boot

1. Creates `data/curator.db` (SQLite, WAL mode) if it doesn't exist.
2. Starts a background fetch of all 27 feeds and merges the live articles in.

The board is empty until that first fetch completes, so press **Run ingestion**
(top right) if you want it populated immediately rather than waiting for the
background pass. Deleting `data/` and restarting re-fetches from scratch.

### What you'll see

The dashboard has two tabs in the header — **Board** and **Settings**. Only one
is on screen at a time.

**Board** is the working view: a stats strip, then a Kanban board with four
columns — **New / Reviewing / Drafted / Published**. Click any card to open the
detail drawer, then use **Blog post / LinkedIn / X thread / Newsletter** to
generate a draft. **Run ingestion** (top right) re-fetches every feed and
streams a live per-feed log.

Every list is ordered **newest first** by default — the article at the top of a
column is the most recently published. Articles with no usable publish date
fall back to the time they were scraped, and ties break on insertion id so the
order is stable. The **Sort** selector switches the board to `priority` or
`trending` when you want the ranked view instead.

The current tab is kept in the URL (`#board` / `#settings`), so a refresh or a
bookmark lands you back where you were.

### Light and dark themes

The theme button in the header switches between the dark and light themes.
Dark is the default; on a first visit the browser's `prefers-color-scheme` is
honoured instead.

The choice is stored in `localStorage` under `tc-theme` and survives a reload.
While you have *not* made an explicit choice, a live change to your OS theme is
followed; once you click the button, your choice wins and the OS is ignored
until you clear it.

The theme is resolved by a small inline script in `<head>` that runs before the
first paint, so the page never flashes the wrong colours on load. Both themes
are defined purely as CSS custom properties on `:root` — every colour in the
stylesheet resolves through a variable, so there are no theme-specific
duplicated rules to keep in sync. Text/background pairs in both themes were
checked against WCAG AA (4.5:1 or better).

### The Settings panel

The header has a **Board / Settings** switch. Settings is where you change
behaviour without editing code or restarting:

- **Full-text extraction** — pick the `urllib` / `crawl4ai` / `firecrawl`
  backend from a dropdown. Selecting Crawl4AI or Firecrawl shows the install
  command inline, and the status cards at the top report whether the backend is
  actually usable (package installed? API key present?) and which one is really
  in effect.
- **AI engine** — LLM provider (`heuristic` / `openai` / `openrouter` / `ollama`),
  API keys, model ids, and the embedder backend. Selecting a provider shows the
  exact variables to set, inline.
- **Scoring** — duplicate threshold, related-coverage threshold, freshness
  half-life, the four duplicate-signal weights, and the priority/category
  weights.
- **Pipeline** — max entries per feed, max new articles per run, lookback
  window, HTTP timeout.
- **Sources** — every feed being monitored, with live health, article count and
  authority. Toggle a feed on/off, remove it, or add a new one (name, URL,
  category, authority) from the form at the top. Adding a feed triggers a fetch
  immediately.

Changes are validated (a bad value is rejected with the field named, never
silently applied), saved to the `settings` table, and **survive a restart** —
the database wins over the environment variable once a value has been set
there. Fields you have overridden are tagged `saved`, and **Reset to defaults**
clears them all.

Sources you add or edit are marked `yours` in the list. That matters: the 27
curated feeds in `config.py` are re-synced on every ingestion run, but
user-managed rows are never overwritten — so a feed you disable or remove in the
UI stays that way instead of being resurrected.

Everything here is also an environment variable, which only supplies the
*initial* value:

```bash
FETCHER=crawl4ai python3 run.py      # same as choosing it in the panel
```

---

## What it does

```
┌──────────────────── INGESTION ────────────────────┐
│ 27 RSS/Atom feeds ──► feedparser ──► clean text   │
│                        └─► full-text fetch        │
│                           (fallback when the feed │
│                            only ships a teaser)   │
└───────────────────────────┬───────────────────────┘
                            ▼
┌──────────────────── PROCESSING ───────────────────┐
│ embed (hashing TF-IDF, incremental IDF)           │
│ classify (categories · tags · difficulty)         │
│ dedupe (4-signal composite score)                 │
│ score   (trending · freshness · source · novelty) │
└───────────────────────────┬───────────────────────┘
                            ▼
┌──────────────────── STORAGE ──────────────────────┐
│ SQLite  articles · drafts · sources · term_df     │
└───────────────────────────┬───────────────────────┘
                            ▼
┌──────────────────── APPLICATION ──────────────────┐
│ FastAPI /api/*  +  single-page Kanban dashboard   │
│ content generation (RAG context → 4 formats)      │
└───────────────────────────────────────────────────┘
```

### The pipeline in one pass

| Stage | Module | What it produces |
|---|---|---|
| Fetch | `ingest.py` | raw entries + HN point/comment counts |
| Clean | `textutil.py` | readable plain text from HTML/markdown |
| Embed | `embedder.py` | 1024-dim vector + lede fingerprint |
| Classify | `classifier.py` | categories, tags, difficulty, summary, trending 1–10 |
| Dedupe | `dedupe.py` | duplicate flag, cluster id, per-signal scores |
| Score | `prioritizer.py` | `priority_score` 0–100 |
| Generate | `content_gen.py` | blog / LinkedIn / X thread / newsletter |

---

## Design decisions worth knowing

### 1. The duplicate threshold in the original sketch was wrong for this embedder

The architecture this was built from specified `cosine > 0.92` for dedup. That
number is calibrated for **dense** embeddings (OpenAI `text-embedding-3-small`),
where a paraphrase of the same story lands at 0.85–0.95.

The default embedder here is a dependency-free **hashing TF-IDF** (no model
download, no API key, works offline). On sparse vectors the same-story cosine
sits at **0.45–0.57** — permanently below 0.92, so a naive threshold flags
*nothing*. Measured directly before changing anything:

```
same-story pairs   cosine 0.27–0.57   (all below 0.92 → zero duplicates found)
unrelated pairs    cosine 0.00–0.24
```

Rather than fake a number, `dedupe.py` scores **four interpretable signals** and
combines them:

| Signal | Weight | What it catches |
|---|---|---|
| `title` | 0.30 | token Jaccard on normalised titles |
| `lede` | 0.20 | cosine on the first 3 sentences — syndicated copies share a lede |
| `body` | 0.20 | full-document cosine |
| `entity` | 0.30 | overlap of *rare* corpus terms (versions, product names) |

Measured on the bundled corpus — 7 known same-story pairs vs 113 unrelated pairs:

```
positives   0.43 – 0.81
negatives   0.00 – 0.29     ← hardest negative is 0.29
threshold   0.36            ← sits in the gap
```

Every component is stored on the row (`dup_score`, `max_similarity`), so the UI
can show *why* something was flagged instead of asking you to trust a black box.
Duplicates are **flagged, never deleted** — toggle them in the toolbar.

### 2. Why the embedder is hashing TF-IDF

Installed packages don't persist in this workspace, so a solution depending on a
90 MB sentence-transformers download (plus ~1 GB of torch) would break on the
next run. The hashing vectoriser is pure Python + numpy, deterministic, and has
an incremental IDF table that grows with the corpus.

It is genuinely good at the job this layer does — semantic search, novelty
scoring, RAG retrieval. It is *not* a semantic embedding model, which is exactly
why decision 1 exists. To upgrade, no code changes are needed:

```bash
EMBEDDER=openai   OPENAI_API_KEY=sk-...        # text-embedding-3-small, dim 1536
EMBEDDER=minilm                                 # local all-MiniLM-L6-v2
```

If you switch to a dense embedder, **re-calibrate `dup_threshold`** — with dense
vectors the raw cosine is the right signal and you can drop the composite.

### 3. Classification is heuristic by default, LLM-optional

`classifier.py` scores ~20 categories against weighted keyword lexicons, plus a
~200-entry tech dictionary for tags and marker-phrase heuristics for difficulty.
Transparent, instant, free, and it produces a labelled corpus you can train on.

```bash
LLM_PROVIDER=openai     OPENAI_API_KEY=sk-...        # GPT-4o-mini
LLM_PROVIDER=openrouter OPENROUTER_API_KEY=sk-or-... # many models, one key
LLM_PROVIDER=ollama                                   # local llama3.1
```

With an LLM set, classification and generation both upgrade automatically; the
heuristic result is kept as a fallback if the call fails.

#### Using OpenRouter

OpenRouter is an OpenAI-compatible gateway: it fronts models from many vendors
behind a single API key, so the request/response format is identical and only
the base URL, key and model id differ.

```bash
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
LLM_MODEL=inclusionai/ling-3.0-flash-vl:free

python run.py
```

Notes:

- Model ids are namespaced and may carry a `:variant` suffix — `:free` ids cost
  nothing but are rate-limited, `:beta` opts into pre-release models.
- `LLM_MODEL` is a *generic* override: it wins over `OPENROUTER_MODEL`,
  `OPENAI_MODEL` and `OLLAMA_MODEL`, so one variable works with any provider.
  Leave it unset to use the per-provider default.
- All of these are also editable at runtime in **Settings → AI engine** — no
  restart needed. The key field is a password input and is never echoed back by
  the API (it is stored masked).
- Free-tier rate limits are the usual failure mode. Because generation already
  falls back to the template on any error, a 429 gives you a template draft
  rather than a broken page — check the `provider` field on the draft to see
  which path produced it.

### 4. Content generation is a scaffold, not a finished post

`content_gen.py` pulls the article's 5 nearest neighbours (the R in RAG) and
renders four formats. Every sentence is **extracted from the source** — the
opening line is the article's most measurable claim, the bullets are its most
tag-relevant sentences. The framing, CTA and "what I'd watch next" are the
editorial scaffold a human is expected to rewrite, and the UI tracks
`generated_content` vs `human_edited_content` separately for that reason.

### 5. SQLite instead of PostgreSQL + pgvector

Zero-ops, ships with Python, WAL mode, and the vector search is brute-force
cosine over a 21-day window — a few hundred articles, one BLAS call. The swap is
one function (`db.connect()`) plus one column type. See the mapping below.

---

### 6. Full-text extraction is a pluggable backend

Feeds often ship only a teaser, so the pipeline fetches the article body itself.
`settings.fetcher` picks the backend, and every one of them falls back to the
stdlib fetcher if it is missing, unconfigured or errors — a bad `FETCHER` costs
extraction quality, never the ingestion run.

| `FETCHER` | What it is | Needs |
|---|---|---|
| `urllib` | stdlib fetch + HTML-to-text heuristics (**default**) | nothing |
| `crawl4ai` | self-hosted headless browser, returns LLM-ready markdown | `pip install crawl4ai` + browser |
| `firecrawl` | managed web-data API, clean markdown | `FIRECRAWL_API_KEY` |

```bash
# Crawl4AI
pip install crawl4ai
crawl4ai-setup                                  # downloads the browser
FETCHER=crawl4ai python3 run.py

# Firecrawl
FIRECRAWL_API_KEY=fc-... FETCHER=firecrawl python3 run.py
```

`GET /api/config` reports which backend is active and whether it is actually
usable (`fetcher.backend` / `.effective` / `.detail`), so you can confirm the
swap took without reading logs. The **Settings** panel in the dashboard does the
same thing with a dropdown — see "Running the application → The Settings panel".

Crawl4AI also needs system libraries (`libnspr4`, `libnss3`, `libasound2`). On
Debian/Ubuntu: `python -m playwright install-deps`. Without them the browser
will not launch and the fetcher falls back to `urllib`.

#### The stuck-counter bug

`textutil.strip_html()` originally tracked "am I inside a `<script>`" with a
counter. Real-world HTML has unclosed tags, so the counter got permanently
stuck above zero and **silently discarded the entire document**. Measured
before/after on the same URLs:

```
go.dev/blog/go1.24        9 words  →  847 words
kubernetes.io/blog        6 words  → 2077 words
martinfowler.com       2155 words → 2142 words
```

Non-text elements are now removed by regex *before* parsing, and the parser
itself has no skip logic, so it cannot get stuck.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | dashboard |
| `GET` | `/api/stats` | totals, categories, feed health, 14-day timeline |
| `GET` | `/api/articles` | list — `status`, `category`, `source`, `difficulty`, `q`, `sort`, `include_duplicates`; defaults to `sort=newest` (newest first, `id DESC` tie-break) |
| `GET` | `/api/articles/{id}` | detail + related coverage + duplicates + drafts |
| `PATCH` | `/api/articles/{id}` | move through the workflow |
| `POST` | `/api/articles/{id}/generate` | `{format}` or `{all:true}` |
| `GET` | `/api/drafts` | drafts, optionally by article |
| `PATCH` | `/api/drafts/{id}` | save human edits |
| `GET` | `/api/settings` | editable settings + live backend health |
| `PATCH` | `/api/settings` | change a setting (validated, persisted) |
| `POST` | `/api/settings/reset` | drop overrides, back to env defaults |
| `GET` | `/api/sources` · `POST` | list / add feeds |
| `PATCH` · `DELETE` | `/api/sources/{id}` | edit, enable/disable, remove a feed |
| `POST` | `/api/ingest` | run the pipeline (background) |
| `GET` | `/api/job` | ingestion progress + per-feed log |
| `POST` | `/api/rescore` | re-derive priorities (freshness decays) |
| `GET` | `/api/config` | live thresholds and weights |
| `GET` | `/docs` | OpenAPI (Swagger UI) |

---

## Mapping to the production stack

This runs on what the sandbox provides. Each choice has a documented swap:

| Here | Production | Change |
|---|---|---|
| SQLite | PostgreSQL + pgvector | `db.connect()` → SQLAlchemy/asyncpg; `embedding BLOB` → `vector(1536)`; `ivfflat` index |
| Thread + `BackgroundTasks` | Celery + Redis | wrap `pipeline.run_ingestion()` as a periodic task — the function is unchanged |
| `feedparser` + `urllib` | Crawl4AI / Firecrawl | `FETCHER=crawl4ai|firecrawl`; `fetch_full_text()` dispatches to the chosen backend |
| Hashing TF-IDF | `text-embedding-3-small` / MiniLM | `EMBEDDER=openai` or `minilm`; re-calibrate `dup_threshold` |
| Heuristic classifier | LLM classifier | `LLM_PROVIDER=openai` |
| Inline SPA | Next.js 14 + shadcn/ui | the `/api/*` contract is already what the React app needs |
| `run.py` | Docker Compose → ECS/Fly | containerise; `docker-compose.yml` with `api`, `worker`, `db`, `redis` |

---

## Layout

```
content-curator/
├── backend/
│   ├── run.py                 entrypoint
│   ├── requirements.txt
│   └── app/
│       ├── config.py          settings + the 27 curated sources
│       ├── api.py             FastAPI routes
│       ├── dashboard.py       single-page Kanban UI (inline CSS/JS)
│       ├── pipeline.py        orchestration
│       ├── ingest.py          RSS + full-text fetch
│       ├── classifier.py      taxonomy, tags, difficulty, trending
│       ├── embedder.py        hashing TF-IDF, cosine, similarity matrix
│       ├── dedupe.py          4-signal duplicate scoring + clustering
│       ├── prioritizer.py     0–100 priority score
│       ├── content_gen.py     RAG context + 4 output formats
│       ├── textutil.py        HTML→text, tokenizer
│       ├── db.py              schema, connections, vector packing
│       └── llm.py             optional OpenAI/OpenRouter/Ollama client
└── data/curator.db            created on first run
```

## Configuration

Everything is an environment variable. Defaults run with none set.

| Variable | Default | Effect |
|---|---|---|
| `LLM_PROVIDER` | `""` | `""` heuristic · `openai` · `openrouter` · `ollama` |
| `LLM_MODEL` | — | model id for *any* provider; wins over the per-provider model |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | — | LLM classification + generation |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` | `inclusionai/ling-3.0-flash-vl:free` | one key fronts many models |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible gateway |
| `OPENROUTER_REFERER` / `OPENROUTER_TITLE` | — | optional attribution headers |
| `OLLAMA_URL` / `OLLAMA_MODEL` | `localhost:11434` / `llama3.1` | local LLM |
| `EMBEDDER` | `hashing` | `hashing` · `openai` · `minilm` |
| `FETCH_FULL_TEXT` | `1` | fetch article bodies when the feed is teaser-only |
| `DUP_THRESHOLD` | `0.36` | composite duplicate threshold (calibrated) |
| `CLUSTER_THRESHOLD` | `0.25` | body cosine for "related coverage" |
| `MAX_ENTRIES_PER_FEED` | `18` | entries considered per feed each run |
| `MAX_NEW_PER_RUN` | `220` | cap on new articles per ingestion pass |
| `LOOKBACK_DAYS` | `21` | embedding comparison window for dedup |
| `REQUEST_TIMEOUT` | `12` | HTTP timeout for feed and page fetches |
| `PORT` / `HOST` | `8000` / `0.0.0.0` | server |

Weights for the priority score live in `Settings.weights`; per-category editorial
weights in `Settings.category_weights`. Both are editable from the Settings panel
and are stored in the `settings` table, which takes precedence over the
environment once a value has been saved there.

---

## Known limitations

- **Dedup is heuristic.** The hardest negative in the calibration set (two
  different articles about the same broad topic) scored 0.29 against a 0.36
  threshold — close. Flagged duplicates are visible and reversible, but if you
  need high precision, switch to a dense embedder and re-calibrate.
- **Full-text fetch is best-effort.** Sites that block non-browser agents or
  render client-side return nothing, and the article falls back to the feed
  summary. This is where Crawl4AI/Firecrawl earns its place.
- **Priority depends on `category_weights`.** The defaults encode an editorial
  opinion (architecture and AI/ML rank above career pieces). Tune them.
- **IDF is corpus-global.** As the corpus grows the term statistics shift, so
  embeddings from months ago aren't strictly comparable to new ones. Re-run
  `/api/rescore` and a full re-ingest if that matters.
