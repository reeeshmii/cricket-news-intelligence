"""SQL for the dashboard. Every number shown on the dashboard comes from these queries.

Dates: "collected" = articles.scraped_at; "published" = COALESCE(published_at, scraped_at),
counted per UTC day. Topics always come from the ACTIVE clustering model.
"""
from datetime import date, datetime, timedelta, timezone

DAY = "(COALESCE(a.published_at, a.scraped_at) AT TIME ZONE 'UTC')::date"


def active_model(conn) -> dict | None:
    return conn.execute("SELECT id, algorithm, params, created_at FROM cluster_models WHERE is_active").fetchone()


def _model_id(conn) -> int:
    m = active_model(conn)
    return m["id"] if m else -1


# ------------------------------------------------------------------ status
def status(conn) -> dict:
    row = conn.execute("""
        SELECT (SELECT count(*) FROM articles)                                    AS articles,
               (SELECT coalesce(max(id), 0) FROM articles)                        AS max_article,
               (SELECT id FROM cluster_models WHERE is_active)                    AS model_id,
               (SELECT count(*) FROM article_clusters)                            AS assignments,
               (SELECT coalesce(max(id), 0) FROM crawl_runs)                      AS crawl_runs,
               (SELECT max(finished_at) FROM crawl_runs
                 WHERE finished_at IS NOT NULL AND (details IS NULL OR details->>'failed' IS NULL)) AS last_crawl,
               (SELECT max(processed_at) FROM article_nlp)                        AS last_nlp,
               greatest((SELECT max(created_at) FROM cluster_models),
                        (SELECT max(assigned_at) FROM article_clusters))          AS last_topics,
               (SELECT count(*) FROM articles WHERE status <> 'clustered')        AS processing
    """).fetchone()
    # The version changes whenever anything the dashboard shows could have changed;
    # the frontend polls it and refetches only then.
    row["version"] = "-".join(str(row[k]) for k in ("articles", "max_article", "model_id", "assignments", "crawl_runs"))
    return row


# ------------------------------------------------------------------ meta (filter options)
def meta(conn) -> dict:
    model = _model_id(conn)
    return {
        "sources": [r["name"] for r in conn.execute(
            "SELECT DISTINCT s.name FROM sources s JOIN articles a ON a.source_id = s.id ORDER BY 1")],
        "topics": conn.execute(
            "SELECT id, label, stable_key FROM clusters WHERE model_id = %s ORDER BY label", (model,)).fetchall(),
        "dates": conn.execute(f"SELECT min({DAY}) AS min, max({DAY}) AS max FROM articles a").fetchone(),
    }


# ------------------------------------------------------------------ articles
ARTICLE_COLUMNS = f"""
    a.id, a.title, a.url, s.name AS source, a.published_at, a.scraped_at, {DAY} AS day, a.status,
    t.id AS topic_id, t.label AS topic_label, t.score AS topic_score, n.sentiment, n.keywords,
    a.image_url, left(regexp_replace(a.body, '[[:space:]]+', ' ', 'g'), 280) AS summary
"""
ARTICLE_FROM = """
    FROM articles a
    JOIN sources s ON s.id = a.source_id
    LEFT JOIN article_nlp n ON n.article_id = a.id
    LEFT JOIN LATERAL (
        SELECT c.id, c.label, ac.score FROM article_clusters ac JOIN clusters c ON c.id = ac.cluster_id
        WHERE ac.article_id = a.id AND c.model_id = %(model)s LIMIT 1) t ON TRUE
"""
SORTS = {
    "newest": "COALESCE(a.published_at, a.scraped_at) DESC, a.id DESC",
    "oldest": "COALESCE(a.published_at, a.scraped_at) ASC, a.id ASC",
    "title": "lower(a.title) ASC, a.id",
    "source": "s.name ASC, COALESCE(a.published_at, a.scraped_at) DESC",
    "topic": "t.label ASC NULLS LAST, COALESCE(a.published_at, a.scraped_at) DESC",
    "relevance": "t.score DESC NULLS LAST, a.id DESC",       # closeness to the topic centre
}


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def articles(conn, q=None, source=None, topic=None, date_from=None, date_to=None,
             sort="newest", page=1, page_size=20) -> dict:
    """topic: a cluster id, or "none" for articles that are in no topic."""
    p = {"model": _model_id(conn)}
    where = ["a.duplicate_of IS NULL"]
    if q:
        p["q"] = _like(q.strip())
        where.append("(a.title ILIKE %(q)s OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(n.keywords) k "
                     "WHERE k ILIKE %(q)s))")
    if source:
        p["source"] = source
        where.append("s.name = %(source)s")
    if topic == "none":
        where.append("t.id IS NULL")
    elif topic:
        p["topic"] = int(topic)
        where.append("t.id = %(topic)s")
    if date_from:
        p["date_from"] = date_from
        where.append(f"{DAY} >= %(date_from)s")
    if date_to:
        p["date_to"] = date_to
        where.append(f"{DAY} <= %(date_to)s")
    filters = " WHERE " + " AND ".join(where)
    total = conn.execute(f"SELECT count(*) AS n {ARTICLE_FROM} {filters}", p).fetchone()["n"]
    p.update(limit=page_size, offset=(page - 1) * page_size)
    items = conn.execute(f"SELECT {ARTICLE_COLUMNS} {ARTICLE_FROM} {filters} "
                         f"ORDER BY {SORTS.get(sort, SORTS['newest'])} LIMIT %(limit)s OFFSET %(offset)s", p).fetchall()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ------------------------------------------------------------------ overview
