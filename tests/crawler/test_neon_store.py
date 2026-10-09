"""Runs against your real Neon database, inside a throwaway schema that is dropped afterwards.
Skipped automatically when DATABASE_URL is not set in .env."""
import uuid
from datetime import datetime, timezone

import pytest

from src import config

needs_db = pytest.mark.skipif(not config.DATABASE_URL, reason="DATABASE_URL not set in .env")


@pytest.fixture
def store_factory():
    from src.crawler.neon_store import NeonStore
    schema = f"crawler_test_{uuid.uuid4().hex[:8]}"
    opened = []

    def make(**kw):
        s = NeonStore(schema=schema, **kw)
        opened.append(s)
        return s

    yield make
    for s in opened:
        if not s.conn.closed:
            s.close()
    cleanup = NeonStore(schema=schema)
    cleanup.conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
    cleanup.close()


def _article(i):
    return {"source": "fake", "url": f"https://s.test/{i}", "canonical_url": f"https://s.test/{i}",
            "title": f"IPL story {i}", "author": None, "published_at": "2026-10-07T10:00:00+00:00",
            "body": f"body {i}", "word_count": 2, "content_hash": f"hash{i}", "simhash": i * 104729,
            "scraped_at": datetime.now(timezone.utc).isoformat()}


@needs_db
def test_rolling_cap_and_seen_memory_persist(store_factory):
    s = store_factory(max_articles=3)
    evicted = sum(s.add(_article(i)) for i in range(5))
    assert evicted == 2 and s.count() == 3
    urls = [r[0] for r in s.conn.execute("SELECT canonical_url FROM articles ORDER BY id")]
    assert urls == ["https://s.test/2", "https://s.test/3", "https://s.test/4"]
    s.close()

    fresh = store_factory(max_articles=3)                     # new connection = new process
    assert fresh.seen_url("https://s.test/0")                 # evicted but remembered
    assert fresh.url_for_hash("hash4") == "https://s.test/4"


@needs_db
def test_crawl_twice_against_neon_inserts_once(store_factory):
    from src.crawler.crawl import crawl_source
    from tests.crawler.test_crawler import BODY, FakeSource, _page
    src = FakeSource({"https://s.test/a": _page("IPL auction recap", BODY, "https://s.test/a"),
                      "https://s.test/a-copy": _page("IPL auction recap", BODY, "https://s.test/a-copy")})
    first = crawl_source(src, None, store_factory(), limit=10, days=3, echo=lambda *_: None)
    second = crawl_source(src, None, store_factory(), limit=10, days=3, echo=lambda *_: None)
    assert first["new"] == 1 and first["duplicate_exact"] == 1
    assert second["new"] == 0 and second["already_seen"] == 2


@needs_db
def test_dry_run_writes_nothing_to_neon(store_factory):
    from src.crawler.crawl import crawl_source
    from tests.crawler.test_crawler import BODY, FakeSource, _page
    s = store_factory()
    src = FakeSource({"https://s.test/a": _page("IPL auction recap", BODY, "https://s.test/a")})
    crawl_source(src, None, s, limit=5, days=3, dry_run=True, echo=lambda *_: None)
    assert s.count() == 0
    assert s.conn.execute("SELECT count(*) FROM seen_articles").fetchone()[0] == 0


def test_direct_dsn_strips_pooler_only_from_host():
    from src.crawler.neon_store import direct_dsn
    pooled = "postgresql://u:p@ep-abc-pooler.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
    assert direct_dsn(pooled) == "postgresql://u:p@ep-abc.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
    assert direct_dsn("postgresql://u:p@localhost/db") == "postgresql://u:p@localhost/db"


@needs_db
def test_only_one_writer_at_a_time(store_factory):
    from src.crawler.crawl import run_crawl
    from src.crawler.lock import CrawlerBusy
    first, second = store_factory(), store_factory()
    assert first.try_lock()
    with pytest.raises(CrawlerBusy):
        run_crawl([], store=second, echo=lambda *_: None)
    first.close()                                   # lock released with the connection...
    import time
    for _ in range(20):                             # ...once the server has ended that session
        if second.try_lock():
            break
        time.sleep(0.25)
    else:
        pytest.fail("advisory lock was not released after closing the first connection")
