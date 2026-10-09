"""The active topic model, explained:  python -m src.cluster.report"""
import sys

from ..db import connect


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with connect() as conn:
        m = conn.execute("SELECT id, algorithm, params, created_at FROM cluster_models WHERE is_active").fetchone()
        if not m:
            print("No active model yet: run python -m src.cluster.run")
            return
        model_id, algorithm, params, created = m
        met, base = params["metrics"], params["baseline_kmeans"]
        print(f"Model {model_id}: {algorithm}, fitted {created:%Y-%m-%d %H:%M} on {params['fitted_on']} articles\n")
        print("Evaluation (same articles, same embeddings):")
        print(f"  {'':<22}{'topics':>7}{'unassigned':>12}{'silhouette':>12}{'Davies-B.':>11}{'NPMI':>8}")
        for name, x in ((algorithm + " (active)", met), (f"kmeans k={base['k']} (baseline)", base)):
            print(f"  {name:<22}{x['n_topics']:>7}{x['unassigned']:>12}{x.get('silhouette', '-'):>12}"
                  f"{x.get('davies_bouldin', '-'):>11}{x['coherence_npmi']:>8}")
        print("  silhouette: -1..1 higher is better | Davies-Bouldin: lower is better | "
              "NPMI coherence: -1..1 higher is better")
        print(f"  new articles join a topic at cosine >= {params['assign_threshold']}")

        topics = conn.execute("SELECT id, label, size, top_terms, stable_key FROM clusters "
                              "WHERE model_id = %s ORDER BY size DESC", (model_id,)).fetchall()
        for cid, label, size, top, key in topics:
            print(f"\n[{size}] {label}   (topic {key}, NPMI {top.get('coherence_npmi')})")
            print(f"    terms: {', '.join(top['terms'][:8])}")
            for elabel, names in top.get("entities", {}).items():
                print(f"    {elabel.lower():<12} {', '.join(names)}")
            for score, title, src in conn.execute(
                    "SELECT ac.score, a.title, s.name FROM article_clusters ac JOIN articles a ON a.id = ac.article_id "
                    "JOIN sources s ON s.id = a.source_id WHERE ac.cluster_id = %s ORDER BY ac.score DESC LIMIT 3",
                    (cid,)).fetchall():
                print(f"    {score:.2f}  {title[:80]}  ({src})")

        emerging = conn.execute(
            "SELECT a.title FROM articles a WHERE a.status = 'clustered' AND NOT EXISTS ("
            "SELECT 1 FROM article_clusters ac JOIN clusters c ON c.id = ac.cluster_id "
            "WHERE ac.article_id = a.id AND c.model_id = %s) ORDER BY a.id DESC", (model_id,)).fetchall()
        print(f"\nUnassigned / emerging ({len(emerging)}): one-off stories that fit no topic yet")
        for (title,) in emerging[:10]:
            print(f"    {title[:90]}")


if __name__ == "__main__":
    main()
