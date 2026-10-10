"""One-time backfill of articles.image_url for articles stored before images were collected.

  python -m src.crawler.backfill_images            # all stored articles without an image
  python -m src.crawler.backfill_images --limit 10

Re-fetches each article page politely (robots.txt, per-site delay) and stores its og:image.
New articles get their image during the normal crawl, so this only needs to run once.
"""
import argparse
import sys

from bs4 import BeautifulSoup

from ..db import connect
from .extract import image_url
from .http import FetchError, Fetcher


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="max articles to process")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    fetcher = Fetcher()
    found = missing = failed = 0
    with connect(autocommit=True, direct=True) as conn:
        rows = conn.execute("SELECT id, canonical_url FROM articles WHERE image_url IS NULL ORDER BY id DESC "
                            "LIMIT %s", (a.limit,)).fetchall()
        print(f"{len(rows)} articles without an image")
        for aid, url in rows:
            try:
                src = image_url(BeautifulSoup(fetcher.get(url), "lxml"), url)
            except FetchError as e:
                failed += 1
                print(f"  ! {e}")
                continue
            if src:
                conn.execute("UPDATE articles SET image_url = %s WHERE id = %s", (src, aid))
                found += 1
            else:
                missing += 1
    print(f"done: {found} images stored, {missing} pages without an image, {failed} fetch errors")


if __name__ == "__main__":
    main()
