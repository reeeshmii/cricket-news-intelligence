from .rss import RSSSource
from .wisden import Wisden

# Every source below was checked on 2026-10-07: robots.txt reachable and permissive for article
# pages, plain HTTP returns full text. Re-verify if a source starts failing.
#
# NOT registered:
#  - Cricbuzz, ESPNcricinfo : 403 (Akamai bot protection), even for robots.txt
#  - Times of India feed    : stale (2016 items);  ESPN.com cricket feed: stale (2020 items)
#  - Sky Sports             : cricket RSS feed URL not found
_FEEDS = {
    "bbc": "https://feeds.bbci.co.uk/sport/cricket/rss.xml",
    "guardian": "https://www.theguardian.com/sport/cricket/rss",
    "crictracker": "https://www.crictracker.com/feed/",
    "hindustantimes": "https://www.hindustantimes.com/feeds/rss/cricket/rssfeed.xml",
    "indianexpress": "https://indianexpress.com/section/sports/cricket/feed/",
    "cricketaddictor": "https://cricketaddictor.com/feed/",
}

REGISTRY = {s.name: s for s in (Wisden(), *(RSSSource(n, u) for n, u in _FEEDS.items()))}


def get_source(name: str):
    try:
        return REGISTRY[name]
    except KeyError:
        raise SystemExit(f"Unknown source '{name}'. Available: {', '.join(REGISTRY)}")
