"""Connection pool for the API.

Uses Neon's pooled endpoint (many short queries, no session-level SET). Tests set
API_DB_SCHEMA to point every connection at a throwaway schema; that goes through the
direct endpoint with a startup option, so nothing leaks to other clients.
"""
import os
from contextlib import contextmanager

from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .. import config
from ..db import direct_dsn

_pool: ConnectionPool | None = None


def _configure(conn) -> None:
    try:
        register_vector(conn)              # embeddings for the 2-D map
    except Exception:                      # extension missing: everything else still works
        pass


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if not config.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set (see .env.example)")
        dsn = config.DATABASE_URL
        kwargs = {"autocommit": True, "row_factory": dict_row, "connect_timeout": 20}
        if schema := os.environ.get("API_DB_SCHEMA"):
            dsn = direct_dsn(dsn)
            kwargs["options"] = f"-c search_path={schema},public"
        _pool = ConnectionPool(dsn, min_size=1, max_size=6, kwargs=kwargs, configure=_configure,
                               check=ConnectionPool.check_connection,   # Neon may drop idle connections
                               timeout=30, open=True)
    return _pool


@contextmanager
def connection():
    with pool().connection() as conn:
        yield conn


def close() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
