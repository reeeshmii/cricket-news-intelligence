"""2-D coordinates of every article embedding, for the dashboard's cluster map.

Computed by the cluster stage (GitHub Actions or locally) and stored in article_projection,
so the deployed API only reads numbers: it needs no numpy / scikit-learn / UMAP and answers
instantly on a serverless host. Refreshed after every fit and assignment, and whenever
articles were added or removed (the crawler's rolling cap deletes rows by cascade).

Topics are found by HDBSCAN in the full 384-d space; this projection is only for viewing.
"""
import numpy as np

from . import model

METHODS = ("umap", "pca")
MIN_POINTS = 5
UMAP_MIN_POINTS = 15          # below this UMAP is unreliable; the "umap" view falls back to PCA


def project(X: np.ndarray, method: str) -> np.ndarray:
    """Rows of X (unit vectors) -> 2-D points scaled to 0..1."""
    n = len(X)
    if method == "umap" and n >= UMAP_MIN_POINTS:
        import warnings
        warnings.filterwarnings("ignore", module="umap")
        import umap                                        # lazy: slow (numba) import
        xy = umap.UMAP(n_components=2, n_neighbors=min(15, n - 1), min_dist=0.15, metric="cosine",
                       random_state=42).fit_transform(X)
    else:
        from sklearn.decomposition import PCA
        xy = PCA(n_components=2, random_state=42).fit_transform(X)
    lo, hi = xy.min(axis=0), xy.max(axis=0)
    return (xy - lo) / np.where(hi - lo == 0, 1, hi - lo)


def is_stale(conn) -> bool:
    """True when the stored map no longer covers exactly the articles that have embeddings."""
    vectors, projected, max_v, max_p = conn.execute("""
        SELECT (SELECT count(*) FROM article_vectors v JOIN articles a ON a.id = v.article_id
                 WHERE a.duplicate_of IS NULL),
               (SELECT count(*) FROM article_projection WHERE method = 'umap'),
               (SELECT coalesce(max(v.article_id), 0) FROM article_vectors v JOIN articles a ON a.id = v.article_id
                 WHERE a.duplicate_of IS NULL),
               (SELECT coalesce(max(article_id), 0) FROM article_projection WHERE method = 'umap')
    """).fetchone()
    if vectors < MIN_POINTS:
        return projected != 0
    return vectors != projected or max_v != max_p


def refresh(conn, echo=print) -> int:
    """Recompute and store the 2-D map for all articles with embeddings. Returns points stored."""
    rows = conn.execute("""
        SELECT a.id, v.embedding FROM articles a JOIN article_vectors v ON v.article_id = a.id
        WHERE a.duplicate_of IS NULL ORDER BY a.id""").fetchall()
    values = []
    if len(rows) >= MIN_POINTS:
        X = model.normalise(np.vstack([model.as_array(r[1]) for r in rows]))
        for method in METHODS:
            xy = project(X, method)
            values += [(aid, method, float(x), float(y)) for (aid, _), (x, y) in zip(rows, xy)]
    with conn.transaction():
        conn.execute("DELETE FROM article_projection")
        if values:
            with conn.cursor() as cur:
                cur.executemany("INSERT INTO article_projection(article_id, method, x, y) VALUES (%s, %s, %s, %s)", values)
    echo(f"map: stored 2-D coordinates for {len(values) // len(METHODS) if values else 0} articles")
    return len(values) // len(METHODS) if values else 0
