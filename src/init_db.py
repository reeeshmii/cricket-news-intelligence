"""Create or upgrade every table, view and function:  python -m src.init_db

Safe to run any time: db/schema.sql only uses CREATE ... IF NOT EXISTS / CREATE OR REPLACE,
so existing data (including what the crawler has stored) is never dropped.
"""
from pathlib import Path

from psycopg import sql

from .db import connect

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def apply_schema(conn, schema: str | None = None) -> None:
    """Run db/schema.sql. `schema` puts everything in another schema (used by the tests)."""
    if schema:
        conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        conn.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def summary(conn) -> list[tuple[str, int]]:
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE' ORDER BY 1").fetchall()
    return [(t, conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(t))).fetchone()[0])
            for (t,) in tables]


def main():
    with connect(autocommit=True, direct=True) as conn:
        apply_schema(conn)
        print("Schema is up to date.\n")
        for table, rows in summary(conn):
            print(f"  {table:<20} {rows:>6} rows")
        status = conn.execute("SELECT * FROM v_pipeline_status")
        cols = [c.name for c in status.description]
        print("\nPipeline status:")
        for col, val in zip(cols, status.fetchone()):
            print(f"  {col:<20} {val}")


if __name__ == "__main__":
    main()
