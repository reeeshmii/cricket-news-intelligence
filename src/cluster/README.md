# Cluster stage: topics and trends

Groups articles into topics, names them, keeps them up to date as news arrives, and measures
which topics are rising.

```
article_vectors (384-d) ─► HDBSCAN (+ UMAP above 300 articles) ─► topics, one-off stories left unassigned
article_nlp.lemmas      ─► c-TF-IDF ─► top terms ─► label "SA20 · Auction · Joburg Super Kings"
                                                └► NPMI coherence (evaluation)
KMeans (k by silhouette) runs on the same data as a baseline for comparison.
```

## Why HDBSCAN (and the evidence)

Measured on the first 30 real articles:

| method | topics | unassigned | silhouette ↑ | NPMI coherence ↑ |
|---|---|---|---|---|
| **HDBSCAN** (active) | 7 | 10 | **0.45** | **0.42** |
| KMeans, best k by silhouette | 10 | 0 | 0.26 | 0.36 |
| UMAP + HDBSCAN | 2 | 0 | 0.26 | – |

- **KMeans** must put every article in some topic and needs k in advance. Its silhouette is
  nearly flat for k = 2…8 on news, so it cannot tell how many topics there are.
- **HDBSCAN** finds the number of topics itself and leaves one-off stories unassigned
  ("emerging"), which suits news: plenty of articles are about nothing else in the corpus.
- **UMAP** first squeezes the 384-d embeddings to 5-d. That keeps density-based clustering
  working on large corpora, but on a few dozen articles it merges everything into 2 blobs, so
  it only switches on above 300 articles (`CLUSTER_UMAP=auto|on|off`).
  `tests/cluster` checks both paths on data with known topics.

The report shows this comparison for every fitted model (`python -m src.cluster.report`).

## Interpreting a topic

| field | where | how |
|---|---|---|
| top terms | `clusters.top_terms.terms` | **c-TF-IDF** (as in BERTopic): all articles of a topic form one document; a term scores high when frequent in this topic and rare in the others |
| label | `clusters.label` | top 3 terms, mapped back to real names (`joburg_super_kings` → "Joburg Super Kings") |
| entities | `clusters.top_terms.entities` | most-mentioned people, teams, tournaments and boards in the topic |
| coherence | `clusters.top_terms.coherence_npmi` | NPMI of the top terms' co-occurrence in articles (−1 … +1) |
| representative articles | `article_clusters.score` | cosine similarity to the topic centroid; highest = most typical |

## Keeping topics current (the dynamic part)

`python -m src.cluster.run` (auto mode) does this every time:

1. **Assign.** Each new `vectorized` article joins its nearest topic if it is at least as close
   as the 10th percentile of that model's members (stored as `assign_threshold`, never below
   0.30). Otherwise it stays unassigned (**emerging**).
2. **Re-fit if needed.** The topic model is rebuilt on the last 90 days when:
   - there is no model;
   - the model is more than 7 days old;
   - at least 5 new articles fit no topic and they are ≥ 20% of the fitted corpus (a new story has appeared);
   - or the corpus has grown 1.5× since the fit.
3. **Stable topics.** On re-fit, each new topic is matched to an old one by centroid similarity
   (≥ 0.75) and inherits its `stable_key`. "SA20 auction" stays the same topic across models,
   and its trend line continues.
4. **Dashboard map.** The 2-D UMAP and PCA coordinates of every embedded article are stored in
   `article_projection` (`projection.py`), so the deployed API only reads numbers.
5. **Trend history.** `refresh_topic_daily_stats()` copies per-day counts into
   `topic_daily_stats`, which survives the crawler's rolling cap.

Older models keep their topics and trend rows. Their per-article rows are pruned after 3 models.

## Trends

`python -m src.cluster.trends` ranks topics by momentum: articles in the last 3 days against
their average rate over the 14 days before (`growth = (recent + 1) / (expected + 1)`). Topics
with no earlier articles are flagged **NEW**. It also prints a 14-day daily table per topic.
`rising_topics()` and `topic_series()` are the functions the API/dashboard will call.

## Commands

| what | command |
|---|---|
| assign new articles, re-fit when needed | `python -m src.cluster.run` |
| force a re-fit | `python -m src.cluster.run --fit` |
| baseline instead of HDBSCAN | `python -m src.cluster.run --fit --algorithm kmeans` |
| preview, write nothing | `python -m src.cluster.run --fit --dry-run` |
| keep running | `python -m src.cluster.run --every 30` |
| explain the active model | `python -m src.cluster.report` |
| rising / new topics | `python -m src.cluster.trends` |
| tests | `python -m pytest tests/cluster -q` |

GitHub Actions ([`.github/workflows/cluster.yml`](../../.github/workflows/cluster.yml)) runs it after
every NLP run, from `main`. The full chain is: crawler (every 3 h) → nlp → cluster.

## Limitations

- With only a few dozen articles, topics are small (2–6 articles) and a third of articles are
  unassigned. Both improve as the crawler accumulates articles.
- Labels come from word statistics; a human can still edit `clusters.label`. A re-fit writes
  new labels, but `stable_key` stays.
- Momentum needs a few weeks of history before "rising" becomes meaningful.
