"""Dashboard API (FastAPI) + the built React app.

  python -m src.api                 # http://localhost:8000  (serves frontend/dist when built)
  python -m src.api --reload        # development
On Vercel, api/index.py exposes this same app as a serverless function (see vercel.json).

Endpoints (all JSON, all read-only):
  /api/health      configuration check (no secrets)
  /api/status      cheap "has anything changed?" version + last refresh times (polled by the UI)
  /api/meta        filter options: sources, topics, date bounds
  /api/overview    KPIs, distributions by source and topic, recently collected articles
  /api/articles    search / filter / sort / paginate
  /api/topics      active topic model: topics, keywords, entities, headlines, evaluation
  /api/topics/map  2-D map of the article embeddings (stored by the cluster stage)
  /api/trends      topic frequency over time, volume vs growth
"""
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import psycopg

from .. import config
from . import db, queries

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    db.close()


app = FastAPI(title="T20 Cricket News Intelligence API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET"], allow_headers=["*"])


def describe_error(exc: Exception) -> str:
    """A safe, useful message for the dashboard and logs. Never includes the connection string."""
    first = str(exc).splitlines()[0] if str(exc) else ""
    if isinstance(exc, RuntimeError) and "DATABASE_URL" in first:
        return "DATABASE_URL is not set on the server (add it in the hosting settings, then redeploy)"
    if isinstance(exc, psycopg.ProgrammingError) and "connection" in first.lower():
        return ("DATABASE_URL is not a valid connection string: it must start with postgresql:// "
                "(no 'psql' command and no quotes around it)")
    if isinstance(exc, psycopg.OperationalError):
        return "Could not connect to the database (check DATABASE_URL and that the Neon project is active)"
    return f"Server error ({type(exc).__name__})"


@app.exception_handler(Exception)
async def unhandled_error(request, exc: Exception):
    print(f"error on {request.url.path}: {type(exc).__name__}: {describe_error(exc)}")   # visible in host logs
    return JSONResponse(status_code=500, content={"detail": describe_error(exc)})


@app.get("/api/health")
def health():
    """Configuration check without secrets: booleans only, plus whether a query succeeds."""
    url = config.DATABASE_URL or ""
    info = {"serverless": db.SERVERLESS, "database_url_set": bool(url),
            "starts_with_postgresql": url.startswith(("postgresql://", "postgres://")),
            "pooled_host": "-pooler." in url}
    try:
        with db.connection() as conn:
            conn.execute("SELECT 1")
        info["database"] = "ok"
    except Exception as exc:
        info["database"] = describe_error(exc)
    return info


@app.get("/api/status")
def status():
    with db.connection() as conn:
        return queries.status(conn)


@app.get("/api/meta")
def meta():
    with db.connection() as conn:
        return queries.meta(conn)


@app.get("/api/overview")
def overview(days: int | None = Query(7, ge=1, le=3650, description="period in days; omit for all time")):
    with db.connection() as conn:
        return queries.overview(conn, days)


@app.get("/api/overview/all")
def overview_all():
    with db.connection() as conn:
        return queries.overview(conn, None)


@app.get("/api/articles")
def articles(q: str | None = Query(None, max_length=100), source: str | None = None,
             topic: str | None = Query(None, pattern=r"^(none|\d+)$"),
             date_from: date | None = None, date_to: date | None = None,
             sort: Literal["newest", "oldest", "title", "source", "topic", "relevance"] = "newest",
             page: int = Query(1, ge=1), page_size: int = Query(20, ge=5, le=100)):
    with db.connection() as conn:
        return queries.articles(conn, q, source, topic, date_from, date_to, sort, page, page_size)


@app.get("/api/topics")
def topics():
    with db.connection() as conn:
        return queries.topics(conn)


@app.get("/api/topics/map")
def topics_map(method: Literal["umap", "pca"] = "umap"):
    with db.connection() as conn:
        return queries.projection(conn, method)


@app.get("/api/trends")
def trends(date_from: date | None = None, date_to: date | None = None, source: str | None = None):
    with db.connection() as conn:
        if date_to is None:
            date_to = queries.meta(conn)["dates"]["max"] or date.today()
        if date_from is None:
            date_from = date_to - timedelta(days=13)
        if date_from > date_to:
            raise HTTPException(400, "date_from must be on or before date_to")
        if (date_to - date_from).days > 366:
            raise HTTPException(400, "range is limited to one year")
        return queries.trends(conn, date_from, date_to, source)


# ------------------------------------------------------------------ the React app (after `npm run build`)
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        file = FRONTEND / path
        return FileResponse(file if path and file.is_file() else FRONTEND / "index.html")
