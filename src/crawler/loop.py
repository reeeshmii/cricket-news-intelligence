"""Run the crawler continuously.

  python -m src.crawler.loop --every 30 --limit 10                 # local storage, every 30 min
  python -m src.crawler.loop --every 30 --limit 10 --store neon    # Neon PostgreSQL
  python -m src.crawler.loop --every 30 --max-runs 2               # stop after 2 runs (testing)

Stop with Ctrl+C. Each cycle: take the lock -> crawl all sources -> release -> sleep.
A failing cycle is logged and the loop carries on. Progress is written to
data/crawler_status.json and data/crawler.log.
"""
import argparse
import logging
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler

from . import settings
from .crawl import make_store, run_crawl
from .lock import CrawlerBusy, crawl_lock, update_status
from .sources import REGISTRY

MIN_EVERY_MINUTES = 5     # politeness floor: sites publish a few articles per hour at most
log = logging.getLogger("crawler")


def setup_logging() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler = RotatingFileHandler(settings.DATA_DIR / "crawler.log", maxBytes=1_000_000,
                                       backupCount=3, encoding="utf-8")
    console = logging.StreamHandler(sys.stdout)
    for h in (file_handler, console):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def run_once(sources, limit, days, store_kind, max_articles=None) -> dict | None:
    """One locked crawl cycle. Never raises: errors are logged and recorded in the status file."""
    try:
        with crawl_lock():
            store = make_store(store_kind, max_articles)
            try:
                if not store.try_lock():        # Neon: another machine is crawling right now
                    raise CrawlerBusy(f"another crawl is writing to {store.location}")
                update_status(state="running", last_started_at=datetime.now(timezone.utc).isoformat())
                summary = run_crawl(sources, limit, days, store=store, echo=log.info)
            finally:
                store.close()
            new = sum(s.get("new", 0) for s in summary["sources"].values())
            update_status(state="idle", last_finished_at=summary["finished_at"], last_new_articles=new,
                          last_summary=summary, stored_total=summary["stored_total"], last_error=None)
            return summary
    except CrawlerBusy as e:
        log.warning("%s; skipping this cycle", e)
    except Exception as e:
        log.exception("crawl cycle failed")
        update_status(state="error", last_error=f"{type(e).__name__}: {e}")
    return None


def run_loop(cycle, every_seconds: float, max_runs: int | None = None, sleep=time.sleep,
             jitter: float = 0.1) -> int:
    """Call cycle() repeatedly; returns the number of runs. `sleep` is injectable for tests."""
    runs = 0
    while True:
        cycle()
        runs += 1
        if max_runs and runs >= max_runs:
            return runs
        delay = every_seconds * (1 + random.uniform(-jitter, jitter))   # avoid hitting sites on the dot
        next_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        update_status(next_run_at=next_at.isoformat())
        log.info("next run at %s (in %.0f min)", next_at.astimezone().strftime("%H:%M:%S"), delay / 60)
        sleep(delay)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--every", type=float, default=30, help=f"minutes between runs (min {MIN_EVERY_MINUTES})")
    ap.add_argument("--source", action="append", choices=list(REGISTRY), help="repeatable; default all")
    ap.add_argument("--limit", type=int, default=10, help="max NEW pages per source per run")
    ap.add_argument("--days", type=int, default=3, help="only consider articles from the last N days")
    ap.add_argument("--store", choices=["local", "neon"], default=settings.STORE)
    ap.add_argument("--max-articles", type=int, help=f"rolling cap (default {settings.MAX_ARTICLES})")
    ap.add_argument("--max-runs", type=int, help="stop after N runs (default: run forever)")
    a = ap.parse_args()
    if a.every < MIN_EVERY_MINUTES:
        ap.error(f"--every must be at least {MIN_EVERY_MINUTES} minutes")

    setup_logging()
    sources = a.source or list(REGISTRY)
    log.info("crawler loop started: every %s min, store=%s, sources=%s", a.every, a.store, ",".join(sources))
    try:
        run_loop(lambda: run_once(sources, a.limit, a.days, a.store, a.max_articles),
                 a.every * 60, a.max_runs)
    except KeyboardInterrupt:
        log.info("stopped by user")
    finally:
        update_status(state="stopped", next_run_at=None)


if __name__ == "__main__":
    main()
