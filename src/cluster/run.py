"""Cluster stage runner.

  python -m src.cluster.run                    # auto: assign new articles, re-fit when needed
  python -m src.cluster.run --fit              # force a full re-fit
  python -m src.cluster.run --fit --algorithm kmeans
  python -m src.cluster.run --fit --dry-run    # show the topics it would create, write nothing
  python -m src.cluster.run --every 30         # keep running

Fit:    all recent articles -> HDBSCAN topics (KMeans baseline for comparison) -> c-TF-IDF labels
        -> new active cluster_models row; topics keep their stable_key across re-fits.
Assign: articles with status 'vectorized' join the nearest topic if close enough; the rest
        stay unassigned ("emerging") until enough of them trigger a re-fit.
Both end with refresh_topic_daily_stats(), which preserves trend history past the rolling cap.
"""
import argparse
import sys
import time
import uuid
from datetime import datetime, timezone

import numpy as np
from psycopg.types.json import Jsonb

from ..db import connect
from . import labels as lb
from . import model, settings


class ClusterBusy(Exception):
    pass


LOAD_WINDOW = """
SELECT a.id, v.embedding, n.lemmas, n.entities
FROM articles a
JOIN article_vectors v ON v.article_id = a.id
JOIN article_nlp n     ON n.article_id = a.id
WHERE a.duplicate_of IS NULL AND a.status IN ('vectorized', 'clustered')
  AND COALESCE(a.published_at, a.scraped_at) >= now() - make_interval(days => %s)
ORDER BY a.id
"""


def _vec(v) -> np.ndarray:
    """pgvector returns Vector objects (or arrays, depending on the version)."""
    return np.asarray(v.to_numpy() if hasattr(v, "to_numpy") else v, dtype=np.float32)


def active_model(conn):
    return conn.execute("SELECT id, params, created_at FROM cluster_models WHERE is_active").fetchone()


