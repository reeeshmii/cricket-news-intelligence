from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.crawler.crawl import crawl_source
from src.crawler.dedup import canonicalize_url, content_hash, simhash, hamming
from src.crawler.extract import extract_article, parse_date
from src.crawler.sources.base import Candidate, Source
from src.crawler.sources.wisden import Wisden
from src.crawler.storage import LocalStore
from src.crawler.validate import is_t20, validate

FIXTURE = (Path(__file__).parent / "fixtures" / "wisden_article.html").read_text(encoding="utf-8")
URL = "https://www.wisden.com/cricket-news/sa20-2027-auction-live-updates"
BODY = ("The SA20 auction saw Kagiso Rabada go to Pretoria Capitals while franchises balanced their purses "
        "and squads for the new T20 season. ") * 12


# ---------- dedup ----------
def test_tracking_params_and_trailing_slash_are_ignored():
    a = canonicalize_url("https://WWW.wisden.com/cricket-news/x/?utm_source=tw&fbclid=1#top")
    assert a == "https://www.wisden.com/cricket-news/x"


def test_same_text_same_hash_different_text_different_hash():
    assert content_hash("T", "Hello  world!") == content_hash("t", "hello world")
    assert content_hash("T", "hello world") != content_hash("T", "goodbye world")


def test_simhash_near_duplicate_vs_different():
    base = " ".join(f"word{i % 40} cricket{i % 7}" for i in range(300))
    edited = base + " small addition"
    other = " ".join(f"other{i} thing{i % 11}" for i in range(300))
    assert hamming(simhash(base), simhash(edited)) <= 3
    assert hamming(simhash(base), simhash(other)) > 10


# ---------- extraction + validation on a real saved Wisden page ----------
def test_extract_real_wisden_page():
    doc = extract_article(FIXTURE, URL)
    assert doc["title"].startswith("SA20 2027 Auction")
    assert doc["published_at"] == "2026-10-07T15:04:00+00:00"
    assert doc["author"] is None                      # site sends the string "null"
    assert len(doc["body"].split()) > 300
    assert validate(doc, doc["canonical_url"]) is None


def test_parse_date_handles_z_and_garbage():
    assert parse_date("2026-01-02T03:04:05Z") == "2026-01-02T03:04:05+00:00"
    assert parse_date("not a date") is None and parse_date(None) is None


def test_validation_rules():
    ok = {"title": "IPL 2026 auction", "published_at": "2026-01-01T00:00:00+00:00", "body": BODY}
    assert validate(ok, "https://x/a") is None
    assert validate({**ok, "body": "short text"}, "https://x/a") == "too_short"
    assert validate({**ok, "published_at": None}, "https://x/a") == "missing_date"
    assert validate({**ok, "title": "County Championship round 5", "body": "rain " * 200}, "https://x/county") == "not_t20"


def test_t20_keyword_uses_word_boundaries():
    assert is_t20("Triple century in a Test", "https://x/a", "nothing here") is False
    assert is_t20("Kohli stars in the IPL", "https://x/a", "") is True
    assert is_t20("ODI series preview", "https://x/a", "one T20I mention only") is False
    assert is_t20("Schedule row", "https://x/a", "BBL talks. The BBL deal. BBL clubs.") is True


# ---------- storage / rolling cap ----------
def _article(i, source="wisden"):
    return {"source": source, "url": f"https://x/{i}", "canonical_url": f"https://x/{i}", "title": f"t{i}",
            "author": None, "published_at": "2026-01-01T00:00:00+00:00", "body": f"body {i}", "word_count": 2,
            "content_hash": f"h{i}", "simhash": i * 7919, "scraped_at": datetime.now(timezone.utc).isoformat()}


def test_rolling_cap_deletes_first_added_but_remembers_them(tmp_path):
    store = LocalStore(tmp_path, max_articles=3)
    evicted = sum(store.add(_article(i)) for i in range(5))
    assert evicted == 2
    assert [a["canonical_url"] for a in store.articles] == ["https://x/2", "https://x/3", "https://x/4"]
    assert store.seen_url("https://x/0")              # evicted, but never re-ingested
    store.save()
    assert [a["title"] for a in LocalStore(tmp_path, max_articles=3).articles] == ["t2", "t3", "t4"]


# ---------- end-to-end with a fake source (no network) ----------
class FakeSource(Source):
    name = "fake"

    def __init__(self, pages):
        self.pages = pages          # url -> html

    def discover(self, fetcher):
        now = datetime.now(timezone.utc)
        return [Candidate(u, now) for u in self.pages]

    def fetch_article(self, fetcher, url):
        return self.pages[url]


def _page(title, body, url):
    return (f'<html><head><meta property="og:title" content="{title}">'
            f'<meta property="article:published_time" content="2026-10-07T10:00:00+00:00">'
            f'<link rel="canonical" href="{url}"></head><body><article><p>{body}</p></article></body></html>')


