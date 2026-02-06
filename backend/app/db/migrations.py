"""Auto-create database tables on startup."""

import os
import logging

import asyncpg

logger = logging.getLogger(__name__)

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


async def run_migrations(pool: asyncpg.Pool):
    """Execute schema.sql to create tables if they don't exist."""
    with open(SCHEMA_PATH) as f:
        sql = f.read()

    async with pool.acquire() as conn:
        await conn.execute(sql)
    logger.info("Database migrations complete.")


def run_migrations_sync(dsn: str):
    """Run migrations synchronously (for CLI startup)."""
    import psycopg2

    with open(SCHEMA_PATH) as f:
        sql = f.read()

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        logger.info("Database migrations complete (sync).")
    finally:
        conn.close()
