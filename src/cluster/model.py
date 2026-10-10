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


def as_array(v) -> np.ndarray:
    """pgvector returns Vector objects (or arrays, depending on the version)."""
    return np.asarray(v.to_numpy() if hasattr(v, "to_numpy") else v, dtype=np.float32)


def normalise(X: np.ndarray) -> np.ndarray:
    return X / np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)


def min_cluster_size(n: int) -> int:
    """2 for a few dozen articles, growing slowly to 10 for thousands."""
    return int(np.clip(round(np.sqrt(n) / 3), 2, 10))


def _use_umap(n: int) -> bool:
    return settings.UMAP == "on" or (settings.UMAP == "auto" and n >= settings.UMAP_MIN_ARTICLES)


def _largest_share(labels: np.ndarray) -> float:
    assigned = labels[labels >= 0]
    return float(np.bincount(assigned).max() / len(assigned)) if len(assigned) else 1.0


def hdbscan_fit(X: np.ndarray) -> TopicFit:
    """HDBSCAN with a guard against topic collapse.

    HDBSCAN's min_samples defaults to min_cluster_size; from 3 upwards its "excess of mass"
    selection can merge sibling topics into one blob (seen live: 58 articles -> topics of
    43 + 7). So min_samples=1, and a few candidate settings are tried: any result where one
    topic holds more than MAX_TOPIC_SHARE of the assigned articles is rejected, and the rest
    are ranked by silhouette x sqrt(coverage). Every candidate's scores are kept in params."""
    n, mcs = len(X), min_cluster_size(len(X))
    params = {"metric": "cosine", "umap": None, "min_samples": 1}
    Z = X
    if _use_umap(n):
        import umap                                       # imported lazily: slow (numba) import
        umap_params = {"n_neighbors": min(15, n - 1), "n_components": 5, "min_dist": 0.0,
                       "metric": "cosine", "random_state": 42}
        Z = umap.UMAP(**umap_params).fit_transform(X)
        params.update(umap=umap_params, metric="euclidean (UMAP space)")
    metric = "euclidean" if params["umap"] else "cosine"

    candidates = []
    for method, size in (("eom", mcs), ("leaf", mcs), ("eom", max(2, mcs - 1))):
        labels = HDBSCAN(min_cluster_size=size, min_samples=1, metric=metric,
                         cluster_selection_method=method).fit_predict(Z)
        m = labels >= 0
        k = len(set(labels[m].tolist()))
        sil = float(silhouette_score(X[m], labels[m], metric="cosine")) if k >= 2 and m.sum() > k else -1.0
        share = _largest_share(labels)
        candidates.append({"method": method, "min_cluster_size": size, "topics": k,
                           "coverage": round(float(m.mean()), 3), "largest_share": round(share, 3),
                           "silhouette": round(sil, 4), "score": round(sil * float(np.sqrt(m.mean())), 4),
                           "valid": k >= 2 and share <= settings.MAX_TOPIC_SHARE, "labels": labels})
    valid = [c for c in candidates if c["valid"]] or candidates
    best = max(valid, key=lambda c: c["score"])
    params.update(min_cluster_size=best["min_cluster_size"], cluster_selection_method=best["method"],
                  candidates=[{k: v for k, v in c.items() if k != "labels"} for c in candidates])
    return TopicFit("hdbscan", best["labels"], params)


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
