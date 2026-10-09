import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USER_AGENT = os.environ.get("USER_AGENT", "T20NewsIntelBot/0.1")
CRAWL_DELAY = float(os.environ.get("CRAWL_DELAY_SECONDS", "2"))

MIN_WORDS = 100
NEAR_DUP_HAMMING = 3          # SimHash distance threshold
NEAR_DUP_WINDOW_DAYS = 7
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"   # 384-d
ASSIGN_MIN_SIMILARITY = 0.35  # below this a new article goes to the "emerging" pool
REFIT_WINDOW_DAYS = 90

# Feed/sitemap URLs change over time -- VERIFY each one and check robots.txt / ToS
# before crawling. Add or remove sources here; no other code changes needed.
SOURCES = [
    {"name": "ESPNcricinfo", "base_url": "https://www.espncricinfo.com",
     "feeds": ["https://www.espncricinfo.com/rss/content/story/feeds/0.xml"]},
    {"name": "Cricbuzz", "base_url": "https://www.cricbuzz.com",
     "feeds": ["https://www.cricbuzz.com/rss-feed/cricket-news"]},   # verify; may need sitemap
    {"name": "Wisden", "base_url": "https://wisden.com",
     "feeds": ["https://wisden.com/feed"]},
]

# Cheap relevance gate on title/summary/body (lowercase substrings)
T20_KEYWORDS = ["t20", "ipl", "indian premier league", "big bash", "bbl", "psl",
                "pakistan super league", "sa20", "cpl", "caribbean premier league",
                "the hundred", "wpl", "ilt20", "mlc", "t20i"]