def overview(conn, days: int | None) -> dict:
    model = _model_id(conn)
    since = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    p = {"model": model, "since": since}
    period = "(%(since)s::timestamptz IS NULL OR a.scraped_at >= %(since)s::timestamptz)"
    p["prev_since"] = since - timedelta(days=days) if since else None
    totals = conn.execute(f"""
        SELECT count(*) AS total, count(*) FILTER (WHERE {period}) AS in_period,
               count(*) FILTER (WHERE a.scraped_at >= %(prev_since)s::timestamptz
                                  AND a.scraped_at < %(since)s::timestamptz) AS in_previous,
               min(a.scraped_at) AS first_collected,
               count(DISTINCT a.source_id) AS n_sources
        FROM articles a WHERE a.duplicate_of IS NULL""", p).fetchone()
    by_source = conn.execute(f"""
        SELECT s.name AS source, count(*) AS articles FROM articles a JOIN sources s ON s.id = a.source_id
        WHERE a.duplicate_of IS NULL AND {period} GROUP BY 1 ORDER BY 2 DESC, 1""", p).fetchall()
    topics = conn.execute(f"""
        SELECT c.id, c.label, count(a.id) AS articles
        FROM clusters c
        LEFT JOIN article_clusters ac ON ac.cluster_id = c.id
        LEFT JOIN articles a ON a.id = ac.article_id AND {period}
        WHERE c.model_id = %(model)s GROUP BY c.id, c.label ORDER BY 3 DESC, 2""", p).fetchall()
    unassigned = conn.execute(f"""
        SELECT count(*) AS n FROM articles a
        WHERE a.status = 'clustered' AND {period} AND NOT EXISTS (
            SELECT 1 FROM article_clusters ac JOIN clusters c ON c.id = ac.cluster_id
            WHERE ac.article_id = a.id AND c.model_id = %(model)s)""", p).fetchone()["n"]
    recent = conn.execute(f"SELECT {ARTICLE_COLUMNS} {ARTICLE_FROM} WHERE a.duplicate_of IS NULL "
                          "ORDER BY a.scraped_at DESC, a.id DESC LIMIT 8", p).fetchall()
    # new articles per collection day in the period (days without articles included as 0)
    counts = {r["day"]: r["n"] for r in conn.execute(f"""
        SELECT (a.scraped_at AT TIME ZONE 'UTC')::date AS day, count(*) AS n FROM articles a
        WHERE a.duplicate_of IS NULL AND {period} GROUP BY 1""", p)}
    daily = []
    if counts:
        today = datetime.now(timezone.utc).date()
        first = (since.date() if since else min(counts))
        daily = [{"day": first + timedelta(days=i), "articles": counts.get(first + timedelta(days=i), 0)}
                 for i in range((today - first).days + 1)]
    m = active_model(conn)
    return {
        "days": days, "total": totals["total"], "in_period": totals["in_period"],
        # previous period of the same length; None when collection had not started then,
        # so the dashboard never shows a change against a period with no data
        "in_previous": totals["in_previous"] if since and totals["first_collected"]
                       and totals["first_collected"] < since - timedelta(days=days) else None,
        "n_sources": totals["n_sources"],
        "n_topics": len(topics), "unassigned_in_period": unassigned,
        "by_source": by_source, "topics": topics, "recent": recent, "daily": daily,
        "model": {"id": m["id"], "algorithm": m["algorithm"], "fitted_at": m["created_at"]} if m else None,
        "status": status(conn),
    }


