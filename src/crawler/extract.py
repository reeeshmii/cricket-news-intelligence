"""Article extraction: HTML -> {title, author, published_at, canonical_url, body}."""
import json
from datetime import datetime, timezone
from urllib.parse import urljoin

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
    ld = _json_ld(soup)
    canonical = soup.find("link", rel="canonical")
    time_tag = soup.find("time", attrs={"datetime": True})

    published = (parse_date(_meta(soup, "article:published_time", "og:article:published_time", "datePublished"))
                 or parse_date(_first(ld, "datePublished"))
                 or parse_date(time_tag["datetime"] if time_tag else None)
                 or parse_date(doc.get("date")))           # trafilatura: often date-only, last resort
    return {
        "title": _meta(soup, "og:title", "twitter:title") or doc.get("title"),
        "author": _clean_author(_meta(soup, "author", "article:author"))
                  or _clean_author(_ld_author(ld)) or _clean_author(doc.get("author")),
        "published_at": published,
        "canonical_url": urljoin(url, canonical["href"].strip()) if canonical and canonical.get("href") else url,
        "image_url": image_url(soup, url),
        "body": doc["text"].strip(),
    }


def image_url(soup: BeautifulSoup, url: str) -> str | None:
    """The article's own preview image (og:image / twitter:image), as an absolute https URL."""
    src = _meta(soup, "og:image", "og:image:url", "twitter:image")
    if not src:
        return None
    src = urljoin(url, src.strip())
    return src if src.startswith("https://") else None


def _clean_author(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value.lower() in _EMPTY_AUTHORS or value.startswith("http"):   # some sites put a profile URL here
        return None
    return value


def _json_ld(soup: BeautifulSoup) -> list[dict]:
    """All JSON-LD objects on the page, flattened (handles lists and @graph)."""
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop(0)
            if isinstance(item, dict):
                out.append(item)
                stack.extend(item.get("@graph", []))
            elif isinstance(item, list):
                stack.extend(item)
    return out


def _first(items: list[dict], key: str):
    return next((i[key] for i in items if isinstance(i.get(key), str) and i[key].strip()), None)


def _ld_author(items: list[dict]) -> str | None:
    for i in items:
        a = i.get("author")
        for cand in (a if isinstance(a, list) else [a]):
            name = cand.get("name") if isinstance(cand, dict) else cand
            if _clean_author(name):
                return name
    return None
