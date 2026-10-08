from dataclasses import dataclass
from datetime import datetime


@dataclass
class Candidate:
    url: str
    lastmod: datetime | None = None


class Source:
    """One adapter per site. Add a site by subclassing and registering it in sources/__init__.py."""
    name: str = ""

    def discover(self, fetcher) -> list[Candidate]:
        """Return candidate article URLs, newest first."""
        raise NotImplementedError

    def fetch_article(self, fetcher, url: str) -> str:
        """Return the page HTML. Default: plain HTTP. A browser-based source can override this."""
        return fetcher.get(url)
