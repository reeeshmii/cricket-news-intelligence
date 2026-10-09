"""Duplicate detection helpers: URL canonicalisation, content hash, SimHash."""
import hashlib
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
             "fbclid", "gclid", "ref", "cmp", "at_medium", "at_campaign", "ocid", "cid"}


def canonicalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(p.query) if k.lower() not in _TRACKING])
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, query, ""))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()


def content_hash(title: str, body: str) -> str:
    return hashlib.sha256(_normalize(title + " " + body).encode()).hexdigest()


def simhash(text: str, bits: int = 64) -> int:
    """64-bit SimHash over word 3-shingles. Returned as signed int for Postgres BIGINT."""
    words = _normalize(text).split()
    shingles = [" ".join(words[i:i + 3]) for i in range(max(1, len(words) - 2))]
    v = [0] * bits
    for sh in shingles:
        h = int.from_bytes(hashlib.md5(sh.encode()).digest()[:8], "big")
        for i in range(bits):
            v[i] += 1 if (h >> i) & 1 else -1
    out = sum(1 << i for i in range(bits) if v[i] > 0)
    return out - (1 << 64) if out >= (1 << 63) else out


def hamming(a: int, b: int) -> int:
    return bin((a ^ b) & ((1 << 64) - 1)).count("1")
