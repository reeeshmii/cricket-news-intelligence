from .rss import RSSSource
from .wisden import Wisden

# The four sources that supply almost all T20 articles (53 of the first 60 stored).
# Each was checked on 2026-10-07: robots.txt reachable and permissive for article pages,
# plain HTTP returns full text. Re-verify if a source starts failing.
#
# NOT used:
#  - BBC Sport, The Guardian, Indian Express : reachable, but mostly non-T20 cricket
#    (5%, 10% and 36% of fetched pages were T20); removed on 2026-10-10
#  - Cricbuzz, ESPNcricinfo : 403 (Akamai bot protection), even for robots.txt
#  - Times of India feed    : stale (2016 items);  ESPN.com cricket feed: stale (2020 items)
#  - Sky Sports             : cricket RSS feed URL not found
_FEEDS = {
    "hindustantimes": "https://www.hindustantimes.com/feeds/rss/cricket/rssfeed.xml",
    "crictracker": "https://www.crictracker.com/feed/",
    "cricketaddictor": "https://cricketaddictor.com/feed/",
}

REGISTRY = {s.name: s for s in (Wisden(), *(RSSSource(n, u) for n, u in _FEEDS.items()))}


def get_source(name: str):
    try:
        return REGISTRY[name]
    except KeyError:
        raise SystemExit(f"Unknown source '{name}'. Available: {', '.join(REGISTRY)}")
