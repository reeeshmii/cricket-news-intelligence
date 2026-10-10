"""Run every stage once, in order (handy for demos; GitHub Actions runs them on a schedule).

  python run_pipeline.py              # crawl -> NLP -> topics, into Neon
  python run_pipeline.py --refit      # same, but force a full topic re-fit
  python run_pipeline.py --limit 5    # fewer new pages per source
"""
import argparse

from src.cluster.run import run_once as cluster_once
from src.crawler.crawl import make_store, run_crawl
from src.crawler.sources import REGISTRY
from src.nlp.run import run_once as nlp_once


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=10, help="max new pages per source")
    ap.add_argument("--refit", action="store_true", help="force a full topic re-fit")
    a = ap.parse_args()

    print("== 1/3 crawl")
    store = make_store("neon")
    try:
        run_crawl(list(REGISTRY), limit=a.limit, days=3, store=store)
    finally:
        store.close()
    print("== 2/3 NLP")
    nlp_once()
    print("== 3/3 topics")
    cluster_once("fit" if a.refit else "auto")


if __name__ == "__main__":
    main()
