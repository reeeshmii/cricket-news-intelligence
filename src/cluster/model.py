"""Topic discovery on article embeddings.

Primary: HDBSCAN (density-based). It finds the number of topics itself and leaves one-off
stories unassigned (label -1) instead of forcing them into a topic. Embeddings are first
reduced with UMAP once the corpus is large enough (settings.UMAP_MIN_ARTICLES).
Baseline: KMeans with k chosen by silhouette, kept for comparison in the evaluation.
"""
from dataclasses import dataclass, field

import numpy as np
from sklearn.cluster import HDBSCAN, KMeans
from sklearn.metrics import davies_bouldin_score, silhouette_score

from . import settings


@dataclass
class TopicFit:
    algorithm: str
    labels: np.ndarray                     # topic index per article, -1 = unassigned
    params: dict = field(default_factory=dict)


def normalise(X: np.ndarray) -> np.ndarray:
    return X / np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)


def min_cluster_size(n: int) -> int:
    """2 for a few dozen articles, growing slowly to 10 for thousands."""
    return int(np.clip(round(np.sqrt(n) / 3), 2, 10))


def _use_umap(n: int) -> bool:
    return settings.UMAP == "on" or (settings.UMAP == "auto" and n >= settings.UMAP_MIN_ARTICLES)


def hdbscan_fit(X: np.ndarray) -> TopicFit:
    n, mcs = len(X), min_cluster_size(len(X))
    params = {"min_cluster_size": mcs, "metric": "cosine", "umap": None}
    if _use_umap(n):
        import umap                                       # imported lazily: slow (numba) import
        umap_params = {"n_neighbors": min(15, n - 1), "n_components": 5, "min_dist": 0.0,
                       "metric": "cosine", "random_state": 42}
        Z = umap.UMAP(**umap_params).fit_transform(X)
        labels = HDBSCAN(min_cluster_size=mcs).fit_predict(Z)
        params.update(umap=umap_params, metric="euclidean (UMAP space)")
    else:
        labels = HDBSCAN(min_cluster_size=mcs, metric="cosine").fit_predict(X)
    return TopicFit("hdbscan", labels, params)


def kmeans_fit(X: np.ndarray, k: int | None = None) -> TopicFit:
    n = len(X)
    ks = [k] if k else list(range(2, max(2, min(settings.KMEANS_MAX_K, n // 3)) + 1))
    best, by_k = None, {}
    for kk in ks:
        if kk >= n:
            break
        labels = KMeans(n_clusters=kk, n_init=10, random_state=42).fit_predict(X)
        s = float(silhouette_score(X, labels, metric="cosine"))
        by_k[kk] = round(s, 4)
        if best is None or s > best[0]:
            best = (s, kk, labels)
    return TopicFit("kmeans", best[2], {"k": best[1], "silhouette_by_k": by_k})


def centroids(X: np.ndarray, labels: np.ndarray) -> dict[int, np.ndarray]:
    return {t: normalise(X[labels == t].mean(axis=0, keepdims=True))[0]
            for t in sorted(set(labels.tolist()) - {-1})}


def geometry_metrics(X: np.ndarray, labels: np.ndarray) -> dict:
    """Silhouette (cosine, -1..1, higher = tighter, better separated topics) and
    Davies-Bouldin (lower = better), both on assigned articles only."""
    m = labels >= 0
    k = len(set(labels[m].tolist()))
    out = {"n_articles": int(len(X)), "n_topics": k, "unassigned": int((~m).sum()),
           "coverage": round(float(m.mean()), 3)}
    if k >= 2 and m.sum() > k:
        out["silhouette"] = round(float(silhouette_score(X[m], labels[m], metric="cosine")), 4)
        out["davies_bouldin"] = round(float(davies_bouldin_score(X[m], labels[m])), 4)
    return out


def assign_threshold(X: np.ndarray, labels: np.ndarray) -> float:
    """How close a NEW article must be to a topic centroid to join it.

    Uses leave-one-out similarities: each member against the centroid of the OTHER members,
    which is exactly the position a new article is in. (A member's similarity to a centroid it
    helped build is inflated, badly so for 2-3 article topics.)"""
    sims = []
    for t in set(labels.tolist()) - {-1}:
        members = X[labels == t]
        if len(members) < 2:
            continue
        total = members.sum(axis=0)
        for x in members:
            sims.append(float(x @ normalise((total - x)[None, :])[0]))
    if not sims:
        return settings.ASSIGN_FLOOR
    return round(max(settings.ASSIGN_FLOOR, float(np.percentile(sims, settings.ASSIGN_PERCENTILE))), 4)


def match_stable_keys(previous: list[tuple[str, np.ndarray]], new: dict[int, np.ndarray],
                      new_key) -> dict[int, str]:
    """Greedy best-first matching of new topic centroids to the previous model's topics,
    so a topic keeps its identity (and trend history) across re-fits."""
    keys, used = {}, set()
    pairs = sorted(((float(c @ old_c), t, key) for t, c in new.items() for key, old_c in previous),
                   reverse=True)
    for sim, t, key in pairs:
        if sim < settings.MATCH_MIN_SIMILARITY:
            break
        if t not in keys and key not in used:
            keys[t] = key
            used.add(key)
    for t in new:
        keys.setdefault(t, new_key())
    return keys
