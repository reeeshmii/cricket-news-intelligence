"""Local storage (JSONL) with a rolling cap and an "already seen" memory.

data/articles.jsonl   one article per line, in the order they were added
data/seen.json        {"urls": {...}, "hashes": {...}} - tiny memory so evicted/rejected
                      pages are never fetched or re-inserted again
data/crawl_log.jsonl  one summary line per crawl run
data/raw_html/        optional saved pages (--save-html)

When articles.jsonl holds more than `max_articles`, the first-added are deleted.
The same interface will later be implemented on top of Neon PostgreSQL.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import settings
from .dedup import hamming


class LocalStore:
    def __init__(self, data_dir: Path | str | None = None, max_articles: int | None = None,
                 seen_max: int | None = None):
        self.dir = Path(data_dir or settings.DATA_DIR)
        self.max_articles = max_articles or settings.MAX_ARTICLES
        self.seen_max = seen_max or settings.SEEN_MAX
        self.dir.mkdir(parents=True, exist_ok=True)
        self.articles_path = self.dir / "articles.jsonl"
        self.seen_path = self.dir / "seen.json"
        self.log_path = self.dir / "crawl_log.jsonl"
        self.articles: list[dict] = self._read_jsonl(self.articles_path)
        seen = json.loads(self.seen_path.read_text("utf-8")) if self.seen_path.exists() else {}
        self._urls: dict[str, str] = seen.get("urls", {})       # url -> outcome
        self._hashes: dict[str, str] = seen.get("hashes", {})   # content_hash -> url
        for a in self.articles:                                  # self-heal if seen.json was lost
            self._urls.setdefault(a["canonical_url"], "stored")
            self._hashes.setdefault(a["content_hash"], a["canonical_url"])

    # ---- lookups -------------------------------------------------------------------
    def seen_url(self, canonical_url: str) -> bool:
        return canonical_url in self._urls

    def url_for_hash(self, content_hash: str) -> str | None:
        return self._hashes.get(content_hash)

    def near_duplicate(self, simhash: int, now: datetime | None = None) -> str | None:
        """canonical_url of a recent stored article within the SimHash distance, if any."""
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=settings.NEAR_DUP_WINDOW_DAYS)
        for a in self.articles:
            if a.get("simhash") is None or datetime.fromisoformat(a["scraped_at"]) < cutoff:
                continue
            if hamming(simhash, a["simhash"]) <= settings.NEAR_DUP_HAMMING:
                return a["canonical_url"]
        return None

    # ---- writes (in memory; call save()) --------------------------------------------
    def mark_seen(self, canonical_url: str, outcome: str, content_hash: str | None = None) -> None:
        self._urls[canonical_url] = outcome
        if content_hash:
            self._hashes[content_hash] = canonical_url
        self._trim(self._urls)
        self._trim(self._hashes)

    def add(self, article: dict) -> int:
        """Append an article; returns how many old articles were evicted by the cap."""
        self.articles.append(article)
        self.mark_seen(article["canonical_url"], "stored", article["content_hash"])
        evicted = max(0, len(self.articles) - self.max_articles)
        if evicted:
            del self.articles[:evicted]          # oldest-added first
        return evicted

    def _trim(self, d: dict) -> None:
        while len(d) > self.seen_max:
            d.pop(next(iter(d)))

    def log_run(self, summary: dict) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")

    def save(self) -> None:
        self._atomic_write(self.articles_path,
                           "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in self.articles))
        self._atomic_write(self.seen_path, json.dumps({"urls": self._urls, "hashes": self._hashes}))

    # ---- helpers -------------------------------------------------------------------
    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
