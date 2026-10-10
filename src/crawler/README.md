# Web crawler

Collects T20 cricket news from open sources, cleans and validates it, removes duplicates,
and stores it locally or in Neon PostgreSQL. It runs once, in a loop, or on a GitHub schedule.

```
discover (RSS / sitemap) -> already seen? -> fetch (robots.txt + 2 s delay) -> extract
  -> validate + T20 filter -> exact duplicate? -> near duplicate? -> store (rolling cap)
```

## Sources

Each source was checked on 2026-10-07: `robots.txt` is readable and allows article pages,
and plain HTTP returns the full text (no Playwright needed).

| name | site | discovery |
|---|---|---|
| `wisden` | wisden.com | sitemap (`site-map/post/1.xml`, newest first) |
| `hindustantimes` | Hindustan Times | RSS |
| `crictracker` | CricTracker | RSS |
| `cricketaddictor` | Cricket Addictor | RSS |

These four supplied 53 of the first 60 stored T20 articles.

Not used:
- **BBC Sport**, **The Guardian** and **Indian Express** were reachable but mostly non-T20
  (5%, 10% and 36% of fetched pages were T20). They were removed on 2026-10-10.
- **Cricbuzz** and **ESPNcricinfo** return 403 from Akamai bot protection, even for
  `robots.txt`.
- The **Times of India** and **ESPN.com** feeds are stale (2016 / 2020).
- No **Sky Sports** cricket feed was found.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-crawler.txt
```

Put `DATABASE_URL` (your Neon connection string) in a `.env` file. `python-dotenv` also
finds a `.env` in a parent folder; the current one is in `ATSMA\`, outside the repo.
The crawler switches the pooled host (`ep-…-pooler…`) to Neon's direct host by itself.

## Commands

| what | command |
|---|---|
| preview, store nothing | `python -m src.crawler.crawl --limit 3 --dry-run` |
| one crawl, local files | `python -m src.crawler.crawl --limit 10` |
| one crawl, Neon | `python -m src.crawler.crawl --limit 10 --store neon` |
| one source only | `python -m src.crawler.crawl --source wisden --limit 10` |
| run continuously | `python -m src.crawler.loop --every 30 --store neon` (Ctrl+C to stop) |
| quality report | `python -m src.crawler.report --store neon` |
| tests | `python -m pytest tests -q` |

Prefix each with `.venv/Scripts/` (Windows) when the virtual environment is not activated.

Options: `--limit` caps NEW pages downloaded per source per run, `--days` ignores older
items, `--max-articles` sets the rolling cap, `--save-html` keeps raw pages in
`data/raw_html/`. The defaults can be set in `.env`: `CRAWLER_STORE`, `CRAWLER_MAX_ARTICLES`.

## Storage

**Local** (`data/`, git-ignored): `articles.jsonl`, `seen.json`, `crawl_log.jsonl`.

**Neon**: tables are created automatically from [`schema.sql`](schema.sql):

| table | contents |
|---|---|
| `articles` | one row per stored article; `status='cleaned'` is the NLP stage's input |
| `sources` | one row per site, with `last_crawled_at` |
| `seen_articles` | every URL ever processed and its outcome (stored, not_t20, duplicate, ...) |
| `crawl_runs` | per source, per run: found / inserted / skipped / duplicates / errors, plus details |

`articles`, `sources` and `crawl_runs` must stay identical to `db/schema.sql` on the
`database` branch.

### Duplicates (three layers)
1. **URL.** It is canonicalised (tracking parameters, fragments and trailing slashes removed)
   and skipped before downloading if seen before.
2. **Exact content.** A SHA-256 hash of the normalised title + body catches the same story at
   another URL.
3. **Near-duplicate.** SimHash Hamming distance ≤ 3 against articles from the last 7 days.
   Only the URL is remembered, so near-duplicates never use up a slot under the cap.

### Rolling cap
When more than `MAX_ARTICLES` (default 3000) are stored, the **first-added** articles are
deleted, in the same transaction as the insert. Their URLs stay in `seen_articles`, so they
are never fetched again. `seen_articles` itself is capped at 50,000 rows.

## Running continuously

- **Laptop:** `python -m src.crawler.loop --every 30 --store neon`. It writes progress to
  `data/crawler_status.json` (state, last/next run, new articles), which the future API's
  `/status` can read, and logs to `data/crawler.log`.
- **GitHub Actions:** [`.github/workflows/crawler.yml`](../../.github/workflows/crawler.yml)
  crawls every 3 hours. Add the repository secret `DATABASE_URL` (Settings → Secrets and
  variables → Actions). GitHub only runs scheduled workflows from the **default branch**,
  so it starts after the crawler is merged into `main`.

Only one crawl runs at a time: a file lock covers one machine, and a Postgres advisory lock
covers laptop + Actions together (a run that finds the other one busy prints
"Skipped" and exits normally). A failing site is logged and skipped; if every source
fails, the command exits non-zero.

## Adding a source

RSS site: add `"name": "feed url"` to `_FEEDS` in [`sources/__init__.py`](sources/__init__.py).
Other sites: subclass `Source` (see [`sources/wisden.py`](sources/wisden.py)) and
implement `discover()`. Override `fetch_article()` only if the site needs a browser.
Check `robots.txt` and the terms first; dry-run it before storing.

## Known limitations

- Wisden publishes no author name (the byline is empty in the HTML), so `author` is NULL.
- The T20 filter is keyword-based: a keyword must be in the title/URL, or appear ≥ 3 times in
  the body. Expect many general-cricket articles to be rejected (`rejected_not_t20`).
- GitHub's datacenter IPs might be treated differently from home connections by some sites;
  check `crawl_runs.errors` after the first scheduled runs.
- Don't share a session-level `SET` through Neon's **pooled** URL: PgBouncer leaks it to other
  clients. The crawler avoids this by using the direct endpoint.

## Files

| file | role |
|---|---|
| `crawl.py` | entry point, per-article flow, `make_store()` |
| `loop.py` | continuous mode, logging, status file |
| `sources/` | one adapter per site (`wisden.py`, `rss.py`) |
| `http.py` | robots.txt, per-host delay, retries |
| `extract.py` | title / author / date / body (meta tags, JSON-LD, trafilatura) |
| `validate.py` | required fields, minimum length, T20 relevance |
| `dedup.py` | URL canonicalisation, content hash, SimHash |
| `storage.py` / `neon_store.py` | local and Neon stores (same interface) |
| `lock.py` | single-crawl lock and status file |
| `report.py` | data-quality report |
| `schema.sql` | the crawler's Neon tables |
