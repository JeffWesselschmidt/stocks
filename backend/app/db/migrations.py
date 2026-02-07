"""Auto-create database tables and materialized views on startup."""

import os
import logging

import asyncpg

logger = logging.getLogger(__name__)

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
SCREENER_VIEW_PATH = os.path.join(os.path.dirname(__file__), "screener_view.sql")


async def run_migrations(pool: asyncpg.Pool):
    """Execute schema.sql and screener_view.sql to create tables/views if they don't exist."""
    with open(SCHEMA_PATH) as f:
        schema_sql = f.read()
    with open(SCREENER_VIEW_PATH) as f:
        screener_sql = f.read()

    async with pool.acquire() as conn:
        await conn.execute(schema_sql)
        await conn.execute(screener_sql)
    logger.info("Database migrations complete.")


def run_migrations_sync(dsn: str):
    """Run migrations synchronously (for CLI startup)."""
    import psycopg2

    with open(SCHEMA_PATH) as f:
        schema_sql = f.read()
    with open(SCREENER_VIEW_PATH) as f:
        screener_sql = f.read()

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
            cur.execute(screener_sql)
        conn.commit()
        logger.info("Database migrations complete (sync).")
    finally:
        conn.close()
