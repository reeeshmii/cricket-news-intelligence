"""Database connections for the API.

Locally (python -m src.api): a small connection pool, so requests reuse connections.
On Vercel (serverless, env VERCEL is set): one short connection per request through Neon's
pooled endpoint, because function instances start, freeze and stop at any time.

Tests set API_DB_SCHEMA to point every connection at a throwaway schema; that goes through the
direct endpoint with a startup option, so nothing leaks to other clients.
"""
import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from .. import config
from ..db import direct_dsn

SERVERLESS = bool(os.environ.get("VERCEL"))
_pool = None


def _dsn_and_options() -> tuple[str, dict]:
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set (see .env.example)")
    dsn = config.DATABASE_URL
    # prepare_threshold=None: no server-side prepared statements, safe behind PgBouncer
    kwargs = {"autocommit": True, "row_factory": dict_row, "connect_timeout": 15, "prepare_threshold": None}
    if schema := os.environ.get("API_DB_SCHEMA"):
        dsn = direct_dsn(dsn)
        kwargs["options"] = f"-c search_path={schema},public"
    return dsn, kwargs


def _get_pool():
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool
        dsn, kwargs = _dsn_and_options()
        _pool = ConnectionPool(dsn, min_size=1, max_size=6, kwargs=kwargs,
                               check=ConnectionPool.check_connection,   # Neon may drop idle connections
                               timeout=30, open=True)
    return _pool


@contextmanager
def connection():
    if SERVERLESS:
        dsn, kwargs = _dsn_and_options()
        with psycopg.connect(dsn, **kwargs) as conn:
            yield conn
    else:
        with _get_pool().connection() as conn:
            yield conn


def close() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
