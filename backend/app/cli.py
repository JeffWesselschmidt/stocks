"""
CLI for bulk data ingestion.

Usage:
    python -m backend.app.cli ingest-universe
    python -m backend.app.cli ingest-fundamentals [--limit N] [--force]
    python -m backend.app.cli ingest-symbol COST [--force]
    python -m backend.app.cli status
"""

import logging
import time

import click

from backend.app.config import settings
from backend.app.db.migrations import run_migrations_sync
from backend.app.services.fmp_client import FMPClientSync
from backend.app.services.ingestion import IngestionServiceSync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _get_service() -> IngestionServiceSync:
    """Create ingestion service with migrations."""
    run_migrations_sync(settings.database_url)
    fmp = FMPClientSync()
    return IngestionServiceSync(fmp, settings.database_url)


@click.group()
def cli():
    """Stocks data ingestion CLI."""


@cli.command("ingest-universe")
def ingest_universe():
    """Fetch all NYSE/NASDAQ symbols and store in the symbols table."""
    svc = _get_service()
    count = svc.ingest_universe()
    click.echo(f"Done. {count} symbols upserted.")


@cli.command("ingest-fundamentals")
@click.option("--limit", default=0, help="Max symbols to process (0 = all)")
@click.option("--force", is_flag=True, help="Re-ingest even if data is fresh")
def ingest_fundamentals(limit: int, force: bool):
    """Bulk-ingest quarterly fundamentals for all symbols in the universe.

    Resumable: skips symbols already marked 'complete' in ingestion_state
    unless --force is set.
    """
    import psycopg2
    import psycopg2.extras

    svc = _get_service()

    # Get symbols that haven't been ingested yet (or all if force)
    conn = psycopg2.connect(settings.database_url)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if force:
                cur.execute("SELECT symbol FROM symbols WHERE is_active = TRUE ORDER BY symbol")
            else:
                cur.execute(
                    """SELECT s.symbol FROM symbols s
                       LEFT JOIN ingestion_state i ON s.symbol = i.symbol AND i.job_type = 'fundamentals'
                       WHERE s.is_active = TRUE AND (i.status IS NULL OR i.status != 'complete')
                       ORDER BY s.symbol"""
                )
            symbols = [r["symbol"] for r in cur.fetchall()]
    finally:
        conn.close()

    if limit > 0:
        symbols = symbols[:limit]

    total = len(symbols)
    click.echo(f"Processing {total} symbols...")

    success = 0
    errors = 0
    start = time.time()

    for i, sym in enumerate(symbols, 1):
        try:
            svc.ingest_symbol(sym, force=force)
            success += 1
        except Exception as e:
            errors += 1
            logger.error("%s: %s", sym, e)

        # Progress every 50 symbols
        if i % 50 == 0 or i == total:
            elapsed = time.time() - start
            rate = i / elapsed * 60 if elapsed > 0 else 0
            click.echo(f"  [{i}/{total}] {success} ok, {errors} errors, {rate:.0f} symbols/min")

    elapsed = time.time() - start
    click.echo(f"Done in {elapsed:.0f}s. {success} succeeded, {errors} errors out of {total}.")


@cli.command("ingest-symbol")
@click.argument("symbol")
@click.option("--force", is_flag=True, help="Re-ingest even if data is fresh")
def ingest_symbol(symbol: str, force: bool):
    """Ingest a single symbol (profile + fundamentals)."""
    svc = _get_service()
    svc.ingest_symbol(symbol, force=force)
    click.echo(f"Done. {symbol.upper()} ingested.")


@cli.command("refresh-screener")
def refresh_screener():
    """Refresh the screener_metrics materialized view.

    Run this after ingesting new data so the screener reflects the latest
    quarterly fundamentals.
    """
    import psycopg2

    run_migrations_sync(settings.database_url)
    conn = psycopg2.connect(settings.database_url)
    try:
        # Use CONCURRENTLY so readers are not blocked during refresh.
        # Requires the unique index on screener_metrics(symbol).
        conn.autocommit = True
        with conn.cursor() as cur:
            click.echo("Refreshing screener_metrics materialized view...")
            start = time.time()
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY screener_metrics")
            elapsed = time.time() - start
            click.echo(f"Done in {elapsed:.1f}s.")
    finally:
        conn.close()


@cli.command("status")
def status():
    """Show ingestion progress summary."""
    import psycopg2
    import psycopg2.extras

    run_migrations_sync(settings.database_url)
    conn = psycopg2.connect(settings.database_url)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM symbols WHERE is_active = TRUE")
            total_symbols = cur.fetchone()["cnt"]

            cur.execute(
                "SELECT status, COUNT(*) as cnt FROM ingestion_state WHERE job_type = 'fundamentals' GROUP BY status"
            )
            states = {r["status"]: r["cnt"] for r in cur.fetchall()}

            cur.execute("SELECT COUNT(DISTINCT symbol) as cnt FROM quarterly_income")
            symbols_with_data = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) as cnt FROM quarterly_income")
            income_rows = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) as cnt FROM quarterly_balance_sheet")
            bs_rows = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) as cnt FROM quarterly_cash_flow")
            cf_rows = cur.fetchone()["cnt"]

    finally:
        conn.close()

    click.echo(f"Symbol universe: {total_symbols}")
    click.echo(f"Ingestion state:")
    click.echo(f"  complete: {states.get('complete', 0)}")
    click.echo(f"  error:    {states.get('error', 0)}")
    click.echo(f"  pending:  {states.get('pending', 0)}")
    remaining = total_symbols - sum(states.values())
    click.echo(f"  not started: {remaining}")
    click.echo(f"Symbols with data: {symbols_with_data}")
    click.echo(f"Quarterly rows: {income_rows} income, {bs_rows} balance sheet, {cf_rows} cash flow")


if __name__ == "__main__":
    cli()
