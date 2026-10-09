"""Polite HTTP client: honours robots.txt, rate-limits per host, retries with backoff."""
import time
import urllib.robotparser
from urllib.parse import urlsplit

import requests

from . import settings


class FetchError(Exception):
    pass


class RobotsDisallowed(FetchError):
    pass


class Fetcher:
    def __init__(self, user_agent: str | None = None, delay: float | None = None,
                 timeout: float = 20, retries: int = 2):
        self.user_agent = user_agent or settings.USER_AGENT
        self.delay = settings.DELAY_SECONDS if delay is None else delay
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent,
                                     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                                     "Accept-Language": "en"})
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_request: dict[str, float] = {}

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser:
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.session.get(origin + "/robots.txt", timeout=self.timeout)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                    rp.modified()
                elif r.status_code in (401, 403) or r.status_code >= 500:
                    rp.disallow_all = True      # cannot read the rules -> be conservative
                else:
                    rp.allow_all = True         # 404 etc: no robots.txt, nothing disallowed
            except requests.RequestException:
                rp.disallow_all = True
            self._robots[origin] = rp
        return self._robots[origin]

    def allowed(self, url: str) -> bool:
        return self._robots_for(url).can_fetch(self.user_agent, url)

    def _wait(self, host: str) -> None:
        wait = self._last_request.get(host, 0) + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request[host] = time.monotonic()

    def get(self, url: str) -> str:
        """Return response text, or raise FetchError / RobotsDisallowed."""
        if not self.allowed(url):
            raise RobotsDisallowed(url)
        host = urlsplit(url).netloc
        last_err = None
        for attempt in range(self.retries + 1):
            self._wait(host)
            try:
                r = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as e:
                last_err = str(e)
            else:
                if r.status_code == 200:
                    return r.text
                last_err = f"HTTP {r.status_code}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    break                       # 403/404 etc: retrying will not help
            if attempt < self.retries:
                time.sleep(self.delay * (2 ** attempt))
        raise FetchError(f"{url}: {last_err}")
