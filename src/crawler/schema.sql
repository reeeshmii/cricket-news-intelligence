-- Tables the crawler writes to. Idempotent: NeonStore runs this on every connect.
-- sources / articles / crawl_runs match db/schema.sql (database branch) so the NLP stage
-- reads the same `articles` table. seen_articles is crawler-only.

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

-- Small memory of every URL ever processed (stored, rejected, duplicate, evicted), so the
-- rolling cap never causes an old article to be fetched and inserted again.
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
ALTER TABLE crawl_runs ADD COLUMN IF NOT EXISTS details JSONB;   -- full per-reason counts
