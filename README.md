# T20 Cricket News Intelligence System

Web crawling, text analysis and dynamic clustering for T20 cricket news.

The system runs on its own: it collects new T20 articles from open news sites, analyses their
text, groups them into topics it discovers itself, and shows everything on a live dashboard.
Nothing is a static dataset. Every 3 hours new articles flow through the pipeline, topics are
updated, and the dashboard refreshes by itself.

```
Wisden · BBC Sport · The Guardian · CricTracker · Hindustan Times · Indian Express · Cricket Addictor
        │  sitemap / RSS discovery, robots.txt respected, 2 s per-site delay
        ▼
  CRAWLER      extract → validate (T20 filter) → 3-layer duplicate check ─────┐
        ▼                                                                      │ rolling cap (3,000):
  NEON POSTGRES   articles · sources · seen_articles · crawl_runs  ◄───────────┘ oldest deleted, never re-fetched
        ▼
  NLP          cricket-aware entities · lemmas · sentiment · keywords · 384-d embeddings
        ▼
  CLUSTER      HDBSCAN topics (KMeans baseline) · c-TF-IDF labels · stable topics · trend history
        ▼
  API + DASHBOARD   FastAPI → React: Overview · Latest News · Topic Explorer · Trending Topics
```

## Components

| stage | code | docs | tests |
|---|---|---|---|
| Web crawler | `src/crawler/` | [src/crawler/README.md](src/crawler/README.md) | `tests/crawler` |
| Database | `db/schema.sql`, `src/db.py`, `src/init_db.py` | [db/README.md](db/README.md) | `tests/database` |
| NLP | `src/nlp/` | [src/nlp/README.md](src/nlp/README.md) | `tests/nlp` |
| Topics & trends | `src/cluster/` | [src/cluster/README.md](src/cluster/README.md) | `tests/cluster` |
| Dashboard | `src/api/`, `frontend/` | [frontend/README.md](frontend/README.md) | `tests/api` |

Each stage reads only the rows waiting for it (`articles.status`: `cleaned` → `nlp_done` →
`vectorized` → `clustered`), so every stage can be re-run safely and can run on its own schedule.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m spacy download en_core_web_md
copy .env.example .env          # paste your Neon connection string as DATABASE_URL
.venv/Scripts/python -m src.init_db
cd frontend && npm install && npm run build && cd ..
```

## Run

| what | command |
|---|---|
| whole pipeline once | `.venv/Scripts/python run_pipeline.py` |
| dashboard | `.venv/Scripts/python -m src.api` → http://localhost:8000 |
| crawl continuously | `.venv/Scripts/python -m src.crawler.loop --every 30 --store neon` |
| NLP continuously | `.venv/Scripts/python -m src.nlp.run --every 15` |
| topics continuously | `.venv/Scripts/python -m src.cluster.run --every 30` |
| all tests | `.venv/Scripts/python -m pytest tests -q` |

**Automatically on GitHub** (from `main`, with the `DATABASE_URL` repository secret):
`crawler.yml` runs every 3 h, which triggers `nlp.yml`, which triggers `cluster.yml`.

## Design decisions

- **Sources.** Cricbuzz and ESPNcricinfo block automated access (HTTP 403 from Akamai, even for
  `robots.txt`), so the system uses open sources only. No bot protection is bypassed.
- **Duplicates.** Three layers: canonical URL, a hash of the exact content, and SimHash for
  near-duplicates. Re-running any stage never creates duplicate rows.
- **Bounded storage.** At most 3,000 articles are kept. The oldest are deleted, but remembered so
  they are never collected again. Daily topic counts are kept separately, so trends survive.
- **Topics.** HDBSCAN on sentence embeddings found clearer topics than KMeans on the real data
  (silhouette 0.45 against 0.26, NPMI coherence 0.42 against 0.36). Both are evaluated on every
  re-fit and shown in the Explorer.
- **Concurrency.** Each stage holds a Postgres advisory lock, so a laptop and GitHub Actions never
  process the same stage at the same time.

## Branches

`web-crawler` → `database` → `nlp` → `cluster` → `dashboard`, each merged into `main` in turn.
