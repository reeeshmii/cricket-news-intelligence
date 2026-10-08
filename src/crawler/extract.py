"""Article extraction: HTML -> {title, author, published_at, canonical_url, body}."""
import json
from datetime import datetime, timezone

import trafilatura
from bs4 import BeautifulSoup

_EMPTY_AUTHORS = {"", "null", "none", "unknown", "n/a"}


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for n in names:
        tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if tag and tag.get("content", "").strip():
            return tag["content"].strip()
    return None


def parse_date(value: str | None) -> str | None:
    """Return an ISO-8601 UTC string, or None if the value cannot be parsed."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def extract_article(html: str, url: str) -> dict | None:
    """Generic extractor (works for any site with standard og/article meta tags)."""
    raw = trafilatura.extract(html, url=url, output_format="json", with_metadata=True,
                              include_comments=False, include_tables=False)
    doc = json.loads(raw) if raw else {}
    if not doc.get("text"):
        return None

    soup = BeautifulSoup(html, "lxml")
    canonical = soup.find("link", rel="canonical")
    author = _meta(soup, "author", "article:author") or doc.get("author")
    if author and author.strip().lower() in _EMPTY_AUTHORS:
        author = None

    return {
        "title": _meta(soup, "og:title", "twitter:title") or doc.get("title"),
        "author": author,
        "published_at": parse_date(_meta(soup, "article:published_time", "og:article:published_time",
                                         "datePublished")) or parse_date(doc.get("date")),
        "canonical_url": canonical["href"] if canonical and canonical.get("href") else url,
        "body": doc["text"].strip(),
    }
