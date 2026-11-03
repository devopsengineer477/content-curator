"""
Bundled demo corpus.

The platform is designed to run against live feeds, but a dashboard full of
empty states is a bad demo and a bad smoke test. These records are pushed
through the *exact same* pipeline as live articles (embed -> classify ->
dedupe -> score).

The corpus deliberately contains six same-story clusters syndicated across
different outlets - each cluster shares a lede, exactly as real coverage does
when several blogs pick up the same release - plus five standalone pieces.
That exercises duplicate detection, clustering and the "N sources covering
this" trending signal.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from . import db as store
from . import ingest
from .dedupe import recompute_clusters
from .pipeline import _process, _rescore, run_in_background

NOW = datetime.now(timezone.utc)

# Each cluster: a shared lede plus a per-outlet angle. Mirrors how a release or
# study gets picked up by several outlets with the same opening paragraph.
CLUSTERS: list[dict] = [
    dict(
        lede=(
            "PostgreSQL 18 is out, and the headline change is asynchronous I/O. "
            "The new io_method=worker setting lets a backend issue read-ahead and "
            "write-back requests without blocking, and vacuum now skips indexes "
            "that have no dead tuples to clean."
        ),
        outlets=[
            dict(name="Hacker News · Front Page", feed="https://hnrss.org/frontpage",
                 authority=0.95, cat="general-dev", days_ago=0.2, points=812,
                 title="PostgreSQL 18 ships async I/O and a faster vacuum",
                 angle=(
                     "In testing on a 400 GB table the incremental vacuum dropped "
                     "from 41 minutes to 9 minutes. There is a migration caveat: the "
                     "statistics collector now records parenthesised expression "
                     "selectivity separately, so plans built on expression indexes may "
                     "change after ANALYZE. Snapshot pg_stat_statements before you "
                     "compare plans so you can prove the difference.")),
            dict(name="The New Stack", feed="https://thenewstack.io/feed/",
                 authority=0.80, cat="general-dev", days_ago=0.3, points=None,
                 title="What async I/O actually changes in PostgreSQL 18",
                 angle=(
                     "Async I/O does not make queries faster. It makes the backend stop "
                     "waiting. With io_method=worker, a sequential scan issues prefetches "
                     "for pages it has not reached yet, so the latency of a large table "
                     "scan becomes bounded by throughput instead of round trips. The "
                     "vacuum improvements are the quiet win for anyone running a busy "
                     "primary.")),
            dict(name="InfoQ", feed="https://www.infoq.com/feed/",
                 authority=0.85, cat="architecture", days_ago=0.4, points=None,
                 title="PostgreSQL 18 Brings Async I/O, Improved Vacuum and New Statistics",
                 angle=(
                     "The release also carries incremental improvements to logical "
                     "replication and a new default for synchronous_commit on standbys. "
                     "Operators should expect meaningful reductions in autovacuum "
                     "pressure, and should re-ANALYZE expression indexes before "
                     "comparing query plans against 17.")),
        ],
    ),
    dict(
        lede=(
            "The async runtime trait has stabilised, and it is the most consequential "
            "change to async Rust since async/await itself. Libraries can now depend on "
            "a stable executor interface instead of a specific runtime, which finally "
            "makes runtime-agnostic async libraries practical."
        ),
        outlets=[
            dict(name="The Rust Blog", feed="https://blog.rust-lang.org/feed.xml",
                 authority=0.92, cat="programming-language", days_ago=1.1, points=340,
                 title="Async Rust in 2026: what the new runtime trait changes",
                 angle=(
                     "The trait is deliberately minimal: spawn, sleep, and a handle type. "
                     "Anything richer stays in ecosystem crates, which keeps the standard "
                     "surface small enough to stabilise. The trade-off is compile time and "
                     "diagnostic quality - trait-based dispatch means worse error messages "
                     "in some cases. Measure before you migrate a hot library.")),
            dict(name="Hacker News · 100+ points",
                 feed="https://hnrss.org/frontpage?points=100",
                 authority=0.92, cat="general-dev", days_ago=1.3, points=415,
                 title="Async Rust in 2026: what the new runtime trait changes",
                 angle=(
                     "The surface is intentionally tiny - spawn, sleep, and a handle - "
                     "with richer behaviour left to ecosystem crates. That minimalism is "
                     "what made stabilisation possible. Expect worse compile times and "
                     "messier diagnostics in exchange, and benchmark before porting "
                     "anything hot.")),
        ],
    ),
    dict(
        lede=(
            "Most teams complaining about observability costs are looking at the wrong "
            "metric. Ingest volume is a symptom; the disease is label cardinality. One "
            "high-cardinality label added to a metric multiplies every series that "
            "carries it."
        ),
        outlets=[
            dict(name="Grafana Labs Blog", feed="https://grafana.com/blog/index.xml",
                 authority=0.82, cat="observability", days_ago=0.6, points=None,
                 title="Your observability bill is a cardinality problem, not a volume problem",
                 angle=(
                     "We audited a customer writing 4.1 million active series and found "
                     "that 78% came from three labels: user_id, request_id and pod_name. "
                     "Removing user_id alone cut the bill by 61% and lost nothing "
                     "operationally important - nobody had ever alerted on it. The fix is "
                     "a cardinality budget enforced in CI, with an owner and an exception "
                     "process.")),
            dict(name="The Pragmatic Engineer", feed="https://blog.pragmaticengineer.com/feed",
                 authority=0.93, cat="observability", days_ago=0.9, points=None,
                 title="The observability cost crisis is really a cardinality crisis",
                 angle=(
                     "In the environments we have audited, three labels account for the "
                     "majority of active series: a user identifier, a request identifier, "
                     "and the pod name. None belong in a metric label. Moving them to "
                     "structured logs or exemplars preserves debuggability at a fraction "
                     "of the cost. Treat metric labels as a scarce resource, because they "
                     "are.")),
        ],
    ),
    dict(
        lede=(
            "We removed a service from the playback path and p99 start-up latency fell "
            "40%. The service was not slow. It was a network hop, a serialisation "
            "boundary, and a failure domain that nobody owned anymore."
        ),
        outlets=[
            dict(name="Netflix TechBlog", feed="https://netflixtechblog.com/feed",
                 authority=0.90, cat="architecture", days_ago=2.4, points=690,
                 title="How we cut p99 latency 40% by deleting a service",
                 angle=(
                     "The lesson generalises: every hop buys independent deployability and "
                     "costs a tail-latency budget. Once a service's logic stops changing, "
                     "the trade stops being worth it. We now review every service that has "
                     "gone two quarters without a functional change as a deletion "
                     "candidate. If p99 does not move, the hop was not the problem.")),
            dict(name="Engineering at Meta", feed="https://engineering.fb.com/feed/",
                 authority=0.88, cat="architecture", days_ago=2.9, points=None,
                 title="Deleting a service to fix tail latency",
                 angle=(
                     "The service being removed was healthy and well-monitored, which is "
                     "exactly why it survived so long: nothing looked broken. After folding "
                     "the read path into the caller, p99 latency improved by roughly 40%. "
                     "The write path stayed separate because it had genuinely different "
                     "scaling characteristics.")),
        ],
    ),
    dict(
        lede=(
            "A class of CI compromise that needs no malicious package. If your OIDC token "
            "audience is broader than the workflow that requested it, a token minted for "
            "a low-privilege pull-request workflow can be replayed against a deployment "
            "role."
        ),
        outlets=[
            dict(name="Cloudflare Blog", feed="https://blog.cloudflare.com/rss/",
                 authority=0.85, cat="security", days_ago=3.2, points=520,
                 title="The supply chain attack nobody modelled: stale OIDC tokens in CI",
                 angle=(
                     "We found configurations where the subject claim matched any workflow "
                     "in the repository rather than the specific one, effectively granting "
                     "every contributor a path to production credentials. The condition "
                     "check is one line in the trust policy and it was missing. Audit for "
                     "exact subject matching, short token lifetimes and environment "
                     "protection rules.")),
            dict(name="GitHub Blog", feed="https://github.blog/feed/",
                 authority=0.85, cat="security", days_ago=3.6, points=None,
                 title="Hardening CI: OIDC audience scoping and the tokens you forgot",
                 angle=(
                     "Scope the subject claim to the exact workflow and ref, keep lifetimes "
                     "short, and require environment approvals for anything "
                     "production-facing. Then test the negative case: try to use a "
                     "PR-workflow token against the deployment role and confirm it fails. "
                     "This is the supply chain risk dependency scanning will never find, "
                     "because there is no malicious package involved.")),
        ],
    ),
]

# Standalone pieces - no duplicates, just normal corpus entries.
STANDALONE = [
    dict(name="Hacker News · Front Page", feed="https://hnrss.org/frontpage",
         authority=0.95, cat="ai-ml", days_ago=0.1, points=960,
         title="RAG retrieval quality is a chunking problem, and chunking is a schema problem",
         body=(
             "Most RAG systems underperform because of chunking, not because of the "
             "embedding model. Fixed-size chunking destroys the structure that makes a "
             "document retrievable: a table separated from its caption, a code block "
             "separated from the function it belongs to.\n\n"
             "The fix is to chunk along the document's own structure - headings, sections, "
             "function boundaries - and to store enough parent context to make the chunk "
             "self-contained when retrieved. A 400-token chunk that starts mid-sentence is "
             "unretrievable no matter how good the model is.\n\n"
             "Evaluate retrieval independently of generation. If your recall@10 is below "
             "0.8, no prompt engineering will save the answer.")),
    dict(name="ByteByteGo", feed="https://blog.bytebytego.com/feed",
         authority=0.88, cat="architecture", days_ago=1.8, points=275,
         title="Visual guide: how vector search actually retrieves your documents",
         body=(
             "A walk through what happens between a user question and the passages a vector "
             "database returns. The query is embedded into the same space as the documents, "
             "then an approximate nearest neighbour index - HNSW in most systems - navigates "
             "a proximity graph rather than comparing against every vector.\n\n"
             "The practical consequence is that recall is tunable and rarely tuned. "
             "ef_search and the number of probes determine how much of the graph you "
             "explore, and the defaults favour latency. If answers feel randomly wrong, "
             "raise recall before touching the prompt.\n\n"
             "The diagram covers the full path: embed, index, probe, rerank, and the parent "
             "lookup that reassembles the original document.")),
    dict(name="The Go Blog", feed="https://go.dev/blog/feed.atom",
         authority=0.92, cat="performance", days_ago=4.5, points=310,
         title="Profiling Go services in production without ruining production",
         body=(
             "Continuous profiling in production is now table stakes, and the risk is not "
             "the profiler - it is what you do with the data. A profile taken during a "
             "traffic spike describes the spike, not the service.\n\n"
             "Sample at a fixed rate rather than on demand, tag profiles with the deployment "
             "revision, and always diff against a baseline from the same time of day. A 12% "
             "CPU increase means nothing at 3am on a Tuesday; a 12% increase against last "
             "Tuesday at 3am is a regression you can act on.\n\n"
             "The other rule: never profile the whole fleet. One node per availability zone, "
             "chosen deterministically, gives a statistically useful sample at a fraction of "
             "the overhead.")),
    dict(name="Spotify Engineering", feed="https://engineering.atspotify.com/feed/",
         authority=0.88, cat="performance", days_ago=5.1, points=None,
         title="What we learned profiling 4,000 production services",
         body=(
             "Four years of continuous profiling across a large fleet, and the surprises "
             "were not where we expected. Flamegraphs rarely pointed at the code we "
             "suspected. They pointed at serialisation, at mutex contention in shared "
             "caches, and at logging frameworks holding locks on the hot path.\n\n"
             "Diffing is the whole game. Absolute profiles are archaeology; a diff against "
             "the previous deploy is a bug report. We now treat a profile without a baseline "
             "as unreviewable.\n\n"
             "Our biggest win came from a logging library, not from application code. Look "
             "at framework overhead before optimising business logic.")),
    dict(name="Stack Overflow Blog", feed="https://stackoverflow.blog/feed/",
         authority=0.80, cat="career", days_ago=6.2, points=180,
         title="The senior engineer's real job is deleting options",
         body=(
             "The gap between senior and staff is not technical depth. It is the willingness "
             "to remove possibilities. Junior engineers add options - a new library, a second "
             "service, a feature flag. Senior engineers take them away, because every option "
             "you keep is a thing the team has to reason about forever.\n\n"
             "This shows up in review comments. 'Can we also support X?' is a junior "
             "question. 'What happens if we deliberately do not support X?' is a senior one. "
             "The second question is uncomfortable and it is where the leverage is.\n\n"
             "If your design doc has six alternatives and no recommendation, you have written "
             "a research summary, not a design doc.")),
]


def _ensure_source(conn, name: str, feed: str, cat: str, authority: float) -> dict:
    """
    Find or create the source for a demo entry.

    Matches on name first so a stale feed_url in this file can never create a
    duplicate source row - it updates the existing one instead.
    """
    row = conn.execute("SELECT * FROM sources WHERE name=?", (name,)).fetchone()
    if row is None:
        row = conn.execute("SELECT * FROM sources WHERE feed_url=?", (feed,)).fetchone()
    if row is None:
        ingest.add_source(conn, name, feed, cat, authority)
        row = conn.execute("SELECT * FROM sources WHERE feed_url=?", (feed,)).fetchone()
    elif row["feed_url"] != feed:
        conn.execute("UPDATE sources SET feed_url=?, category=?, authority=? WHERE id=?",
                     (feed, cat, authority, row["id"]))
        row = conn.execute("SELECT * FROM sources WHERE id=?", (row["id"],)).fetchone()
    return dict(row)


def seed_demo_data() -> dict:
    """Push the bundled corpus through the real pipeline."""
    with store.db() as conn:
        ingest.ensure_sources(conn)

    stats = {"new": 0, "skipped": 0, "errors": []}
    jobs: list[tuple[dict, dict]] = []

    for cluster in CLUSTERS:
        for o in cluster["outlets"]:
            jobs.append((
                dict(name=o["name"], feed=o["feed"], authority=o["authority"],
                     cat=o["cat"], days_ago=o["days_ago"], points=o["points"],
                     title=o["title"],
                     body=cluster["lede"] + "\n\n" + o["angle"]),
            ))
    for s in STANDALONE:
        jobs.append((s,))

    for j in jobs:
        o = j[0]
        with store.db() as conn:
            source = _ensure_source(conn, o["name"], o["feed"], o["cat"], o["authority"])
        published = (NOW - timedelta(days=o["days_ago"])).isoformat()
        slug = o["title"][:40].lower().replace(" ", "-").replace(":", "")
        # deterministic fingerprint so re-seeding is idempotent
        fp = hashlib.md5((o["title"] + o["name"]).encode()).hexdigest()[:10]
        entry = {
            "title": o["title"],
            "url": f"https://demo.local/{fp}/{slug}",
            "author": "",
            "raw_text": o["body"],
            "published_at": published,
            "points": o.get("points"),
            "comments": None,
        }
        try:
            _process(source=source, entry=entry, stats=stats)
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append(str(exc))

    recompute_clusters()
    _rescore()
    return stats


def seed_if_empty() -> None:
    """Called on boot: seed the demo corpus when the DB has no articles."""
    with store.db() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()["n"]
    if n == 0:
        seed_demo_data()
        run_in_background()
