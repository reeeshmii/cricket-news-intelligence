"""Generic RSS adapter: one feed URL per source, plain HTTP article pages."""
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .base import Candidate, Source


def _parse_pubdate(text: str | None) -> datetime | None:
    if not text:
        return None
    text = text.strip()
    try:
        dt = parsedate_to_datetime(text)                   # RFC 822: "Wed, 07 Oct 2026 14:28:55 GMT"
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class RSSSource(Source):
    def __init__(self, name: str, feed_url: str):
        self.name = name
        self.feed_url = feed_url

    def discover(self, fetcher) -> list[Candidate]:
        root = ET.fromstring(fetcher.get(self.feed_url))
        out = []
        for item in root.iter("item"):
            link = (item.findtext("link") or "").strip()
            if link:
                out.append(Candidate(link, _parse_pubdate(item.findtext("pubDate"))))
        out.sort(key=lambda c: c.lastmod or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return out
