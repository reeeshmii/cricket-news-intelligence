"""Crawler-only settings (kept out of the shared src/config.py)."""
import os
from pathlib import Path

from .. import config

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("CRAWLER_DATA_DIR", ROOT / "data"))   # git-ignored

USER_AGENT = config.USER_AGENT
DELAY_SECONDS = config.CRAWL_DELAY
MIN_WORDS = config.MIN_WORDS
NEAR_DUP_HAMMING = config.NEAR_DUP_HAMMING
NEAR_DUP_WINDOW_DAYS = config.NEAR_DUP_WINDOW_DAYS

# Rolling cap: when more than MAX_ARTICLES are stored, the oldest-added are deleted.
MAX_ARTICLES = int(os.environ.get("CRAWLER_MAX_ARTICLES", "3000"))
# Tiny "already seen" memory (URL / hash only) so evicted articles are not re-ingested.
SEEN_MAX = int(os.environ.get("CRAWLER_SEEN_MAX", "50000"))

# "the hundred" is dropped from the shared list: as plain text it matches ordinary Test reports.
T20_KEYWORDS = [k for k in config.T20_KEYWORDS if k != "the hundred"] + ["twenty20"]
