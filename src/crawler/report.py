"""Quality report:  python -m src.crawler.report [--store local|neon]"""
import argparse
import sys
from collections import defaultdict
from statistics import mean

from . import settings
from .crawl import make_store


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", choices=["local", "neon"], default=settings.STORE)
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    store = make_store(a.store)
    try:
        arts = store.rows()
        print(f"Store       : {store.location}")
        print(f"Articles    : {len(arts)} (cap {store.max_articles}) | seen-memory: {store.seen_count()} URLs")
        if not arts:
            print(f"No articles stored yet. Run: python -m src.crawler.crawl --limit 5 --store {a.store}")
            return
        by_src = defaultdict(list)
        for x in arts:
            by_src[x["source"]].append(x)
        for src, items in sorted(by_src.items()):
            n = len(items)
            no_author = sum(not x["author"] for x in items)
            words = [x["word_count"] for x in items]
            dates = sorted(x["published_at"] for x in items if x["published_at"])
            print(f"\n[{src}] {n} articles")
            print(f"  missing author : {no_author} ({no_author / n:.0%})")
            print(f"  missing date   : {n - len(dates)}")
            print(f"  words          : avg {mean(words):.0f}, min {min(words)}, max {max(words)}")
            if dates:
                print(f"  published      : {dates[0][:16]}  ->  {dates[-1][:16]}")
            print(f"  duplicate hashes inside store: {n - len({x['content_hash'] for x in items})}")
        print("\nLast crawl runs:")
        for r in store.recent_runs(5):
            print(f"  {r['started_at'][:19]}  " + " | ".join(
                f"{s}: " + ", ".join(f"{k}={v}" for k, v in c.items()) for s, c in r["sources"].items()))
    finally:
        store.close()


if __name__ == "__main__":
    main()
