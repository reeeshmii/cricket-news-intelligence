"""Cluster stage tests.

Synthetic embeddings with known topics test the algorithms offline. The lifecycle test runs
against Neon inside a throwaway schema (dropped afterwards), so real data is never touched.
"""
import uuid
from datetime import date

import numpy as np
import pytest
from psycopg import sql
from sklearn.metrics import adjusted_rand_score

from src import config
from src.cluster import labels as lb
from src.cluster import model, settings

needs_db = pytest.mark.skipif(not config.DATABASE_URL, reason="DATABASE_URL not set in .env")
DIM = 384


def blobs(n_topics: int, per_topic: int, seed: int = 0, spread: float = 0.038):
    """Unit vectors around random topic centres: ~0.8 cosine to their centre, like real news."""
    rng = np.random.default_rng(seed)
    centres = model.normalise(rng.normal(size=(n_topics, DIM)))
    X = np.vstack([model.normalise(c + spread * rng.normal(size=(per_topic, DIM))) for c in centres])
    return X.astype(np.float32), np.repeat(np.arange(n_topics), per_topic), centres


# ------------------------------ algorithms ------------------------------
def test_hdbscan_recovers_topics_on_small_corpus():
    X, truth, _ = blobs(4, 8)
    fit = model.hdbscan_fit(X)
    assert fit.params["umap"] is None                                   # small: raw cosine
    assert adjusted_rand_score(truth, fit.labels) > 0.9


def test_hdbscan_uses_umap_on_large_corpus():
    X, truth, _ = blobs(8, 40, seed=1)                                  # 320 >= UMAP_MIN_ARTICLES
    fit = model.hdbscan_fit(X)
    assert fit.params["umap"] is not None
    assert adjusted_rand_score(truth, fit.labels) > 0.9


def test_hdbscan_leaves_outliers_unassigned():
    X, _, _ = blobs(3, 8)
    outliers = model.normalise(np.random.default_rng(9).normal(size=(3, DIM))).astype(np.float32)
    labels = model.hdbscan_fit(np.vstack([X, outliers])).labels
    assert (labels[-3:] == -1).all() and (labels[:-3] >= 0).all()


def test_real_news_embeddings_do_not_collapse():
    """Regression on REAL data: the embeddings of the 58 live articles of 9 Oct 2026 (vectors
    only, no text). HDBSCAN's default min_samples merged them into topics of 43 + 7; the
    guarded fit must keep the separate stories apart."""
    from pathlib import Path
    from sklearn.cluster import HDBSCAN
    X = np.load(Path(__file__).parent / "fixtures" / "live_embeddings_58.npy")
    old = HDBSCAN(min_cluster_size=model.min_cluster_size(len(X)), metric="cosine").fit_predict(X)
    assert model._largest_share(old) > 0.8                      # the failure this test guards against
    fit = model.hdbscan_fit(X)
    assigned = fit.labels[fit.labels >= 0]
    assert len(set(assigned.tolist())) >= 5
    assert model._largest_share(fit.labels) <= settings.MAX_TOPIC_SHARE
    assert {"method", "topics", "largest_share", "valid"} <= set(fit.params["candidates"][0])


def test_kmeans_baseline_picks_k_by_silhouette():
    X, truth, _ = blobs(5, 8, seed=2)
    fit = model.kmeans_fit(X)
    assert fit.params["k"] == 5 and adjusted_rand_score(truth, fit.labels) > 0.95


def test_metrics_and_assign_threshold():
    X, truth, _ = blobs(3, 10, seed=3)
    m = model.geometry_metrics(X, truth)
    assert m["n_topics"] == 3 and m["coverage"] == 1.0 and m["silhouette"] > 0.4
    t = model.assign_threshold(X, truth)
    assert settings.ASSIGN_FLOOR <= t < 0.9


def test_stable_keys_survive_a_refit():
    _, _, centres = blobs(3, 1, seed=4)
    previous = [("auction", centres[0]), ("injuries", centres[1])]
    drifted = {0: model.normalise(centres[1][None] + 0.01)[0],         # topic order changed, slight drift
               1: model.normalise(centres[0][None] + 0.01)[0],
               2: centres[2]}                                           # brand-new topic
    keys = model.match_stable_keys(previous, drifted, lambda: "fresh")
    assert keys == {0: "injuries", 1: "auction", 2: "fresh"}


# ------------------------------ interpretation ------------------------------
LEMMAS = ["sa20 auction joburg_super_kings faf_du_plessis purse"] * 3 + \
         ["shreyas_iyer century t20i west_indies chase"] * 3 + \
         ["injury hamstring scan rule bumrah"] * 2


def test_ctfidf_finds_each_topics_own_terms():
    vocab = lb.Vocabulary(LEMMAS)
    terms = lb.ctfidf_terms(vocab, np.array([0, 0, 0, 1, 1, 1, 2, 2]))
    assert {"auction", "sa20"} <= set(terms[0][:5])
    assert {"shreyas_iyer", "century"} <= set(terms[1][:5])
    assert "hamstring" in terms[2]


def test_npmi_separates_coherent_from_random_terms():
    vocab = lb.Vocabulary(LEMMAS)
    assert lb.npmi(vocab, ["auction", "sa20", "purse"]) > 0.9
    assert lb.npmi(vocab, ["auction", "century", "hamstring"]) == -1.0


def test_labels_use_real_names():
    names = lb.token_names([{"TEAM": {"Joburg Super Kings": 2}, "PERSON": {"Faf du Plessis": 1}}])
    assert lb.make_label(["sa20", "auction", "joburg_super_kings"], names) == "SA20 · Auction · Joburg Super Kings"
    assert lb.pretty("faf_du_plessis", names) == "Faf du Plessis"


