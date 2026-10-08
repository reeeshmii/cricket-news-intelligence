"""Quality report over the locally stored data:  python -m src.crawler.report"""
import json
from collections import defaultdict
from statistics import mean

from .storage import LocalStore


def main():
    store = LocalStore()
    arts = store.articles
    print(f"Data folder : {store.dir}")
    print(f"Articles    : {len(arts)} (cap {store.max_articles}) | seen-memory: {len(store._urls)} URLs")
    if not arts:
        print("No articles stored yet. Run: python -m src.crawler.crawl --source wisden --limit 5")
        return
    by_src = defaultdict(list)
    for a in arts:
        by_src[a["source"]].append(a)
    for src, items in by_src.items():
        n = len(items)
        dates = sorted(a["published_at"] for a in items if a["published_at"])
        print(f"\n[{src}] {n} articles")
        print(f"  missing author : {sum(not a['author'] for a in items)} ({sum(not a['author'] for a in items)/n:.0%})")
        print(f"  missing date   : {sum(not a['published_at'] for a in items)}")
        print(f"  words          : avg {mean(a['word_count'] for a in items):.0f}, "
              f"min {min(a['word_count'] for a in items)}, max {max(a['word_count'] for a in items)}")
        if dates:
            print(f"  published      : {dates[0][:16]}  ->  {dates[-1][:16]}")
        print(f"  duplicate hashes inside store: {n - len({a['content_hash'] for a in items})}")
    print("\nLast crawl runs:")
    if store.log_path.exists():
        for line in store.log_path.read_text("utf-8").splitlines()[-5:]:
            r = json.loads(line)
            print(f"  {r['started_at'][:19]}  " + " | ".join(
                f"{s}: " + ", ".join(f"{k}={v}" for k, v in c.items()) for s, c in r["sources"].items()))


if __name__ == "__main__":
    main()