# ======================================== fit ========================================
def fit(conn, algorithm: str = "hdbscan", dry_run: bool = False, echo=print) -> dict | None:
    rows = conn.execute(LOAD_WINDOW, (settings.WINDOW_DAYS,)).fetchall()
    if len(rows) < settings.MIN_ARTICLES:
        echo(f"fit: only {len(rows)} articles ready (need {settings.MIN_ARTICLES}); skipping")
        return None
    ids = [r[0] for r in rows]
    X = model.normalise(np.vstack([_vec(r[1]) for r in rows]))
    lemmas, entities = [r[2] for r in rows], [r[3] or {} for r in rows]

    baseline = model.kmeans_fit(X)
    primary = baseline if algorithm == "kmeans" else model.hdbscan_fit(X)
    if primary.algorithm == "hdbscan" and len(set(primary.labels.tolist()) - {-1}) < 2:
        echo("fit: HDBSCAN found fewer than 2 topics; falling back to the KMeans baseline")
        primary = model.TopicFit("kmeans", baseline.labels, {**baseline.params, "fallback_from": "hdbscan"})
    labels = primary.labels

    vocab = lb.Vocabulary(lemmas)
    terms = lb.ctfidf_terms(vocab, labels)
    cents = model.centroids(X, labels)
    names = lb.token_names(entities)
    metrics = {**model.geometry_metrics(X, labels),
               "coherence_npmi": round(float(np.mean([lb.npmi(vocab, t) for t in terms.values()])), 4)}
    base_terms = lb.ctfidf_terms(vocab, baseline.labels)
    baseline_metrics = {**model.geometry_metrics(X, baseline.labels),
                        "coherence_npmi": round(float(np.mean([lb.npmi(vocab, t) for t in base_terms.values()])), 4),
                        **baseline.params}

    previous = []
    if (old := active_model(conn)):
        previous = [(k, _vec(c)) for k, c in conn.execute(
            "SELECT stable_key, centroid FROM clusters WHERE model_id = %s AND stable_key IS NOT NULL", (old[0],))]
    keys = model.match_stable_keys(previous, cents, lambda: uuid.uuid4().hex[:10])

    topics = []
    for t, c in cents.items():
        members = np.where(labels == t)[0]
        topics.append({
            "t": t, "label": lb.make_label(terms[t], names), "stable_key": keys[t], "centroid": c,
            "members": [(ids[i], round(float(X[i] @ c), 4)) for i in members],
            "top_terms": {"terms": terms[t], "entities": lb.topic_entities([entities[i] for i in members]),
                          "coherence_npmi": lb.npmi(vocab, terms[t])},
        })
    topics.sort(key=lambda d: -len(d["members"]))
    params = {**primary.params, "assign_threshold": model.assign_threshold(X, labels),
              "window_days": settings.WINDOW_DAYS, "metrics": metrics, "baseline_kmeans": baseline_metrics,
              "fitted_on": len(ids), "carried_over_topics": sum(k in dict(previous) for k in keys.values())}

    echo(f"fit: {primary.algorithm} -> {metrics['n_topics']} topics, {metrics['unassigned']} unassigned of "
         f"{len(ids)} | silhouette {metrics.get('silhouette')} | NPMI {metrics['coherence_npmi']} "
         f"(kmeans k={baseline.params['k']}: silhouette {baseline_metrics.get('silhouette')}, "
         f"NPMI {baseline_metrics['coherence_npmi']})")
    for d in topics:
        echo(f"  [{len(d['members']):>3}] {d['label']}")
    if dry_run:
        return {"params": params, "topics": topics}

    with conn.transaction():
        conn.execute("UPDATE cluster_models SET is_active = FALSE WHERE is_active")
        model_id = conn.execute(
            "INSERT INTO cluster_models(algorithm, params, n_clusters, silhouette, is_active) "
            "VALUES (%s, %s, %s, %s, TRUE) RETURNING id",
            (primary.algorithm, Jsonb(params), len(topics), metrics.get("silhouette"))).fetchone()[0]
        for d in topics:
            cid = conn.execute(
                "INSERT INTO clusters(model_id, label, top_terms, centroid, size, stable_key) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (model_id, d["label"], Jsonb(d["top_terms"]), d["centroid"], len(d["members"]),
                 d["stable_key"])).fetchone()[0]
            with conn.cursor() as cur:
                cur.executemany("INSERT INTO article_clusters(article_id, cluster_id, score) VALUES (%s, %s, %s)",
                                [(aid, cid, score) for aid, score in d["members"]])
        conn.execute("UPDATE articles SET status = 'clustered' WHERE id = ANY(%s) AND status = 'vectorized'", (ids,))
        # keep topics + trend rows of old models, but drop their per-article rows to bound table size
        conn.execute("""DELETE FROM article_clusters WHERE cluster_id IN (
                          SELECT c.id FROM clusters c WHERE c.model_id NOT IN (
                            SELECT id FROM cluster_models ORDER BY id DESC LIMIT %s))""",
                     (settings.KEEP_ASSIGNMENTS_FOR_MODELS,))
    refreshed = conn.execute("SELECT refresh_topic_daily_stats()").fetchone()[0]
    echo(f"fit: model {model_id} active; {params['carried_over_topics']} topics carried over; "
         f"{refreshed} daily trend rows refreshed")
    return {"model_id": model_id, "params": params, "topics": topics}


# ======================================== assign ========================================
def assign(conn, dry_run: bool = False, echo=print) -> dict | None:
    current = active_model(conn)
    if not current:
        return None
    model_id, params, _ = current
    clusters = conn.execute("SELECT id, label, centroid FROM clusters WHERE model_id = %s", (model_id,)).fetchall()
    C = model.normalise(np.vstack([_vec(c[2]) for c in clusters]))
    rows = conn.execute("SELECT a.id, a.title, v.embedding FROM articles a JOIN article_vectors v "
                        "ON v.article_id = a.id WHERE a.status = 'vectorized' AND a.duplicate_of IS NULL "
                        "ORDER BY a.id").fetchall()
    threshold = params.get("assign_threshold", settings.ASSIGN_FLOOR)
    assigned, emerging = [], []
    for aid, title, emb in rows:
        sims = C @ model.normalise(_vec(emb)[None, :])[0]
        j = int(np.argmax(sims))
        (assigned if sims[j] >= threshold else emerging).append((aid, clusters[j][0], round(float(sims[j]), 4), title))
    for aid, cid, s, title in assigned:
        echo(f"  -> {next(c[1] for c in clusters if c[0] == cid)} ({s:.2f}): {title[:70]}")
    for aid, _, s, title in emerging:
        echo(f"  ?  emerging (best {s:.2f} < {threshold}): {title[:70]}")
    if dry_run or not rows:
        return {"assigned": len(assigned), "emerging": len(emerging)}

    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO article_clusters(article_id, cluster_id, score) VALUES (%s, %s, %s) "
                            "ON CONFLICT DO NOTHING", [(a, c, s) for a, c, s, _ in assigned])
        conn.execute("UPDATE articles SET status = 'clustered' WHERE id = ANY(%s) AND status = 'vectorized'",
                     ([r[0] for r in rows],))
        conn.execute("UPDATE clusters c SET size = (SELECT count(*) FROM article_clusters ac "
                     "WHERE ac.cluster_id = c.id) WHERE c.model_id = %s", (model_id,))
    conn.execute("SELECT refresh_topic_daily_stats()")
    return {"assigned": len(assigned), "emerging": len(emerging)}