def test_second_run_inserts_nothing_and_duplicates_are_caught(tmp_path):
    other = " ".join(f"unrelated{i} ipl{i % 5} story{i % 13}" for i in range(150))
    pages = {
        "https://s.test/a": _page("IPL auction recap", BODY, "https://s.test/a"),
        "https://s.test/a-copy": _page("IPL auction recap", BODY, "https://s.test/a-copy"),        # same text, new URL
        "https://s.test/a-edit": _page("IPL auction recap!", BODY + " tiny edit", "https://s.test/a-edit"),  # near-dup
        "https://s.test/b": _page("IPL transfer window", other, "https://s.test/b"),
    }
    src, store = FakeSource(pages), LocalStore(tmp_path)

    first = crawl_source(src, None, store, limit=10, days=3, echo=lambda *_: None)
    assert first["new"] == 2 and first["duplicate_exact"] + first["duplicate_near"] == 2
    store.save()

    store2 = LocalStore(tmp_path)                    # fresh process, same data folder
    second = crawl_source(src, None, store2, limit=10, days=3, echo=lambda *_: None)
    assert second["new"] == 0 and second["already_seen"] == 4


def test_dry_run_stores_nothing(tmp_path):
    src = FakeSource({"https://s.test/a": _page("IPL auction recap", BODY, "https://s.test/a")})
    store = LocalStore(tmp_path)
    stats = crawl_source(src, None, store, limit=5, days=3, dry_run=True, echo=lambda *_: None)
    assert stats["new"] == 1 and store.articles == []


# ---------- RSS discovery (network faked) ----------
def test_rss_discovery_parses_dates_and_sorts_newest_first():
    from src.crawler.sources.rss import RSSSource
    feed = ('<rss><channel>'
            '<item><link>https://b/old?at_medium=RSS</link><pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate></item>'
            '<item><link>https://b/new</link><pubDate>Wed, 07 Oct 2026 14:28:55 +0530</pubDate></item>'
            '<item><title>no link</title></item></channel></rss>')
    got = RSSSource("b", "https://b/feed").discover(FakeFetcher({"https://b/feed": feed}))
    assert [c.url for c in got] == ["https://b/new", "https://b/old?at_medium=RSS"]
    assert canonicalize_url(got[1].url) == "https://b/old"
    assert got[0].lastmod.tzinfo is not None


# ---------- Wisden sitemap discovery (network faked) ----------
class FakeFetcher:
    def __init__(self, files):
        self.files = files

    def get(self, url):
        return self.files[url]


def test_wisden_discovery_picks_newest_post_sitemap_and_filters_news():
    ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
    idx = (f'<sitemapindex {ns}><sitemap><loc>https://w/site-map/post/2.xml</loc></sitemap>'
           f'<sitemap><loc>https://w/site-map/post/1.xml</loc></sitemap></sitemapindex>')
    post1 = (f'<urlset {ns}>'
             '<url><loc>https://w/cricket-news/old</loc><lastmod>2026-10-01T00:00:00+00:00</lastmod></url>'
             '<url><loc>https://w/cricket-news/new</loc><lastmod>2026-10-07T00:00:00+00:00</lastmod></url>'
             '<url><loc>https://w/cricket-videos/clip</loc><lastmod>2026-10-07T01:00:00+00:00</lastmod></url></urlset>')
    f = FakeFetcher({"https://w/index.xml": idx, "https://w/site-map/post/1.xml": post1})
    got = Wisden(sitemap_index="https://w/index.xml").discover(f)
    assert [c.url for c in got] == ["https://w/cricket-news/new", "https://w/cricket-news/old"]


def test_date_and_author_fall_back_to_json_ld_and_time_tag():
    body = "<p>" + " ".join(["IPL"] * 150) + "</p>"
    ld = ('<script type="application/ld+json">{"@graph":[{"@type":"NewsArticle",'
          '"datePublished":"2026-10-08T14:38:18.349Z","author":[{"@type":"Person","name":"Jane Doe"}]}]}</script>')
    doc = extract_article(f"<html><head><title>IPL x</title>{ld}</head><body><article>{body}</article></body></html>",
                          "https://bbc.test/a")
    assert doc["published_at"] == "2026-10-08T14:38:18.349000+00:00" and doc["author"] == "Jane Doe"
    doc = extract_article('<html><head><title>IPL x</title><meta name="author" content="https://fb.com/x"></head>'
                          f'<body><time datetime="2026-10-08T09:00:00Z">today</time><article>{body}</article></body></html>',
                          "https://bbc.test/b")
    assert doc["published_at"] == "2026-10-08T09:00:00+00:00" and doc["author"] is None
