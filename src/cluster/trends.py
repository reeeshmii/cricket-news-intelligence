"""Trend analysis over topic_daily_stats (history that survives the crawler's rolling cap).

A topic is identified by its stable_key, so its series continues across model re-fits.
When several models wrote a row for the same day and topic, the newest model's row wins.

  python -m src.cluster.trends              # rising / new topics + last 14 days per topic
"""
import sys
from collections import defaultdict
from datetime import date, timedelta

from ..db import connect

SERIES = """
WITH ranked AS (
    SELECT s.day, c.stable_key, s.article_count, s.avg_sentiment,
           row_number() OVER (PARTITION BY s.day, c.stable_key ORDER BY s.model_id DESC) AS rn
    FROM topic_daily_stats s JOIN clusters c ON c.id = s.cluster_id
    WHERE s.day >= %s AND c.stable_key IS NOT NULL
)
SELECT day, stable_key, article_count, avg_sentiment FROM ranked WHERE rn = 1 ORDER BY day
"""

# Latest label for each stable_key (the active model's, if the topic still exists).
LABELS = """
SELECT DISTINCT ON (c.stable_key) c.stable_key, c.label, m.is_active
FROM clusters c JOIN cluster_models m ON m.id = c.model_id
WHERE c.stable_key IS NOT NULL
ORDER BY c.stable_key, m.is_active DESC, m.id DESC
"""


def topic_series(conn, days: int = 30, today: date | None = None) -> dict[str, dict]:
    """{stable_key: {"label", "active", "days": {date: (count, avg_sentiment)}}}"""
    today = today or date.today()
    labels = {k: (label, active) for k, label, active in conn.execute(LABELS).fetchall()}
    out: dict[str, dict] = {}
    for day, key, count, sentiment in conn.execute(SERIES, (today - timedelta(days=days),)).fetchall():
        label, active = labels.get(key, (key, False))
        out.setdefault(key, {"label": label, "active": active, "days": {}})["days"][day] = (count, sentiment)
    return out


def rising_topics(conn, recent_days: int = 3, baseline_days: int = 14, today: date | None = None) -> list[dict]:
    """Compare each topic's articles in the last `recent_days` with its average rate over the
    `baseline_days` before that. growth = (recent + 1) / (expected + 1), so a topic going from
    0 to 4 articles scores 5.0 and a steady topic scores about 1. Topics with no earlier
    articles are flagged as new."""
    today = today or date.today()
    recent_start = today - timedelta(days=recent_days - 1)
    base_start = recent_start - timedelta(days=baseline_days)
    out = []
    for key, s in topic_series(conn, recent_days + baseline_days, today).items():
        recent = sum(c for d, (c, _) in s["days"].items() if d >= recent_start)
        before = sum(c for d, (c, _) in s["days"].items() if base_start <= d < recent_start)
        expected = before / baseline_days * recent_days
        sentiments = [sent for d, (_, sent) in s["days"].items() if d >= recent_start and sent is not None]
        out.append({"stable_key": key, "label": s["label"], "active": s["active"], "recent": recent,
                    "expected": round(expected, 2), "growth": round((recent + 1) / (expected + 1), 2),
                    "new": before == 0 and recent > 0,
                    "recent_sentiment": round(sum(sentiments) / len(sentiments), 3) if sentiments else None})
    return sorted(out, key=lambda r: (-r["growth"], -r["recent"]))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with connect() as conn:
        rising = rising_topics(conn)
        if not rising:
            print("No trend data yet: run python -m src.cluster.run first.")
            return
        print("Topics by momentum (last 3 days vs the 14 days before):")
        for r in rising:
            flag = "NEW " if r["new"] else "    "
            print(f"  {flag}x{r['growth']:<5} {r['recent']:>3} recent (expected {r['expected']:>4})  {r['label']}")
        series = topic_series(conn, 14)
        days = [date.today() - timedelta(days=i) for i in range(13, -1, -1)]
        print("\nDaily articles, last 14 days (oldest -> today):")
        for key, s in sorted(series.items(), key=lambda kv: -sum(c for c, _ in kv[1]["days"].values())):
            row = " ".join(f"{s['days'].get(d, (0, None))[0]:>2}" for d in days)
            print(f"  {row}  {s['label'][:60]}")


if __name__ == "__main__":
    main()
