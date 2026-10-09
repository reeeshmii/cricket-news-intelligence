"""NLP stage runner.

  python -m src.nlp.run                       # process everything waiting, then exit
  python -m src.nlp.run --every 15            # keep running: check for new articles every 15 min
  python -m src.nlp.run --dry-run --limit 3   # print results, write nothing
  python -m src.nlp.run --stage nlp           # only entities/lemmas/sentiment/keywords
  python -m src.nlp.run --stage embed         # only embeddings
  python -m src.nlp.run --reprocess           # re-analyse processed articles after changing NLP code

Status flow in `articles`:  cleaned --(nlp)--> nlp_done --(embed)--> vectorized
Each article is written in its own small transaction, so a crash loses at most one article,
and only rows still in the input status are touched: re-running never redoes work.
"""
import argparse
import json
import sys
import time
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from ..db import connect
from . import settings

STAGES = {"nlp": ("cleaned", "nlp_done"), "embed": ("nlp_done", "vectorized")}


class NLPBusy(Exception):
    pass


def pending(conn) -> dict[str, int]:
    rows = conn.execute("SELECT status, count(*) FROM articles WHERE duplicate_of IS NULL "
                        "GROUP BY status").fetchall()
    return {s: n for s, n in rows}


def _batches(conn, status: str | list[str], batch: int, limit: int | None):
    """Yield [(id, title, body)] in id order. A cursor on id (not OFFSET) means an article that
    keeps failing is skipped for this run instead of being retried forever."""
    last_id, done = 0, 0
    while limit is None or done < limit:
        size = batch if limit is None else min(batch, limit - done)
        rows = conn.execute(
            "SELECT id, title, body FROM articles WHERE status = ANY(%s) AND duplicate_of IS NULL "
            "AND id > %s ORDER BY id LIMIT %s",
            ([status] if isinstance(status, str) else status, last_id, size)).fetchall()
        if not rows:
            return
        yield rows
        last_id, done = rows[-1][0], done + len(rows)


def _write(conn, article_id: int, insert_sql: str, params: tuple, stage: str) -> bool:
    """Insert results + advance status atomically. False if the article vanished meanwhile
    (the crawler's rolling cap can delete it while we work)."""
    src, dst = STAGES[stage]
    try:
        with conn.transaction():
            cur = conn.execute(insert_sql, params)
            if cur.rowcount == 0:
                return False
            conn.execute("UPDATE articles SET status = %s WHERE id = %s AND status = %s",
                         (dst, article_id, src))
        return True
    except psycopg.errors.ForeignKeyViolation:
        return False


PRIOR_VOTES = """
SELECT e.name, l.label, count(*) FROM article_nlp n, jsonb_each(n.entities) AS l(label, names),
       jsonb_object_keys(l.names) AS e(name)
WHERE l.label = ANY(%s) GROUP BY 1, 2
"""


def prior_votes(conn) -> dict:
    """Label votes from every article processed so far (one vote per article)."""
    from collections import Counter, defaultdict
    from .analyze import VOTING_LABELS
    votes = defaultdict(Counter)
    for name, label, n in conn.execute(PRIOR_VOTES, (sorted(VOTING_LABELS),)).fetchall():
        votes[name][label] += n
    return votes


def run_nlp(conn, analyzer, batch=settings.BATCH_SIZE, limit=None, dry_run=False, echo=print,
            reprocess=False) -> int:
    """reprocess=True re-analyses articles that were already processed (after improving the NLP
    code); it rewrites article_nlp but leaves their pipeline status alone."""
    from .analyze import harmonise, label_votes
    done = 0
    votes = prior_votes(conn)
    statuses = ["nlp_done", "vectorized", "clustered"] if reprocess else "cleaned"
    for rows in _batches(conn, statuses, batch, limit):
        results = analyzer.analyze([(title, body) for _, title, body in rows])
        for name, c in label_votes(r["entities"] for r in results).items():
            votes[name].update(c)                     # this batch votes too
        for r in results:
            r["entities"] = harmonise(r["entities"], votes)
        for (aid, title, _), r in zip(rows, results):
            if dry_run:
                echo(json.dumps({"id": aid, "title": title, **r, "lemmas": r["lemmas"][:200] + "..."},
                                indent=2, ensure_ascii=False))
                continue
            ok = _write(conn, aid,
                        """INSERT INTO article_nlp(article_id, lemmas, sentiment, entities, keywords)
                           SELECT %s, %s, %s, %s, %s WHERE EXISTS (SELECT 1 FROM articles WHERE id = %s)
                           ON CONFLICT (article_id) DO UPDATE SET lemmas = EXCLUDED.lemmas,
                             sentiment = EXCLUDED.sentiment, entities = EXCLUDED.entities,
                             keywords = EXCLUDED.keywords, processed_at = now()""",
                        (aid, r["lemmas"], r["sentiment"], Jsonb(r["entities"]), Jsonb(r["keywords"]), aid),
                        "nlp")
            done += ok
        echo(f"  nlp: {done} articles processed")
    return done