# ------------------------------ full lifecycle against Neon ------------------------------
TOPIC_WORDS = ["sa20 auction joburg_super_kings purse bid", "shreyas_iyer century t20i chase west_indies",
               "injury hamstring scan bumrah ruled", "wpl schedule summer home women"]


@pytest.fixture
def conn():
    from pgvector.psycopg import register_vector
    from src.db import connect
    from src.init_db import apply_schema
    schema = f"cluster_test_{uuid.uuid4().hex[:8]}"
    c = connect(autocommit=True, direct=True)
    try:
        apply_schema(c, schema)
        register_vector(c)
        c.execute("INSERT INTO sources(name, base_url) VALUES ('t', '')")
        yield c
    finally:
        c.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        c.close()


def _add(conn, vectors, topic_ids, tag):
    for i, (v, t) in enumerate(zip(vectors, topic_ids)):
        aid = conn.execute(
            "INSERT INTO articles(source_id, url, canonical_url, title, published_at, body, content_hash, status) "
            "VALUES (1, %s, %s, %s, now(), 'b', %s, 'vectorized') RETURNING id",
            (f"{tag}{i}", f"{tag}{i}", f"{tag} {i}", f"{tag}{i}")).fetchone()[0]
        conn.execute("INSERT INTO article_nlp(article_id, lemmas, entities) VALUES (%s, %s, %s)",
                     (aid, TOPIC_WORDS[t], '{"TEAM": {"Joburg Super Kings": 1}}' if t == 0 else '{}'))
        conn.execute("INSERT INTO article_vectors(article_id, model, embedding) VALUES (%s, 'm', %s)", (aid, v))


@needs_db
def test_fit_assign_refit_keeps_topics_and_trends(conn):
    from src.cluster import run
    from src.cluster.trends import rising_topics
    quiet = lambda *_: None
    X, truth, centres = blobs(4, 6, seed=5)
    first3 = truth < 3
    _add(conn, X[first3], truth[first3], "a")                                # 3 topics x 6

    assert run.refit_reason(conn) == "no active model"
    out = run.fit(conn, echo=quiet)
    assert len(out["topics"]) == 3
    assert dict(conn.execute("SELECT status, count(*) FROM articles GROUP BY 1").fetchall()) == {"clustered": 18}
    labels = {d["label"] for d in out["topics"]}
    assert any("Joburg Super Kings" in l or "Auction" in l or "SA20" in l for l in labels)
    keys_before = {d["stable_key"] for d in out["topics"]}

    # one new article close to topic 0, one unrelated article
    near = model.normalise(centres[0][None] + 0.03 * np.random.default_rng(1).normal(size=(1, DIM)))
    odd = model.normalise(np.random.default_rng(2).normal(size=(1, DIM)))
    _add(conn, np.vstack([near, odd]).astype(np.float32), [0, 3], "b")
    res = run.assign(conn, echo=quiet)
    assert res == {"assigned": 1, "emerging": 1}
    assert run.refit_reason(conn) is None                                     # 1 emerging is not enough

    # a whole new story arrives: 6 articles of topic 3 -> no topic fits -> re-fit
    _add(conn, X[truth == 3], truth[truth == 3], "c")
    run.assign(conn, echo=quiet)
    assert "fit no topic" in run.refit_reason(conn)
    out2 = run.fit(conn, echo=quiet)
    assert len(out2["topics"]) == 4
    assert keys_before <= {d["stable_key"] for d in out2["topics"]}         # old topics kept their keys
    assert out2["params"]["carried_over_topics"] == 3
    assert conn.execute("SELECT count(*) FROM cluster_models WHERE is_active").fetchone()[0] == 1

    rising = rising_topics(conn, today=date.today())
    assert len(rising) == 4 and all(r["recent"] > 0 for r in rising)


@needs_db
def test_map_coordinates_are_stored_and_follow_deletions(conn):
    """The dashboard map reads stored coordinates; they must cover exactly the embedded articles."""
    from src.cluster import projection, run
    X, truth, _ = blobs(3, 6, seed=8)
    _add(conn, X, truth, "m")
    run.fit(conn, echo=lambda *_: None)                                       # fit stores the map
    counts = dict(conn.execute("SELECT method, count(*) FROM article_projection GROUP BY 1").fetchall())
    assert counts == {"umap": 18, "pca": 18} and not projection.is_stale(conn)
    xs = [r[0] for r in conn.execute("SELECT x FROM article_projection WHERE method = 'pca'")]
    assert min(xs) == 0 and max(xs) == 1                                      # scaled to 0..1

    conn.execute("DELETE FROM articles WHERE id = (SELECT min(id) FROM articles)")   # rolling cap removes one
    assert conn.execute("SELECT count(*) FROM article_projection").fetchone()[0] == 34   # its points went with it
    assert not projection.is_stale(conn)                                     # remaining points stay valid

    new = model.normalise(np.random.default_rng(3).normal(size=(1, DIM))).astype(np.float32)
    _add(conn, new, [0], "n")                                                # embedded, not yet on the map
    assert projection.is_stale(conn)
    assert projection.refresh(conn, echo=lambda *_: None) == 18 and not projection.is_stale(conn)


@needs_db
def test_dry_run_fit_writes_nothing(conn):
    from src.cluster import run
    X, truth, _ = blobs(3, 5, seed=6)
    _add(conn, X, truth, "d")
    assert len(run.fit(conn, dry_run=True, echo=lambda *_: None)["topics"]) == 3
    assert conn.execute("SELECT count(*) FROM cluster_models").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM articles WHERE status = 'vectorized'").fetchone()[0] == 15
