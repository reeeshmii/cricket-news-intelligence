"""What the NLP stage found:  python -m src.nlp.report"""
import sys

from ..db import connect

TOP_ENTITIES = """
SELECT e.key AS name, sum(e.value::int) AS mentions, count(*) AS articles
FROM article_nlp n, jsonb_each_text(n.entities -> %s) AS e
GROUP BY e.key ORDER BY articles DESC, mentions DESC LIMIT %s
"""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with connect() as conn:
        status = dict(conn.execute("SELECT status, count(*) FROM articles GROUP BY status").fetchall())
        vectors = conn.execute("SELECT count(*), min(model) FROM article_vectors").fetchone()
        print("Articles by status:", ", ".join(f"{k}={v}" for k, v in sorted(status.items())))
        print(f"Embeddings: {vectors[0]} ({vectors[1] or '-'})")

        for label in ("PERSON", "TEAM", "TOURNAMENT", "CRICKET_ORG", "VENUE"):
            rows = conn.execute(TOP_ENTITIES, (label, 8)).fetchall()
            if rows:
                print(f"\nTop {label} (articles / mentions):")
                for name, mentions, arts in rows:
                    print(f"  {arts:>3} / {mentions:<4} {name}")

        print("\nSentiment by source (mean, -1 .. +1):")
        for src, avg, n in conn.execute(
                "SELECT s.name, avg(n.sentiment), count(*) FROM article_nlp n JOIN articles a ON a.id = n.article_id "
                "JOIN sources s ON s.id = a.source_id GROUP BY 1 ORDER BY 2 DESC").fetchall():
            print(f"  {src:<16} {avg:+.3f}  ({n} articles)")

        for title, order in (("Most positive", "DESC"), ("Most negative", "ASC")):
            print(f"\n{title}:")
            for s, t in conn.execute(f"SELECT n.sentiment, a.title FROM article_nlp n JOIN articles a "
                                     f"ON a.id = n.article_id ORDER BY n.sentiment {order} LIMIT 3").fetchall():
                print(f"  {s:+.3f}  {t[:90]}")

        print("\nMost common keywords:")
        rows = conn.execute("SELECT k, count(*) FROM article_nlp n, jsonb_array_elements_text(n.keywords) k "
                            "GROUP BY k ORDER BY 2 DESC, 1 LIMIT 12").fetchall()
        print("  " + ", ".join(f"{k} ({c})" for k, c in rows))


if __name__ == "__main__":
    main()
