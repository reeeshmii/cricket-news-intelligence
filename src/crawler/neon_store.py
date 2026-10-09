"""Neon PostgreSQL store: same interface as LocalStore, so the crawler code is identical.

Every write commits immediately (autocommit; insert + cap run in one transaction), so a
crash or Ctrl+C never leaves half-written data. Seen URLs / hashes and recent SimHashes are
cached in memory at connect time, so duplicate checks cost no extra round trips to Neon.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from .. import config
from . import settings
from .dedup import hamming

CRAWL_LOCK_KEY = 7_202_026            # arbitrary app-wide id for pg_try_advisory_lock
SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")


def direct_dsn(dsn: str) -> str:
    """Neon's pooled host (ep-x-pooler.region...) -> direct host (ep-x.region...).

    The pooler runs PgBouncer in transaction mode, where session settings such as
    search_path leak between clients. A crawler holds one long session, which is what the
    direct endpoint is for."""
    parts = urlsplit(dsn)
    if parts.hostname and "-pooler." in parts.hostname:
        return urlunsplit(parts._replace(netloc=parts.netloc.replace("-pooler.", ".", 1)))
    return dsn


def _ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class NeonStore:
    def __init__(self, dsn: str | None = None, max_articles: int | None = None,
                 seen_max: int | None = None, schema: str | None = None):
        dsn = dsn or config.DATABASE_URL
        if not dsn:
            raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and paste your "
                               "Neon connection string.")
        self.max_articles = max_articles or settings.MAX_ARTICLES
        self.seen_max = seen_max or settings.SEEN_MAX
        self.conn = psycopg.connect(direct_dsn(dsn), autocommit=True, connect_timeout=20)
        schema = schema or "public"                  # tests pass a throwaway schema
        if schema != "public":
            self.conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        self.conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        self.conn.execute(SCHEMA_SQL)

        self._urls = {r[0] for r in self.conn.execute("SELECT url FROM seen_articles")}
        self._hashes = dict(self.conn.execute(
            "SELECT content_hash, url FROM seen_articles WHERE content_hash IS NOT NULL").fetchall())
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.NEAR_DUP_WINDOW_DAYS)
        self._recent = self.conn.execute(
            "SELECT canonical_url, simhash, scraped_at FROM articles WHERE scraped_at >= %s "
            "AND simhash IS NOT NULL", (cutoff,)).fetchall()
        self._source_ids: dict[str, int] = {}

    # ---- common store interface ------------------------------------------------------
    @property
    def location(self) -> str:
        info = self.conn.info
        return f"Neon ({info.host}/{info.dbname})"

    def count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM articles").fetchone()[0]

    def seen_count(self) -> int:
        return len(self._urls)

    def rows(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT s.name AS source, a.author, a.published_at, a.word_count, a.content_hash "
            "FROM articles a LEFT JOIN sources s ON s.id = a.source_id ORDER BY a.id")
        cols = [c.name for c in cur.description]
        return [{**dict(zip(cols, r)),
                 "published_at": r[2].isoformat() if r[2] else None} for r in cur.fetchall()]

    def recent_runs(self, n: int = 5) -> list[dict]:
        cur = self.conn.execute(
            "SELECT r.started_at, s.name, r.details FROM crawl_runs r LEFT JOIN sources s "
            "ON s.id = r.source_id ORDER BY r.id DESC LIMIT %s", (n * 10,))
        runs: dict[str, dict] = {}
        for started, name, details in cur.fetchall():
            key = started.isoformat()
            runs.setdefault(key, {"started_at": key, "sources": {}})["sources"][name] = details or {}
        return list(runs.values())[:n][::-1]

    def try_lock(self) -> bool:
        """Cross-machine "one crawl at a time" (laptop loop vs GitHub Actions).
        Session-level advisory lock: released automatically when the connection closes."""
        return self.conn.execute("SELECT pg_try_advisory_lock(%s)", (CRAWL_LOCK_KEY,)).fetchone()[0]

    def close(self) -> None:
        self.conn.close()

    # ---- lookups ---------------------------------------------------------------------
    def seen_url(self, canonical_url: str) -> bool:
        return canonical_url in self._urls

    def url_for_hash(self, content_hash: str) -> str | None:
        return self._hashes.get(content_hash)

    def near_duplicate(self, simhash: int, now: datetime | None = None) -> str | None:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=settings.NEAR_DUP_WINDOW_DAYS)
        for url, other, scraped_at in self._recent:
            if scraped_at >= cutoff and hamming(simhash, other) <= settings.NEAR_DUP_HAMMING:
                return url
        return None

    # ---- writes ----------------------------------------------------------------------
    def mark_seen(self, canonical_url: str, outcome: str, content_hash: str | None = None) -> None:
        self._mark_seen_sql(canonical_url, outcome, content_hash)
        self._urls.add(canonical_url)
        if content_hash:
            self._hashes[content_hash] = canonical_url

    def _mark_seen_sql(self, url, outcome, content_hash):
        self.conn.execute(
            "INSERT INTO seen_articles(url, outcome, content_hash) VALUES (%s, %s, %s) "
            "ON CONFLICT (url) DO UPDATE SET outcome = EXCLUDED.outcome, seen_at = now(), "
            "content_hash = COALESCE(EXCLUDED.content_hash, seen_articles.content_hash)",
            (url, outcome, content_hash))

    def add(self, article: dict) -> int:
        """Insert + enforce the rolling cap in one transaction. Returns number evicted."""
        source_id = self._source_id(article["source"], article["url"])
        with self.conn.transaction():
            self.conn.execute(
                """INSERT INTO articles(source_id, url, canonical_url, title, author, published_at,
                                        scraped_at, body, word_count, content_hash, simhash)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (source_id, article["url"], article["canonical_url"], article["title"], article["author"],
                 _ts(article["published_at"]), _ts(article["scraped_at"]), article["body"],
                 article["word_count"], article["content_hash"], article["simhash"]))
            self._mark_seen_sql(article["canonical_url"], "stored", article["content_hash"])
            evicted = self.conn.execute(
                "DELETE FROM articles WHERE id IN (SELECT id FROM articles ORDER BY id DESC OFFSET %s)",
                (self.max_articles,)).rowcount      # oldest-added first; seen_articles keeps them
        self._urls.add(article["canonical_url"])
        self._hashes[article["content_hash"]] = article["canonical_url"]
        self._recent.append((article["canonical_url"], article["simhash"], _ts(article["scraped_at"])))
        return max(evicted, 0)

    def save(self) -> None:
        """Writes are already committed; just keep the seen-memory within its cap."""
        self.conn.execute(
            "DELETE FROM seen_articles WHERE url IN "
            "(SELECT url FROM seen_articles ORDER BY seen_at DESC OFFSET %s)", (self.seen_max,))

    def log_run(self, summary: dict) -> None:
        for name, stats in summary["sources"].items():
            failed = name in summary.get("errors", {})
            details = {**stats, **({"failed": summary["errors"][name]} if failed else {})}
            dups = stats.get("duplicate_exact", 0) + stats.get("duplicate_near", 0)
            new, errors = stats.get("new", 0), stats.get("errors", 0) + int(failed)
            skipped = sum(v for k, v in stats.items()
                          if k not in ("found", "new", "errors", "evicted", "duplicate_exact", "duplicate_near"))
            sid = self._source_id(name)
            self.conn.execute(
                """INSERT INTO crawl_runs(source_id, started_at, finished_at, found, inserted, skipped,
                                          duplicates, errors, details)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (sid, _ts(summary["started_at"]), _ts(summary["finished_at"]), stats.get("found", 0),
                 new, skipped, dups, errors, Jsonb(details)))
            if not failed:
                self.conn.execute("UPDATE sources SET last_crawled_at = %s WHERE id = %s",
                                  (_ts(summary["finished_at"]), sid))

    # ---- helpers ---------------------------------------------------------------------
    def _source_id(self, name: str, url: str | None = None) -> int:
        if name not in self._source_ids:
            base = "{0.scheme}://{0.netloc}".format(urlsplit(url)) if url else ""
            self._source_ids[name] = self.conn.execute(
                "INSERT INTO sources(name, base_url) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE "
                "SET base_url = CASE WHEN sources.base_url = '' THEN EXCLUDED.base_url "
                "ELSE sources.base_url END RETURNING id", (name, base)).fetchone()[0]
        return self._source_ids[name]
