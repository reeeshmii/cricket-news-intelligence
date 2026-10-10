"""Dashboard API tests: every endpoint against a throwaway Neon schema with a real topic model
(synthetic embeddings, fitted by the actual cluster stage). Real data is never touched."""
import os
import uuid
from datetime import date, timedelta

import pytest
from psycopg import sql

from src import config

pytestmark = pytest.mark.skipif(not config.DATABASE_URL, reason="DATABASE_URL not set in .env")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from pgvector.psycopg import register_vector
    from src.api import db as api_db
    from src.cluster import run
    from src.db import connect
    from src.init_db import apply_schema
    from tests.cluster.test_cluster import _add, blobs

    schema = f"api_test_{uuid.uuid4().hex[:8]}"
    conn = connect(autocommit=True, direct=True)
    try:
        apply_schema(conn, schema)
        register_vector(conn)
        conn.execute("INSERT INTO sources(name, base_url) VALUES ('wisden', '')")
        X, truth, _ = blobs(3, 6, seed=11)
        _add(conn, X, truth, "a")                                  # 18 articles, 3 topics, published today
        run.fit(conn, echo=lambda *_: None)
        # one article still waiting for the pipeline, one older article for date filters
        conn.execute("INSERT INTO articles(source_id, url, canonical_url, title, published_at, body, content_hash, status) "
                     "VALUES (1, 'w1', 'w1', 'Waiting for NLP', now(), 'b', 'hw1', 'cleaned'), "
                     "(1, 'o1', 'o1', 'Old IPL story', now() - interval '20 days', 'b', 'ho1', 'cleaned')")
        os.environ["API_DB_SCHEMA"] = schema
        api_db.close()                                             # next request opens a pool on the test schema
        from src.api.app import app
        with TestClient(app) as c:
            yield c
    finally:
        api_db.close()
        os.environ.pop("API_DB_SCHEMA", None)
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        conn.close()


def test_status_has_version_and_refresh_info(client):
    s = client.get("/api/status").json()
    assert s["articles"] == 20 and s["processing"] == 2 and s["model_id"]
    assert s["version"].startswith("20-")


def test_meta_lists_filter_options(client):
    m = client.get("/api/meta").json()
    assert m["sources"] == ["wisden"] and len(m["topics"]) == 3 and m["dates"]["max"] == str(date.today())


def test_overview_counts_and_distributions(client):
    o = client.get("/api/overview?days=7").json()
    assert o["total"] == 20 and o["in_period"] == 20 and o["n_topics"] == 3
    assert sum(t["articles"] for t in o["topics"]) == 18
    assert o["by_source"] == [{"source": "wisden", "articles": 20}]
    assert len(o["recent"]) == 8
    assert len(o["daily"]) == 8 and sum(d["articles"] for d in o["daily"]) == 20     # 7 days + today, zeros filled
    assert o["daily"][-1]["day"] == str(date.today())
    assert client.get("/api/overview/all").json()["total"] == 20
    assert o["n_sources"] == 1
    assert o["in_previous"] is None          # collection started within the period: no fake comparison


def test_articles_carry_image_and_summary(client):
    item = client.get("/api/articles?page_size=5").json()["items"][0]
    assert "image_url" in item and item["summary"] == "b"                  # test bodies are just "b"


def test_serverless_mode_uses_one_connection_per_request(client, monkeypatch):
    """On Vercel there is no pool: each request opens and closes its own connection."""
    from src.api import db as api_db
    monkeypatch.setattr(api_db, "SERVERLESS", True)
    assert client.get("/api/status").json()["articles"] == 20
    assert client.get("/api/topics/map?method=pca").json()["method"] == "pca"


def test_vercel_entry_point_exposes_the_app():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("vercel_entry", Path(__file__).resolve().parents[2] / "api" / "index.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from src.api.app import app
    assert mod.app is app


def test_map_projection_can_be_chosen(client):
    assert client.get("/api/topics/map?method=pca").json()["method"] == "pca"
    assert client.get("/api/topics/map?method=tsne").status_code == 422


def test_articles_search_filter_sort_paginate(client):
    page = client.get("/api/articles?page_size=5&sort=newest").json()
    assert page["total"] == 20 and len(page["items"]) == 5
    assert client.get("/api/articles?q=old ipl").json()["total"] == 1
    assert client.get("/api/articles?topic=none").json()["total"] == 2
    a_topic = client.get("/api/meta").json()["topics"][0]["id"]
    in_topic = client.get(f"/api/articles?topic={a_topic}&sort=relevance").json()
    assert in_topic["total"] == 6 and all(i["topic_id"] == a_topic for i in in_topic["items"])
    scores = [i["topic_score"] for i in in_topic["items"]]
    assert scores == sorted(scores, reverse=True)
    week_ago = date.today() - timedelta(days=7)
    assert client.get(f"/api/articles?date_to={week_ago}").json()["total"] == 1
    assert client.get("/api/articles?q=%25").json()["total"] == 0        # LIKE wildcards are escaped
    assert client.get("/api/articles?topic=abc").status_code == 422


def test_topics_and_map(client):
    t = client.get("/api/topics").json()
    assert len(t["topics"]) == 3 and t["model"]["algorithm"] == "hdbscan"
    first = t["topics"][0]
    assert first["articles"] == 6 and first["terms"] and len(first["headlines"]) == 3
    m = client.get("/api/topics/map").json()
    assert m["method"] in ("umap", "pca") and len(m["points"]) == 18
    assert all(0 <= p["x"] <= 1 and 0 <= p["y"] <= 1 for p in m["points"])


def test_trends_volume_vs_growth(client):
    today = date.today()
    t = client.get(f"/api/trends?date_from={today - timedelta(days=13)}&date_to={today}").json()
    assert len(t["days"]) == 14 and t["total"][-1] == 19                  # 18 in topics + 1 waiting
    assert len(t["topics"]) == 3
    for topic in t["topics"]:
        assert topic["total"] == 6 and topic["recent"] == 6 and topic["previous"] == 0 and topic["is_new"]
    assert t["comparison"]["recent"][1] == str(today)
    assert client.get("/api/trends?source=nobody").json()["topics"] == []
    assert client.get(f"/api/trends?date_from={today}&date_to={today - timedelta(days=1)}").status_code == 400
