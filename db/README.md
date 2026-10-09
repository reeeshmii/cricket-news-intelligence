# Database (Neon PostgreSQL)

[`schema.sql`](schema.sql) defines every table, view and function. Apply or upgrade it with:

```bash
python -m src.init_db
```

It is idempotent (`CREATE … IF NOT EXISTS`, `CREATE OR REPLACE`): it never drops data, so it
is safe to run after the crawler has already created its own tables.

## How articles move through the tables

```
crawler ──► articles (status = cleaned)
nlp     ──► article_nlp       ──► status = nlp_done
        ──► article_vectors   ──► status = vectorized
cluster ──► article_clusters  ──► status = clustered
            clusters / cluster_models / topic_daily_stats
API     ──► v_article_topics, v_topic_daily, v_pipeline_status
```

Each stage picks up only the rows with its input status, so every stage can be re-run safely.

## Tables

| table | owner | contents |
|---|---|---|
| `sources` | crawler | one row per news site, with `last_crawled_at` |
| `articles` | crawler | title, author, dates, body, hashes, `status` |
| `seen_articles` | crawler | every URL ever processed, so evicted articles never come back |
| `crawl_runs` | crawler | per run and source: found / inserted / skipped / duplicates / errors |
| `article_nlp` | nlp | lemmas (TF-IDF input), sentiment, entities, keywords |
| `article_vectors` | nlp | 384-d embedding (`vector(384)`, HNSW cosine index) |
| `cluster_models` | cluster | each clustering run; at most one `is_active` |
| `clusters` | cluster | label, top terms, centroid, size, `stable_key` across re-fits |
| `article_clusters` | cluster | article → cluster with similarity score |
| `topic_daily_stats` | cluster | per-day topic counts that survive the rolling cap |

The crawler's four tables must stay identical to [`src/crawler/schema.sql`](../src/crawler/schema.sql);
`tests/database/test_schema.py` fails if they drift apart.

## Rolling cap and history

The crawler keeps at most `CRAWLER_MAX_ARTICLES` (3000) articles and deletes the oldest-added.
Every table that references `articles` uses `ON DELETE CASCADE`, so NLP, vector and cluster
rows are removed with them. Before that happens, `SELECT refresh_topic_daily_stats();` (run by
the cluster stage) copies the per-day counts into `topic_daily_stats`. It keeps the highest
count ever seen for a day, so trend charts keep their history.

## Views

| view | use |
|---|---|
| `v_article_topics` | articles with topic, sentiment and entities under the active model |
| `v_topic_daily` | live per-day article count and sentiment per topic |
| `v_pipeline_status` | articles waiting at each stage, last crawl, active model (for `/status`) |

## Connecting from code

```python
from src.db import connect

with connect() as conn:                       # pooled endpoint: short queries (API)
    ...
with connect(direct=True) as conn:            # direct endpoint: long jobs, schema changes, SET
    ...
```

Never run session-level `SET` statements through the **pooled** URL: Neon's PgBouncer runs in
transaction mode and leaks them to other clients.
