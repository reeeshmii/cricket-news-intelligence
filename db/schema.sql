-- Full database schema for the T20 Cricket News Intelligence System.
-- Idempotent: safe to run any number of times (python -m src.init_db); it never drops data.
--
-- Pipeline stages and the tables they own:
--   crawler  -> sources, articles, seen_articles, crawl_runs   (must match src/crawler/schema.sql)
--   nlp      -> article_nlp, article_vectors                   (articles.status: cleaned -> nlp_done -> vectorized)
--   cluster  -> cluster_models, clusters, article_clusters,    (articles.status -> clustered)
--               topic_daily_stats
--   dashboard/API reads the v_* views.
--
-- The crawler deletes the oldest articles beyond its rolling cap. Every table that references
-- articles uses ON DELETE CASCADE, so the NLP/cluster rows go with them. topic_daily_stats keeps
-- per-day topic counts after the articles are gone, so trend history survives the cap.

-- pgvector lives in `public` explicitly, so it can never end up inside a temporary/test schema.
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

-- ============================ crawler (identical to src/crawler/schema.sql) ============================
CREATE TABLE IF NOT EXISTS sources (
    id              SERIAL PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,
    base_url        TEXT NOT NULL,
    last_crawled_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS articles (
    id            BIGSERIAL PRIMARY KEY,               -- insertion order -> rolling cap
    source_id     INT REFERENCES sources(id),
    url           TEXT NOT NULL,
    canonical_url TEXT NOT NULL UNIQUE,                -- dedup layer 1
    title         TEXT NOT NULL,
    author        TEXT,
    published_at  TIMESTAMPTZ,
    scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    body          TEXT NOT NULL,
    word_count    INT,
    content_hash  TEXT NOT NULL UNIQUE,                -- dedup layer 2
    simhash       BIGINT,                              -- dedup layer 3
    duplicate_of  BIGINT REFERENCES articles(id),
    status        TEXT NOT NULL DEFAULT 'cleaned'
                  CHECK (status IN ('cleaned','nlp_done','vectorized','clustered'))
);
CREATE INDEX IF NOT EXISTS idx_articles_status    ON articles(status);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_scraped   ON articles(scraped_at);

CREATE TABLE IF NOT EXISTS seen_articles (
    url          TEXT PRIMARY KEY,
    outcome      TEXT NOT NULL,
    content_hash TEXT,
    seen_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_seen_hash ON seen_articles(content_hash);
CREATE INDEX IF NOT EXISTS idx_seen_at   ON seen_articles(seen_at);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id          SERIAL PRIMARY KEY,
    source_id   INT REFERENCES sources(id),
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    found       INT DEFAULT 0,
    inserted    INT DEFAULT 0,
    skipped     INT DEFAULT 0,
    duplicates  INT DEFAULT 0,
    errors      INT DEFAULT 0
);
ALTER TABLE crawl_runs ADD COLUMN IF NOT EXISTS details JSONB;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS image_url TEXT;           -- article's own preview image (og:image)

-- ============================ nlp ============================
CREATE TABLE IF NOT EXISTS article_nlp (
    article_id   BIGINT PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
    lemmas       TEXT NOT NULL,                        -- space-joined tokens, input for TF-IDF
    sentiment    REAL,                                 -- -1 (negative) .. +1 (positive)
    entities     JSONB,                                -- {"PERSON": [...], "ORG": [...], "GPE": [...]}
    keywords     JSONB,                                -- top keywords for the article
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_nlp_entities ON article_nlp USING gin (entities);

CREATE TABLE IF NOT EXISTS article_vectors (
    article_id BIGINT PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
    model      TEXT NOT NULL,                          -- e.g. all-MiniLM-L6-v2
    embedding  vector(384) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_vectors_hnsw ON article_vectors USING hnsw (embedding vector_cosine_ops);

-- ============================ cluster ============================
CREATE TABLE IF NOT EXISTS cluster_models (
    id          SERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    algorithm   TEXT NOT NULL,                         -- e.g. kmeans-minilm, hdbscan, bertopic
    params      JSONB,
    n_clusters  INT,
    silhouette  REAL,
    is_active   BOOLEAN NOT NULL DEFAULT FALSE
);
-- at most one active model at a time
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_active_model ON cluster_models(is_active) WHERE is_active;

CREATE TABLE IF NOT EXISTS clusters (
    id         SERIAL PRIMARY KEY,
    model_id   INT NOT NULL REFERENCES cluster_models(id) ON DELETE CASCADE,
    label      TEXT,                                   -- auto label from top terms (editable)
    top_terms  JSONB,
    centroid   vector(384) NOT NULL,
    size       INT,
    stable_key TEXT                                    -- same topic across re-fits (old->new matching)
);
CREATE INDEX IF NOT EXISTS idx_clusters_model ON clusters(model_id);

CREATE TABLE IF NOT EXISTS article_clusters (
    article_id  BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    cluster_id  INT    NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    score       REAL,                                  -- similarity to the centroid
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (article_id, cluster_id)
);
CREATE INDEX IF NOT EXISTS idx_article_clusters_cluster ON article_clusters(cluster_id);

-- Per-day topic counts that survive the crawler's rolling cap (trend history).
CREATE TABLE IF NOT EXISTS topic_daily_stats (
    day           DATE NOT NULL,
    model_id      INT  NOT NULL REFERENCES cluster_models(id) ON DELETE CASCADE,
    cluster_id    INT  NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    label         TEXT,
    article_count INT  NOT NULL,
    avg_sentiment REAL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, cluster_id)
);

-- ============================ views (dashboard / API) ============================
-- Articles with their topic under the ACTIVE clustering model.
CREATE OR REPLACE VIEW v_article_topics AS
SELECT a.id, a.title, a.url, a.published_at, a.scraped_at, s.name AS source,
       c.id AS cluster_id, c.label, ac.score, n.sentiment, n.entities
FROM articles a
JOIN sources s           ON s.id = a.source_id
JOIN article_clusters ac ON ac.article_id = a.id
JOIN clusters c          ON c.id = ac.cluster_id
JOIN cluster_models m    ON m.id = c.model_id AND m.is_active
LEFT JOIN article_nlp n  ON n.article_id = a.id;

-- Live per-day topic counts from the articles currently stored.
CREATE OR REPLACE VIEW v_topic_daily AS
SELECT c.model_id, t.cluster_id, t.label,
       (COALESCE(t.published_at, t.scraped_at) AT TIME ZONE 'UTC')::date AS day,
       count(*) AS articles, avg(t.sentiment)::real AS avg_sentiment
FROM v_article_topics t
JOIN clusters c ON c.id = t.cluster_id
GROUP BY 1, 2, 3, 4;

-- Pipeline health: how many articles wait at each stage, plus the last crawl per source.
CREATE OR REPLACE VIEW v_pipeline_status AS
SELECT
    (SELECT count(*) FROM articles)                                    AS articles_total,
    (SELECT count(*) FROM articles WHERE status = 'cleaned')           AS waiting_for_nlp,
    (SELECT count(*) FROM articles WHERE status = 'nlp_done')          AS waiting_for_vectors,
    (SELECT count(*) FROM articles WHERE status = 'vectorized')        AS waiting_for_cluster,
    (SELECT count(*) FROM articles WHERE status = 'clustered')         AS clustered,
    (SELECT max(scraped_at) FROM articles)                             AS last_article_at,
    (SELECT max(finished_at) FROM crawl_runs)                          AS last_crawl_at,
    (SELECT id FROM cluster_models WHERE is_active)                    AS active_model_id;

-- ============================ functions ============================
-- Copy today's live counts into topic_daily_stats. GREATEST() keeps the highest count seen,
-- so a day whose articles were partly evicted by the rolling cap never loses history.
CREATE OR REPLACE FUNCTION refresh_topic_daily_stats() RETURNS INT
LANGUAGE sql AS $$
    WITH up AS (
        INSERT INTO topic_daily_stats (day, model_id, cluster_id, label, article_count, avg_sentiment)
        SELECT day, model_id, cluster_id, label, articles, avg_sentiment FROM v_topic_daily
        ON CONFLICT (day, cluster_id) DO UPDATE
            SET article_count = GREATEST(topic_daily_stats.article_count, EXCLUDED.article_count),
                avg_sentiment = CASE WHEN EXCLUDED.article_count >= topic_daily_stats.article_count
                                     THEN EXCLUDED.avg_sentiment ELSE topic_daily_stats.avg_sentiment END,
                label         = EXCLUDED.label,
                updated_at    = now()
        RETURNING 1
    )
    SELECT count(*)::int FROM up;
$$;
