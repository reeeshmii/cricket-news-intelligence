"""Dashboard API (FastAPI) + the built React app.

  python -m src.api                 # http://localhost:8000  (serves frontend/dist when built)
  python -m src.api --reload        # development

Endpoints (all JSON, all read-only):
  /api/status      cheap "has anything changed?" version + last refresh times (polled by the UI)
  /api/meta        filter options: sources, topics, date bounds
  /api/overview    KPIs, distributions by source and topic, recently collected articles
  /api/articles    search / filter / sort / paginate
  /api/topics      active topic model: topics, keywords, entities, headlines, evaluation
  /api/topics/map  2-D projection of the article embeddings
  /api/trends      topic frequency over time, volume vs growth
"""
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, queries
from .embedding_map import embedding_map

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _warm_map() -> None:
    """UMAP compiles itself (numba) on first use, ~30 s; do it before anyone opens the map."""
    try:
        with db.connection() as conn:
            model_id, rows = queries.embedding_rows(conn)
        embedding_map(model_id, rows)
    except Exception:
        pass                                       # the map endpoint will report real errors


@asynccontextmanager
async def lifespan(app: FastAPI):
    import threading
    threading.Thread(target=_warm_map, daemon=True).start()
    yield
    db.close()


app = FastAPI(title="T20 Cricket News Intelligence API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET"], allow_headers=["*"])


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
        model_id, rows = queries.embedding_rows(conn)
    return embedding_map(model_id, rows, method)


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