# ------------------------------------------------------------------ topics
def topics(conn) -> dict:
    m = active_model(conn)
    if not m:
        return {"model": None, "topics": [], "unassigned": 0}
    rows = conn.execute("""
        SELECT c.id, c.stable_key, c.label, c.top_terms, count(ac.article_id) AS articles
        FROM clusters c LEFT JOIN article_clusters ac ON ac.cluster_id = c.id
        WHERE c.model_id = %s GROUP BY c.id ORDER BY articles DESC, c.label""", (m["id"],)).fetchall()
    heads = conn.execute("""
        SELECT * FROM (
            SELECT ac.cluster_id, a.id, a.title, a.url, s.name AS source, ac.score,
                   row_number() OVER (PARTITION BY ac.cluster_id ORDER BY ac.score DESC, a.id) AS rn
            FROM article_clusters ac
            JOIN clusters c ON c.id = ac.cluster_id AND c.model_id = %s
            JOIN articles a ON a.id = ac.article_id
            JOIN sources s ON s.id = a.source_id) x
        WHERE rn <= 3 ORDER BY cluster_id, rn""", (m["id"],)).fetchall()
    by_cluster: dict[int, list] = {}
    for h in heads:
        by_cluster.setdefault(h["cluster_id"], []).append(
            {k: h[k] for k in ("id", "title", "url", "source", "score")})
    unassigned = conn.execute("""
        SELECT count(*) AS n FROM articles a WHERE a.status = 'clustered' AND NOT EXISTS (
            SELECT 1 FROM article_clusters ac JOIN clusters c ON c.id = ac.cluster_id
            WHERE ac.article_id = a.id AND c.model_id = %s)""", (m["id"],)).fetchone()["n"]
    params = m["params"] or {}
    return {
        "model": {"id": m["id"], "algorithm": m["algorithm"], "fitted_at": m["created_at"],
                  "fitted_on": params.get("fitted_on"), "assign_threshold": params.get("assign_threshold"),
                  "metrics": params.get("metrics"), "baseline": params.get("baseline_kmeans"),
                  "umap": params.get("umap")},
        "topics": [{"id": r["id"], "stable_key": r["stable_key"], "label": r["label"], "articles": r["articles"],
                    "terms": (r["top_terms"] or {}).get("terms", []),
                    "entities": (r["top_terms"] or {}).get("entities", {}),
                    "coherence": (r["top_terms"] or {}).get("coherence_npmi"),
                    "headlines": by_cluster.get(r["id"], [])} for r in rows],
        "unassigned": unassigned,
    }


def projection(conn, method: str) -> dict:
    """Stored 2-D map coordinates (computed by the cluster stage) + each article's cluster."""
    rows = conn.execute("""
        SELECT a.id, a.title, s.name AS source, p.x, p.y, t.cluster_id
        FROM article_projection p
        JOIN articles a ON a.id = p.article_id
        JOIN sources s  ON s.id = a.source_id
        LEFT JOIN LATERAL (SELECT ac.cluster_id FROM article_clusters ac JOIN clusters c ON c.id = ac.cluster_id
                           WHERE ac.article_id = a.id AND c.model_id = %(model)s LIMIT 1) t ON TRUE
        WHERE p.method = %(method)s ORDER BY a.id""", {"model": _model_id(conn), "method": method}).fetchall()
    return {"method": method if rows else None,
            "points": [{**r, "x": round(float(r["x"]), 4), "y": round(float(r["y"]), 4)} for r in rows]}


