"""Database connection management for both async (web) and sync (CLI) contexts."""

import asyncpg
import psycopg2
import psycopg2.extras

from backend.app.config import settings

# ---------------------------------------------------------------------------
# Async connection pool (for FastAPI / web)
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the asyncpg connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.asyncpg_url,
            min_size=2,
            max_size=10,
        )
    return _pool


async def close_pool():
    """Close the asyncpg connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Sync connection (for CLI)
# ---------------------------------------------------------------------------


def get_sync_connection():
    """Get a synchronous psycopg2 connection for CLI operations."""
    return psycopg2.connect(settings.database_url)


def sync_execute(query: str, params: tuple | None = None):
    """Execute a query synchronously and return rows as dicts."""
    conn = get_sync_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            if cur.description:
                rows = cur.fetchall()
                conn.commit()
                return [dict(r) for r in rows]
            conn.commit()
            return []
    finally:
        conn.close()


def sync_execute_many(query: str, params_list: list[tuple]):
    """Execute a query with many parameter sets synchronously."""
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.executemany(query, params_list)
        conn.commit()
    finally:
        conn.close()
