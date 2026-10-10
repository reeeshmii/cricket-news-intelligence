"""2-D map of the article embeddings for the Topic & Cluster Explorer.

Topics are found by HDBSCAN in the full 384-d space; this projection is only for looking at
them. UMAP (cosine) keeps nearby articles nearby, so the topics' groups stay visible. With very
few articles (or when asked) it uses PCA. Results are cached until the articles or the model change.
"""
import threading

import numpy as np

MIN_POINTS = 5
_cache: dict = {}
_lock = threading.Lock()


def _vec(v) -> np.ndarray:
    return np.asarray(v.to_numpy() if hasattr(v, "to_numpy") else v, dtype=np.float32)


def project(X: np.ndarray, method: str = "umap") -> tuple[np.ndarray, str]:
    n = len(X)
    if method == "umap" and n >= 15:
        import warnings
        warnings.filterwarnings("ignore", module="umap")
        import umap
        xy = umap.UMAP(n_components=2, n_neighbors=min(15, n - 1), min_dist=0.15, metric="cosine",
                       random_state=42).fit_transform(X)
        method = "umap"
    else:
        from sklearn.decomposition import PCA
        xy, method = PCA(n_components=2, random_state=42).fit_transform(X), "pca"
    lo, hi = xy.min(axis=0), xy.max(axis=0)
    return (xy - lo) / np.where(hi - lo == 0, 1, hi - lo), method        # scale to 0..1


def embedding_map(model_id: int, rows: list[dict], method: str = "umap") -> dict:
    key = (method, model_id, len(rows), rows[-1]["id"] if rows else 0,
           sum(r["cluster_id"] or 0 for r in rows))                     # changes when anything moves
    with _lock:
        if key in _cache:
            return _cache[key]
        if len(rows) < MIN_POINTS:
            result = {"method": None, "points": []}
        else:
            xy, used = project(np.vstack([_vec(r["embedding"]) for r in rows]), method)
            result = {"method": used, "points": [
                {"id": r["id"], "title": r["title"], "source": r["source"], "cluster_id": r["cluster_id"],
                 "x": round(float(x), 4), "y": round(float(y), 4)} for r, (x, y) in zip(rows, xy)]}
        if len(_cache) >= 4:                                             # a few recent maps (UMAP + PCA)
            _cache.pop(next(iter(_cache)))
        _cache[key] = result
        return result