# ------------------------------------------------------------------ trends
def trends(conn, date_from: date, date_to: date, source: str | None = None) -> dict:
    """Daily topic frequency + total volume, and growth: the later half of the range vs the
    earlier half. Without a source filter, days older than the oldest stored article are
    filled from topic_daily_stats (history kept past the crawler's rolling cap)."""
    model = _model_id(conn)
    days = [date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1)]
    p = {"model": model, "f": date_from, "t": date_to, "source": source}
    src = "AND s.name = %(source)s" if source else ""
    live = conn.execute(f"""
        SELECT {DAY} AS day, c.stable_key, count(*) AS n
        FROM articles a JOIN sources s ON s.id = a.source_id
        JOIN article_clusters ac ON ac.article_id = a.id
        JOIN clusters c ON c.id = ac.cluster_id AND c.model_id = %(model)s
        WHERE a.duplicate_of IS NULL AND {DAY} BETWEEN %(f)s AND %(t)s {src}
        GROUP BY 1, 2""", p).fetchall()
    totals = {r["day"]: r["n"] for r in conn.execute(f"""
        SELECT {DAY} AS day, count(*) AS n FROM articles a JOIN sources s ON s.id = a.source_id
        WHERE a.duplicate_of IS NULL AND {DAY} BETWEEN %(f)s AND %(t)s {src} GROUP BY 1""", p)}

    counts: dict[str, dict] = {}
    for r in live:
        counts.setdefault(r["stable_key"], {})[r["day"]] = r["n"]
    coverage_start = conn.execute(f"SELECT min({DAY}) AS d FROM articles a").fetchone()["d"]
    history_used = False
    if not source and coverage_start and date_from < coverage_start:
        for r in conn.execute("""
            SELECT day, stable_key, article_count FROM (
                SELECT s.day, c.stable_key, s.article_count,
                       row_number() OVER (PARTITION BY s.day, c.stable_key ORDER BY s.model_id DESC) AS rn
                FROM topic_daily_stats s JOIN clusters c ON c.id = s.cluster_id
                WHERE s.day >= %s AND s.day < %s AND c.stable_key IS NOT NULL) x WHERE rn = 1""",
                (date_from, coverage_start)):
            counts.setdefault(r["stable_key"], {})[r["day"]] = r["article_count"]
            history_used = True

    labels = {r["stable_key"]: r for r in conn.execute("""
        SELECT DISTINCT ON (c.stable_key) c.stable_key, c.label, c.id, (c.model_id = %s) AS active
        FROM clusters c WHERE c.stable_key IS NOT NULL
        ORDER BY c.stable_key, (c.model_id = %s) DESC, c.model_id DESC""", (model, model))}

    half = len(days) // 2
    previous_days, recent_days = days[len(days) - 2 * half:len(days) - half], days[len(days) - half:]
    out = []
    for key, by_day in counts.items():
        series = [by_day.get(d, 0) for d in days]
        prev = sum(by_day.get(d, 0) for d in previous_days)
        rec = sum(by_day.get(d, 0) for d in recent_days)
        info = labels.get(key, {})
        out.append({"stable_key": key, "label": info.get("label", key),
                    "cluster_id": info.get("id") if info.get("active") else None,
                    "series": series, "total": sum(series), "previous": prev, "recent": rec,
                    "change": rec - prev, "growth_pct": round(100 * (rec - prev) / prev, 1) if prev else None,
                    "is_new": prev == 0 and rec > 0})
    out.sort(key=lambda r: (-r["total"], r["label"]))
    return {
        "date_from": date_from, "date_to": date_to, "source": source, "days": days,
        "total": [totals.get(d, 0) for d in days], "topics": out,
        "comparison": {"previous": [previous_days[0], previous_days[-1]] if previous_days else None,
                       "recent": [recent_days[0], recent_days[-1]] if recent_days else None},
        "coverage_start": coverage_start, "history_used": history_used,
    }
