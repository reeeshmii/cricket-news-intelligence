"""Data validation + T20 relevance. Each check returns a reason string, or None if OK."""
import re

from . import settings

_T20 = re.compile(r"\b(" + "|".join(re.escape(k) for k in settings.T20_KEYWORDS) + r")\b", re.I)


BODY_MENTIONS = 3     # a passing mention (e.g. one "T20I" in an ODI preview) is not enough


def is_t20(title: str, url: str, body: str) -> bool:
    """T20 if a keyword is in the title/URL, or is mentioned repeatedly in the body."""
    slug = re.sub(r"[-_/]+", " ", url)
    return bool(_T20.search(f"{title} {slug}")) or len(_T20.findall(body)) >= BODY_MENTIONS


def validate(doc: dict, url: str) -> str | None:
    """Return None if the article is acceptable, else a short reason code."""
    if not doc.get("title"):
        return "missing_title"
    if not doc.get("published_at"):
        return "missing_date"
    if len(doc["body"].split()) < settings.MIN_WORDS:
        return "too_short"
    if not is_t20(doc["title"], url, doc["body"]):
        return "not_t20"
    return None