def refit_reason(conn) -> str | None:
    """Why the active model should be replaced, or None."""
    current = active_model(conn)
    if not current:
        return "no active model"
    model_id, params, created_at = current
    age_days = (datetime.now(timezone.utc) - created_at).total_seconds() / 86400
    if age_days > settings.REFIT_MAX_AGE_DAYS:
        return f"model is {age_days:.1f} days old"
    fitted = params.get("fitted_on", 0) or 1
    emerging = conn.execute(
        "SELECT count(*) FROM articles a WHERE a.status = 'clustered' AND a.scraped_at > %s "
        "AND NOT EXISTS (SELECT 1 FROM article_clusters ac JOIN clusters c ON c.id = ac.cluster_id "
        "WHERE ac.article_id = a.id AND c.model_id = %s)", (created_at, model_id)).fetchone()[0]
    if emerging >= max(settings.EMERGING_MIN, settings.EMERGING_SHARE * fitted):
        return f"{emerging} new articles fit no topic"
    window = conn.execute(f"SELECT count(*) FROM ({LOAD_WINDOW}) w", (settings.WINDOW_DAYS,)).fetchone()[0]
    if window >= settings.GROWTH_FACTOR * fitted:
        return f"corpus grew from {fitted} to {window} articles"
    return None


# ======================================== entry points ========================================
def run_once(mode: str = "auto", algorithm: str = "hdbscan", dry_run: bool = False, echo=print) -> dict:
    with connect(autocommit=True, direct=True) as conn:
        if not dry_run and not conn.execute("SELECT pg_try_advisory_lock(%s)",
                                            (settings.CLUSTER_LOCK_KEY,)).fetchone()[0]:
            raise ClusterBusy("another cluster run is in progress")
        result = {}
        if mode == "fit":
            result["fit"] = fit(conn, algorithm, dry_run, echo)
            return result
        if mode in ("auto", "assign") and active_model(conn):
            result["assign"] = assign(conn, dry_run, echo)
        if mode == "auto":
            reason = refit_reason(conn)
            if reason:
                echo(f"re-fit: {reason}")
                result["fit"] = fit(conn, algorithm, dry_run, echo)
        assigned = result.get("assign") or {}
        if not result.get("fit") and not assigned.get("assigned") and not assigned.get("emerging"):
            echo("nothing new to cluster")
        return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--fit", action="store_true", help="force a full re-fit")
    group.add_argument("--assign", action="store_true", help="only assign new articles, never re-fit")
    ap.add_argument("--algorithm", choices=["hdbscan", "kmeans"], default="hdbscan")
    ap.add_argument("--dry-run", action="store_true", help="print results, write nothing")
    ap.add_argument("--every", type=float, help="keep running, checking every N minutes")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mode = "fit" if a.fit else "assign" if a.assign else "auto"
    try:
        while True:
            try:
                run_once(mode, a.algorithm, a.dry_run)
            except ClusterBusy as e:
                print(f"Skipped: {e}")
            except Exception as e:
                if not a.every:
                    raise
                print(f"run failed: {type(e).__name__}: {e}")
            if not a.every:
                return
            time.sleep(a.every * 60)
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
