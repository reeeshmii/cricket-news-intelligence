"""Shared Neon connection helper for the pipeline stages (NLP, clustering, API).

    from src.db import connect
    with connect() as conn:
        rows = conn.execute("SELECT id, body FROM articles WHERE status = 'cleaned'").fetchall()

The crawler keeps its own connection logic (src/crawler/neon_store.py) and needs none of this.
"""
from urllib.parse import urlsplit, urlunsplit

import psycopg
from pgvector.psycopg import register_vector

from . import config


def direct_dsn(dsn: str) -> str:
    """Neon pooled host (ep-x-pooler.region...) -> direct host (ep-x.region...).

    Use the direct endpoint for long sessions, schema changes and anything that runs SET:
    the pooler (PgBouncer, transaction mode) leaks session settings to other clients."""
    parts = urlsplit(dsn)
    if parts.hostname and "-pooler." in parts.hostname:
        return urlunsplit(parts._replace(netloc=parts.netloc.replace("-pooler.", ".", 1)))
    return dsn


def connect(autocommit: bool = False, direct: bool = False, dsn: str | None = None) -> psycopg.Connection:
    """Open a connection with the pgvector type registered, so embeddings can be passed as
    Python lists / arrays and read back as vectors.

    direct=True uses Neon's direct endpoint (long jobs, migrations); the default pooled
    endpoint suits short queries such as API requests."""
    dsn = dsn or config.DATABASE_URL
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set. Put your Neon connection string in .env "
                           "(see .env.example).")
    conn = psycopg.connect(direct_dsn(dsn) if direct else dsn, autocommit=autocommit, connect_timeout=20)
    try:
        register_vector(conn)
    except psycopg.ProgrammingError:      # vector extension not created yet: run python -m src.init_db
        if not autocommit:
            conn.rollback()
    return conn
