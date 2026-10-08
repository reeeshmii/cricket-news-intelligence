"""Crawler entry point.

  python -m src.crawler.crawl --source wisden --limit 5 --dry-run     # print JSON, store nothing
  python -m src.crawler.crawl --source wisden --limit 20              # store in data/ (local)
  python -m src.crawler.crawl --source wisden --limit 5 --save-html   # also keep raw pages
  python -m src.crawler.crawl --limit 10 --store neon                  # store in Neon PostgreSQL
  python -m src.crawler.loop --every 30                               # run continuously (see loop.py)

Flow per article: discover -> skip if already seen -> fetch (robots + delay) -> extract
-> validate (+T20 filter) -> exact-hash check -> near-duplicate check -> store (rolling cap).
Re-running is safe: known URLs are never fetched again and duplicates are never stored.
"""
import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import settings
from .dedup import canonicalize_url, content_hash, simhash
from .extract import extract_article
from .http import Fetcher, FetchError, RobotsDisallowed
from .sources import REGISTRY, get_source
from .lock import CrawlerBusy, crawl_lock
from .storage import LocalStore
from .validate import validate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def crawl_source(source, fetcher, store, limit: int, days: int, dry_run: bool = False,
                 save_html: bool = False, echo=print) -> Counter:
    stats = Counter()
    mark_seen = (lambda *a, **k: None) if dry_run else store.mark_seen   # dry run writes nothing
    cutoff = _now() - timedelta(days=days)
    candidates = source.discover(fetcher)
    stats["found"] = len(candidates)
    fetched = 0

    for cand in candidates:
        if fetched >= limit:
            break
        if cand.lastmod and cand.lastmod < cutoff:
            stats["too_old"] += 1
            continue
        curl = canonicalize_url(cand.url)
        if store.seen_url(curl):                       # dedup layer 1: before any download
            stats["already_seen"] += 1
            continue

        fetched += 1
        try:
            html = source.fetch_article(fetcher, curl)
        except RobotsDisallowed:
            stats["robots_blocked"] += 1
            mark_seen(curl, "robots_blocked")
            continue
        except FetchError as e:
            stats["errors"] += 1
            echo(f"  ! fetch failed: {e}")
            continue                                   # not marked seen -> retried next run

        doc = extract_article(html, curl)
        if doc is None:
            stats["errors"] += 1
            echo(f"  ! no article text: {curl}")
            continue
        page_url = canonicalize_url(doc["canonical_url"])
        reason = validate(doc, page_url)
        if reason:
            stats[f"rejected_{reason}"] += 1
            mark_seen(curl, reason)
            continue
        if page_url != curl and store.seen_url(page_url):
            stats["already_seen"] += 1
            mark_seen(curl, "alias")
            continue

        chash = content_hash(doc["title"], doc["body"])          # dedup layer 2
        if store.url_for_hash(chash):
            stats["duplicate_exact"] += 1
            mark_seen(curl, "duplicate_exact")
            continue
        sh = simhash(doc["body"])                                # dedup layer 3
        if (near := store.near_duplicate(sh)):
            stats["duplicate_near"] += 1
            mark_seen(curl, f"duplicate_of:{near}", chash)
            continue

        article = {
            "source": source.name, "url": cand.url, "canonical_url": page_url,
            "title": doc["title"], "author": doc["author"], "published_at": doc["published_at"],
            "body": doc["body"], "word_count": len(doc["body"].split()),
            "content_hash": chash, "simhash": sh, "scraped_at": _now().isoformat(),
        }
        stats["new"] += 1
        echo(f"  + {article['title'][:90]}  ({article['word_count']} words)")
        if dry_run:
            echo(json.dumps({**article, "body": article["body"][:300] + "..."}, indent=2, ensure_ascii=False))
            continue
        if save_html:
            raw = settings.DATA_DIR / "raw_html"
            raw.mkdir(parents=True, exist_ok=True)
            (raw / (hashlib.sha1(page_url.encode()).hexdigest()[:16] + ".html")).write_text(html, encoding="utf-8")
        stats["evicted"] += store.add(article)
    return stats


def run_crawl(source_names, limit=20, days=3, dry_run=False, save_html=False,
              fetcher=None, store=None, echo=print) -> dict:
    fetcher = fetcher or Fetcher()
    store = store or LocalStore()
    if not dry_run and not store.try_lock():
        raise CrawlerBusy(f"another crawl is writing to {store.location}")
    summary = {"started_at": _now().isoformat(), "dry_run": dry_run, "sources": {}, "errors": {}}
    for name in source_names:
        echo(f"[{name}] crawling (limit={limit}, last {days} days{', DRY RUN' if dry_run else ''})")
        try:
            stats = crawl_source(get_source(name), fetcher, store, limit, days, dry_run, save_html, echo)
        except Exception as e:                  # one broken site must not stop the others
            summary["errors"][name] = f"{type(e).__name__}: {e}"
            summary["sources"][name] = {}
            echo(f"[{name}] FAILED: {summary['errors'][name]}")
            continue
        finally:
            if not dry_run:
                store.save()                    # keep whatever this source produced
        summary["sources"][name] = dict(stats)
        echo(f"[{name}] " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    summary["finished_at"] = _now().isoformat()
    summary["stored_total"] = store.count()
    if not dry_run:
        store.log_run(summary)
        echo(f"Stored articles: {summary['stored_total']} (cap {store.max_articles}) in {store.location}")
    return summary


def make_store(kind: str | None = None, max_articles: int | None = None):
    kind = kind or settings.STORE
    if kind == "neon":
        from .neon_store import NeonStore      # imported lazily: local mode needs no database driver
        return NeonStore(max_articles=max_articles)
    if kind == "local":
        return LocalStore(max_articles=max_articles)
    raise ValueError(f"unknown store '{kind}' (use 'local' or 'neon')")


def run() -> dict:
    """Used by run_pipeline.py."""
    store = make_store()
    try:
        return run_crawl(list(REGISTRY), limit=20, days=3, store=store)
    finally:
        store.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="append", choices=list(REGISTRY),
                    help="source to crawl (repeatable; default: all registered)")
    ap.add_argument("--limit", type=int, default=20, help="max NEW pages to download per source")
    ap.add_argument("--days", type=int, default=3, help="only consider articles modified in the last N days")
    ap.add_argument("--dry-run", action="store_true", help="print extracted articles, store nothing")
    ap.add_argument("--save-html", action="store_true", help="keep raw HTML under data/raw_html/")
    ap.add_argument("--store", choices=["local", "neon"], default=settings.STORE,
                    help=f"where to store articles (default: {settings.STORE})")
    ap.add_argument("--max-articles", type=int, help=f"rolling cap (default {settings.MAX_ARTICLES})")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sources = a.source or list(REGISTRY)
    if a.dry_run:                               # dry runs read the store but never write to it
        store = make_store(a.store, a.max_articles)
        try:
            run_crawl(sources, a.limit, a.days, dry_run=True, store=store)
        finally:
            store.close()
        return
    try:
        with crawl_lock():
            store = make_store(a.store, a.max_articles)
            try:
                summary = run_crawl(sources, a.limit, a.days, False, a.save_html, store=store)
            finally:
                store.close()
    except CrawlerBusy as e:
        print(f"Skipped: {e}")                  # not an error: the other crawl does the work
        return
    if len(summary["errors"]) == len(sources):     # every source failed -> non-zero exit (CI shows red)
        sys.exit("all sources failed: " + "; ".join(f"{k}: {v}" for k, v in summary["errors"].items()))


if __name__ == "__main__":
    main()