def run_embed(conn, embedder, batch=settings.BATCH_SIZE, limit=None, dry_run=False, echo=print,
              status="nlp_done") -> int:
    done = 0
    for rows in _batches(conn, status, batch, limit):
        vectors = embedder.encode([(title, body) for _, title, body in rows])
        for (aid, title, _), vec in zip(rows, vectors):
            if dry_run:
                echo(f"  [{aid}] {title[:70]} -> {len(vec)}-d, |v| = {float((vec ** 2).sum()) ** 0.5:.3f}")
                continue
            ok = _write(conn, aid,
                        """INSERT INTO article_vectors(article_id, model, embedding)
                           SELECT %s, %s, %s WHERE EXISTS (SELECT 1 FROM articles WHERE id = %s)
                           ON CONFLICT (article_id) DO UPDATE SET model = EXCLUDED.model,
                             embedding = EXCLUDED.embedding, created_at = now()""",
                        (aid, embedder.name, vec, aid), "embed")
            done += ok
        echo(f"  embed: {done} articles embedded")
    return done


def run_once(stage="all", limit=None, dry_run=False, echo=print, models=None, reprocess=False) -> dict:
    """One pass over everything waiting. `models` caches the loaded models across loop cycles."""
    models = models if models is not None else {}
    with connect(autocommit=True, direct=True) as conn:
        if not dry_run and not conn.execute("SELECT pg_try_advisory_lock(%s)",
                                            (settings.NLP_LOCK_KEY,)).fetchone()[0]:
            raise NLPBusy("another NLP run is in progress")
        waiting = pending(conn)
        echo(f"waiting: nlp={waiting.get('cleaned', 0)}, embed={waiting.get('nlp_done', 0)}")
        result = {"nlp": 0, "embed": 0}
        if reprocess:
            if "analyzer" not in models:
                from .analyze import Analyzer
                models["analyzer"] = Analyzer()
            result["nlp"] = run_nlp(conn, models["analyzer"], limit=limit, dry_run=dry_run, echo=echo,
                                    reprocess=True)
            return result
        if stage in ("all", "nlp") and waiting.get("cleaned"):
            if "analyzer" not in models:                 # load spaCy only when there is work
                from .analyze import Analyzer
                models["analyzer"] = Analyzer()
            result["nlp"] = run_nlp(conn, models["analyzer"], limit=limit, dry_run=dry_run, echo=echo)
        # a dry run never advances statuses, so it previews embeddings for the same waiting articles
        embed_from = "cleaned" if dry_run and not waiting.get("nlp_done") else "nlp_done"
        if stage in ("all", "embed") and pending(conn).get(embed_from):
            if "embedder" not in models:                 # load the transformer only when needed
                from .embed import Embedder
                models["embedder"] = Embedder()
            result["embed"] = run_embed(conn, models["embedder"], limit=limit, dry_run=dry_run,
                                        echo=echo, status=embed_from)
        return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["all", "nlp", "embed"], default="all")
    ap.add_argument("--limit", type=int, help="max articles per stage (default: all waiting)")
    ap.add_argument("--dry-run", action="store_true", help="print results, write nothing")
    ap.add_argument("--every", type=float, help="keep running, checking every N minutes")
    ap.add_argument("--reprocess", action="store_true",
                    help="re-analyse already-processed articles (after changing the NLP code)")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    models: dict = {}
    try:
        _loop(a, models)
    except KeyboardInterrupt:
        print("stopped")


def _loop(a, models: dict) -> None:
    while True:
        try:
            r = run_once(a.stage, a.limit, a.dry_run, models=models, reprocess=a.reprocess)
            print(f"{datetime.now():%H:%M:%S} done: nlp={r['nlp']}, embed={r['embed']}")
        except NLPBusy as e:
            print(f"Skipped: {e}")
        except Exception as e:                      # keep the loop alive; one-shot runs still fail
            if not a.every:
                raise
            print(f"run failed: {type(e).__name__}: {e}")
        if not a.every:
            return
        time.sleep(a.every * 60)


if __name__ == "__main__":
    main()
