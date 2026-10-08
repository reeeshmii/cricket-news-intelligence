"""Wisden adapter: plain HTTP + sitemap discovery (robots.txt allows both; no JS rendering needed)."""
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from .base import Candidate, Source

SITEMAP_INDEX = "https://www.wisden.com/site-map/sitemap.xml"
_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_POST_SITEMAP = re.compile(r"/site-map/post/(\d+)\.xml$")


def _parse_lastmod(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Wisden(Source):
    name = "wisden"

    def __init__(self, sitemap_index: str = SITEMAP_INDEX):
        self.sitemap_index = sitemap_index

    def discover(self, fetcher) -> list[Candidate]:
        index = ET.fromstring(fetcher.get(self.sitemap_index))
        post_maps = sorted(
            ((int(m.group(1)), loc.text.strip()) for loc in index.findall(".//sm:loc", _NS)
             if (m := _POST_SITEMAP.search(loc.text or ""))))
        if not post_maps:
            return []
        # the lowest-numbered post sitemap holds the newest articles (re-sorted by lastmod below)
        root = ET.fromstring(fetcher.get(post_maps[0][1]))
        out = []
        for u in root.findall("sm:url", _NS):
            loc = u.findtext("sm:loc", namespaces=_NS)
            if loc and "/cricket-news/" in loc:       # skips videos, live scores, webstories
                out.append(Candidate(loc.strip(), _parse_lastmod(u.findtext("sm:lastmod", namespaces=_NS))))
        out.sort(key=lambda c: c.lastmod or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return out
