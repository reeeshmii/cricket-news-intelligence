import json
import os
import time

import pytest

from src.crawler import loop as loop_mod
from src.crawler.crawl import run_crawl
from src.crawler.lock import CrawlerBusy, crawl_lock, update_status
from src.crawler.sources import REGISTRY
from src.crawler.storage import LocalStore
from tests.crawler.test_crawler import BODY, FakeSource, _page


def test_lock_blocks_second_crawl_and_is_released(tmp_path):
    lock = tmp_path / "crawler.lock"
    with crawl_lock(lock):
        assert lock.exists()
        with pytest.raises(CrawlerBusy):
            with crawl_lock(lock):
                pass
    assert not lock.exists()


def test_stale_lock_from_crashed_run_is_replaced(tmp_path):
    lock = tmp_path / "crawler.lock"
    lock.write_text("{}")
    old = time.time() - 10_000
    os.utime(lock, (old, old))
    with crawl_lock(lock, stale_after=3600):
        assert json.loads(lock.read_text())["pid"] == os.getpid()


def test_status_file_merges_fields(tmp_path):
    p = tmp_path / "status.json"
    update_status(p, state="running")
    update_status(p, last_new_articles=4)
    s = json.loads(p.read_text())
    assert s["state"] == "running" and s["last_new_articles"] == 4 and "updated_at" in s


def test_loop_runs_cycles_and_sleeps_between(monkeypatch, tmp_path):
    monkeypatch.setattr(loop_mod, "update_status", lambda **k: None)
    calls, sleeps = [], []
    runs = loop_mod.run_loop(lambda: calls.append(1), every_seconds=600, max_runs=3,
                             sleep=sleeps.append, jitter=0.1)
    assert runs == 3 and len(calls) == 3
    assert len(sleeps) == 2 and all(540 <= s <= 660 for s in sleeps)   # no sleep after the last run


def test_one_failing_source_does_not_stop_the_others(monkeypatch, tmp_path):
    class Broken(FakeSource):
        name = "broken"

        def discover(self, fetcher):
            raise RuntimeError("site is down")

    good = FakeSource({"https://s.test/a": _page("IPL auction recap", BODY, "https://s.test/a")})
    monkeypatch.setitem(REGISTRY, "broken", Broken({}))
    monkeypatch.setitem(REGISTRY, "fake", good)
    store = LocalStore(tmp_path)
    summary = run_crawl(["broken", "fake"], limit=5, days=3, store=store, echo=lambda *_: None)
    assert "site is down" in summary["errors"]["broken"]
    assert summary["sources"]["fake"]["new"] == 1
    assert LocalStore(tmp_path).count() == 1                         # saved despite the failure


def test_busy_neon_lock_skips_cycle_without_marking_running(monkeypatch, tmp_path):
    class BusyStore(LocalStore):
        def try_lock(self):
            return False

    statuses = []
    monkeypatch.setattr(loop_mod, "update_status", lambda **k: statuses.append(k))
    monkeypatch.setattr(loop_mod, "crawl_lock", lambda: __import__("contextlib").nullcontext())
    monkeypatch.setattr(loop_mod, "make_store", lambda *a: BusyStore(tmp_path))
    assert loop_mod.run_once(["wisden"], 1, 1, "local") is None
    assert not any(s.get("state") == "running" for s in statuses)
