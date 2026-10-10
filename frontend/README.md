# Dashboard

React (Vite) frontend + FastAPI backend (`src/api`). The API reads Neon and returns JSON; after
`npm run build` it also serves this app, so production is a single process.

## Sections

| section | what it shows | API |
|---|---|---|
| **Overview** | total articles, new in a period, topics discovered, last successful refresh, articles by source, topic distribution, recently collected | `/api/overview` |
| **Latest News** | search (headline + keywords), filters (source, topic, published date), sorting, pagination, links to the originals | `/api/articles` |
| **Topic & Cluster Explorer** | topics from the active model with keywords, people/teams/tournaments, representative headlines, article counts, a 2-D map of all article embeddings, evaluation against the KMeans baseline | `/api/topics`, `/api/topics/map`, `/api/articles?topic=` |
| **Trending Topics** | topic frequency per day (line chart), total volume (separate chart), most covered vs largest increase, date-range and source filters | `/api/trends` |

Nothing is hard-coded: topic names, keywords and groupings come from the database.

**Live updates.** The app polls `/api/status` every minute and when the tab regains focus. Its
`version` changes when new articles, assignments or a new topic model arrive, and only then do
the pages refetch. During a refetch the old view stays visible, slightly faded.

## Design

The palette is exact: warm cream `#FFF7EA` page, white cards, deep forest `#556B5A` for text and
navigation, sage `#8FB08A` for chart marks, pale sage `#C9D8C4` and sand `#E6D9C7` for context
and borders. Headlines use Newsreader (serif); everything else, including numbers, uses Inter.

Charts follow the measured contrast of the palette:

- **Forest text:** on cream it measures 5.4:1, on white 5.8:1, so all text is forest.
- **Sage marks:** sage on white is only 2.4:1, so sage bars always print their values, and every
  chart has a **Table** view.
- **Emphasis instead of many colours:** the palette has one hue family, so multi-topic charts
  highlight one topic (forest) against the others (pale sage), and you choose which. This keeps
  topics distinguishable without inventing extra colours.
- **Volume and growth stay separate:** they are drawn in separate charts, never on two y-axes.

## Run it

```bash
# once
cd frontend && npm install && npm run build && cd ..

# then: API + built app on http://localhost:8000
.venv/Scripts/python -m src.api
```

Development, with hot reload (two terminals):

```bash
.venv/Scripts/python -m src.api --reload          # API on :8000
cd frontend && npm run dev                        # app on http://localhost:5173 (proxies /api)
```

Tests: `.venv/Scripts/python -m pytest tests/api -q` (runs in a throwaway Neon schema).

## Deploy on Vercel

The React app is served as static files; the FastAPI app runs as one Python serverless function
(`api/index.py`). The crawler, NLP and clustering keep running on GitHub Actions and write to Neon,
so the hosted dashboard always shows the latest data.

| file | role |
|---|---|
| `vercel.json` | builds `frontend/`, serves `frontend/dist`, sends `/api/*` to `api/index.py`, everything else to the React app |
| `api/index.py` | exposes `src/api/app.py` to Vercel |
| `requirements.txt` | the API's dependencies only (about 50 MB, no ML libraries); the full pipeline is in `requirements-all.txt` |
| `.vercelignore` | keeps `.venv`, tests, data and `node_modules` out of the upload |

The API needs no machine-learning libraries because the cluster stage stores the 2-D map
coordinates (`article_projection`). On Vercel (env `VERCEL` set) each request opens one short
connection through Neon's pooled endpoint; locally a small connection pool is used.

Steps:

1. Merge everything into `main` and push.
2. On vercel.com: **Add New → Project**, import the GitHub repository. Leave the framework preset
   as **Other**; `vercel.json` supplies the build settings.
3. **Settings → Environment Variables**: add `DATABASE_URL` = the Neon connection string with the
   `-pooler` host, for Production (and Preview if you use preview deployments).
4. **Deploy.** Every push to `main` redeploys automatically.
