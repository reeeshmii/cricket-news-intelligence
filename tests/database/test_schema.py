"""Database schema tests.

Offline tests always run. Tests marked needs_db run against your Neon database inside a
throwaway schema (dropped afterwards) over a DIRECT connection, so nothing leaks through
the pooler and your real tables are never touched.
"""
import re
import uuid
from pathlib import Path

import pytest
from psycopg import sql

from src import config
from src.db import connect, direct_dsn
from src.init_db import SCHEMA_PATH, apply_schema

ROOT = Path(__file__).resolve().parents[2]
CRAWLER_SCHEMA = ROOT / "src" / "crawler" / "schema.sql"
CRAWLER_TABLES = ["sources", "articles", "seen_articles", "crawl_runs"]
needs_db = pytest.mark.skipif(not config.DATABASE_URL, reason="DATABASE_URL not set in .env")


def _statements(path: Path) -> dict[str, str]:
    """CREATE TABLE statements by table name, with comments and whitespace normalised."""
    text = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))
    out = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\);", text, re.S):
        out[m.group(1)] = re.sub(r"\s+", " ", m.group(2)).strip()
    return out


# ------------------------------ offline ------------------------------
def test_crawler_tables_are_identical_in_both_schema_files():
    full, crawler = _statements(SCHEMA_PATH), _statements(CRAWLER_SCHEMA)
    for t in CRAWLER_TABLES:
        assert full[t] == crawler[t], f"table {t} differs between db/schema.sql and src/crawler/schema.sql"


def test_every_reference_to_articles_cascades():
    """The crawler's rolling cap deletes articles; dependent rows must follow, not block it."""
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    refs = re.findall(r"(\w+)\s+BIGINT[^,\n]*REFERENCES articles\(id\)([^,\n]*)", text)
    assert refs, "expected foreign keys to articles"
    for column, rest in refs:
        if column != "duplicate_of":                 # crawler never sets it (near-dups are not stored)
            assert "ON DELETE CASCADE" in rest, f"{column} must use ON DELETE CASCADE"


def test_direct_dsn():
    pooled = "postgresql://u:p@ep-abc-pooler.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
    assert direct_dsn(pooled) == "postgresql://u:p@ep-abc.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"


# ------------------------------ against Neon (throwaway schema) ------------------------------
@pytest.fixture
def conn():
    schema = f"db_test_{uuid.uuid4().hex[:8]}"
    c = connect(autocommit=True, direct=True)
    try:
        apply_schema(c, schema)
        yield c
    finally:
        c.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        c.close()


def _vec(x: float) -> str:
    return "[" + ",".join([str(x)] * 384) + "]"


def _article(c, n: int, source_id: int, day: str = "2026-10-08") -> int:
    return c.execute(
        "INSERT INTO articles(source_id, url, canonical_url, title, published_at, body, content_hash) "
        "VALUES (%s, %s, %s, %s, %s, 'body', %s) RETURNING id",
        (source_id, f"https://s/{n}", f"https://s/{n}", f"IPL {n}", f"{day}T10:00:00+00", f"h{n}")).fetchone()[0]


@needs_db
def test_schema_is_idempotent(conn):
    apply_schema(conn)                              # second run on the same schema
    apply_schema(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()")}
    assert {"articles", "article_nlp", "article_vectors", "clusters", "topic_daily_stats",
            "v_article_topics", "v_pipeline_status"} <= tables


@needs_db
def test_crawler_first_then_full_schema(conn):
    """Production order: the crawler created its tables first, init_db runs afterwards."""
    schema = f"db_test_{uuid.uuid4().hex[:8]}"
    try:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        conn.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        conn.execute(CRAWLER_SCHEMA.read_text(encoding="utf-8"))
        conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))      # must not fail
        conn.execute(CRAWLER_SCHEMA.read_text(encoding="utf-8"))   # and the crawler keeps working
    finally:
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


@needs_db
def test_deleting_an_article_cascades_to_every_stage(conn):
    sid = conn.execute("INSERT INTO sources(name, base_url) VALUES ('t', '') RETURNING id").fetchone()[0]
    aid = _article(conn, 1, sid)
    mid = conn.execute("INSERT INTO cluster_models(algorithm, is_active) VALUES ('k', TRUE) RETURNING id").fetchone()[0]
    cid = conn.execute("INSERT INTO clusters(model_id, label, centroid) VALUES (%s, 'auction', %s) RETURNING id",
                       (mid, _vec(0.1))).fetchone()[0]
    conn.execute("INSERT INTO article_nlp(article_id, lemmas) VALUES (%s, 'ipl auction')", (aid,))
    conn.execute("INSERT INTO article_vectors(article_id, model, embedding) VALUES (%s, 'm', %s)", (aid, _vec(0.2)))
    conn.execute("INSERT INTO article_clusters(article_id, cluster_id, score) VALUES (%s, %s, 0.9)", (aid, cid))

    conn.execute("DELETE FROM articles WHERE id = %s", (aid,))     # what the rolling cap does
    for t in ("article_nlp", "article_vectors", "article_clusters"):
        assert conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(t))).fetchone()[0] == 0


@needs_db
def test_only_one_active_model(conn):
    conn.execute("INSERT INTO cluster_models(algorithm, is_active) VALUES ('a', TRUE)")
    with pytest.raises(Exception):
        conn.execute("INSERT INTO cluster_models(algorithm, is_active) VALUES ('b', TRUE)")


@needs_db
def test_trend_history_survives_rolling_cap(conn):
    sid = conn.execute("INSERT INTO sources(name, base_url) VALUES ('t', '') RETURNING id").fetchone()[0]
    mid = conn.execute("INSERT INTO cluster_models(algorithm, is_active) VALUES ('k', TRUE) RETURNING id").fetchone()[0]
    cid = conn.execute("INSERT INTO clusters(model_id, label, centroid) VALUES (%s, 'auction', %s) RETURNING id",
                       (mid, _vec(0.1))).fetchone()[0]
    ids = [_article(conn, n, sid) for n in range(3)]
    for aid in ids:
        conn.execute("INSERT INTO article_clusters(article_id, cluster_id) VALUES (%s, %s)", (aid, cid))

    assert conn.execute("SELECT refresh_topic_daily_stats()").fetchone()[0] == 1
    conn.execute("DELETE FROM articles WHERE id = ANY(%s)", (ids[:2],))   # cap evicts 2 of the 3
    conn.execute("SELECT refresh_topic_daily_stats()")
    row = conn.execute("SELECT day::text, label, article_count FROM topic_daily_stats").fetchone()
    assert row == ("2026-10-08", "auction", 3)                            # history kept

    live = conn.execute("SELECT articles FROM v_topic_daily").fetchone()[0]
    assert live == 1                                                      # live view shows what is left


@needs_db
def test_pipeline_status_view(conn):
    sid = conn.execute("INSERT INTO sources(name, base_url) VALUES ('t', '') RETURNING id").fetchone()[0]
    _article(conn, 1, sid)
    status = conn.execute("SELECT articles_total, waiting_for_nlp, active_model_id FROM v_pipeline_status").fetchone()
    assert status == (1, 1, None)
