"""Cluster-stage settings."""
import os

from .. import config

WINDOW_DAYS = config.REFIT_WINDOW_DAYS     # articles older than this are left out of a re-fit
MIN_ARTICLES = 10                          # below this there is nothing meaningful to cluster
TOP_TERMS = 10                             # c-TF-IDF terms kept per topic (and used for NPMI)

# HDBSCAN works on raw cosine distances for small corpora. Above UMAP_MIN_ARTICLES it first
# reduces the 384-d embeddings to 5-d with UMAP, which keeps density-based clustering reliable
# as the corpus grows (the BERTopic recipe). "auto" | "on" | "off".
UMAP = os.environ.get("CLUSTER_UMAP", "auto")
UMAP_MIN_ARTICLES = 300
KMEANS_MAX_K = 30                          # baseline searches k = 2 .. min(KMEANS_MAX_K, n / 3)

# New articles join the nearest topic if they are at least as close to its centroid as the
# ASSIGN_PERCENTILE-th percentile of that model's members (never below ASSIGN_FLOOR).
ASSIGN_PERCENTILE = 10
ASSIGN_FLOOR = 0.30

# A re-fit keeps a topic's stable_key when its new centroid is this similar to an old one.
MATCH_MIN_SIMILARITY = 0.75

# Automatic re-fit triggers (checked after each assignment pass).
REFIT_MAX_AGE_DAYS = 7                     # model older than a week
EMERGING_MIN = 5                           # at least this many new articles fit no topic...
EMERGING_SHARE = 0.20                      # ...and they are >= 20% of the articles the model was fitted on
GROWTH_FACTOR = 1.5                        # or the corpus grew 1.5x since the fit

KEEP_ASSIGNMENTS_FOR_MODELS = 3            # older models keep their topics/trend rows, not per-article rows
CLUSTER_LOCK_KEY = 7_202_028               # pg advisory lock (crawler ...026, nlp ...027)
