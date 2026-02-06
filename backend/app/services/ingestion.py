"""
Ingestion service: fetch quarterly fundamental data from FMP and upsert into PostgreSQL.

Provides both async (for web) and sync (for CLI) paths, sharing the same
normalization and upsert logic.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any

import asyncpg
import psycopg2
import psycopg2.extras

from backend.app.services.fmp_client import FMPClient, FMPClientSync

logger = logging.getLogger(__name__)

# How many hours before we consider stored data stale
FRESHNESS_HOURS = 24


# ---------------------------------------------------------------------------
# Field mapping: FMP JSON key -> our DB column name
# ---------------------------------------------------------------------------

INCOME_FIELDS = {
    "revenue": "revenue",
    "costOfRevenue": "cost_of_revenue",
    "grossProfit": "gross_profit",
    "operatingIncome": "operating_income",
    "incomeBeforeTax": "income_before_tax",
    "incomeTaxExpense": "income_tax_expense",
    "netIncome": "net_income",
    "epsDiluted": "eps_diluted",
    "eps": "eps_basic",
    "weightedAverageShsOutDil": "weighted_avg_shares_diluted",
    "ebitda": "ebitda",
    "interestExpense": "interest_expense",
}

BALANCE_SHEET_FIELDS = {
    "totalAssets": "total_assets",
    "totalLiabilities": "total_liabilities",
    "totalStockholdersEquity": "total_equity",
    "cashAndCashEquivalents": "cash_and_equivalents",
    "shortTermInvestments": "short_term_investments",
    "totalCurrentAssets": "total_current_assets",
    "totalCurrentLiabilities": "total_current_liabilities",
    "longTermDebt": "long_term_debt",
    "shortTermDebt": "short_term_debt",
    "goodwill": "goodwill",
    "intangibleAssets": "intangible_assets",
}

CASH_FLOW_FIELDS = {
    "operatingCashFlow": "net_cash_operating",
    "capitalExpenditure": "capex",
    "freeCashFlow": "free_cash_flow",
    "dividendsPaid": "dividends_paid",
    "commonStockRepurchased": "common_stock_repurchased",
    "depreciationAndAmortization": "depreciation_amortization",
}


def _parse_date(val: Any):
    """Parse a date string from FMP, return datetime.date or None.

    Returns datetime.date so it works with both asyncpg (requires date objects)
    and psycopg2 (accepts both strings and date objects).
    """
    if not val:
        return None
    if isinstance(val, str):
        try:
            return date.fromisoformat(val[:10])
        except ValueError:
            return None
    return val


def _normalize_row(raw: dict, field_map: dict, symbol: str) -> dict:
    """Normalize an FMP response row into our DB column names."""
    row = {"symbol": symbol}
    row["period_end_date"] = _parse_date(raw.get("date") or raw.get("period"))
    fy = raw.get("calendarYear") or raw.get("fiscalYear")
    if isinstance(fy, str) and fy.isdigit():
        fy = int(fy)
    row["fiscal_year"] = fy
    row["fiscal_quarter"] = _extract_quarter(raw.get("period", ""))
    row["filing_date"] = _parse_date(raw.get("fillingDate") or raw.get("filingDate") or raw.get("acceptedDate"))

    for fmp_key, db_col in field_map.items():
        row[db_col] = raw.get(fmp_key)

    return row


def _extract_quarter(period_str: str) -> int | None:
    """Extract quarter number from FMP period string like 'Q1', 'Q2', etc."""
    if not period_str:
        return None
    period_str = str(period_str).upper().strip()
    for q in (1, 2, 3, 4):
        if f"Q{q}" in period_str:
            return q
    return None


# ---------------------------------------------------------------------------
# Upsert SQL builders
# ---------------------------------------------------------------------------

def _upsert_sql(table: str, columns: list[str]) -> str:
    """Build an INSERT ... ON CONFLICT DO UPDATE statement."""
    cols = ", ".join(columns)
    placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))
    updates = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in columns if c not in ("symbol", "period_end_date", "created_at")
    )
    return (
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT (symbol, period_end_date) DO UPDATE SET {updates}, updated_at = NOW()"
    )


def _upsert_sql_psycopg2(table: str, columns: list[str]) -> str:
    """Build an INSERT ... ON CONFLICT DO UPDATE for psycopg2 (%s placeholders)."""
    cols = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    updates = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in columns if c not in ("symbol", "period_end_date", "created_at")
    )
    return (
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT (symbol, period_end_date) DO UPDATE SET {updates}, updated_at = NOW()"
    )


INCOME_COLS = ["symbol", "period_end_date", "fiscal_year", "fiscal_quarter", "filing_date"] + list(INCOME_FIELDS.values())
BS_COLS = ["symbol", "period_end_date", "fiscal_year", "fiscal_quarter", "filing_date"] + list(BALANCE_SHEET_FIELDS.values())
CF_COLS = ["symbol", "period_end_date", "fiscal_year", "fiscal_quarter", "filing_date"] + list(CASH_FLOW_FIELDS.values())


# ---------------------------------------------------------------------------
# Async Ingestion (for web / FastAPI)
# ---------------------------------------------------------------------------

class IngestionService:
    """Async ingestion service used by the web API."""

    def __init__(self, fmp: FMPClient, pool: asyncpg.Pool):
        self.fmp = fmp
        self.pool = pool

    async def is_fresh(self, symbol: str) -> bool:
        """Check if we have recent data for this symbol.

        Requires both a recent company profile AND at least some quarterly data.
        This prevents stale states where the profile was saved but fundamentals failed.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT last_updated FROM companies WHERE symbol = $1", symbol
            )
            if not row or not row["last_updated"]:
                return False
            age = datetime.now(timezone.utc) - row["last_updated"]
            if age.total_seconds() >= FRESHNESS_HOURS * 3600:
                return False
            # Also verify we actually have quarterly data
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM quarterly_income WHERE symbol = $1", symbol
            )
            return count > 0

    async def ingest_profile(self, symbol: str):
        """Fetch and store company profile."""
        profile = await self.fmp.get_profile(symbol)
        if not profile:
            logger.warning("No profile data for %s", symbol)
            return

        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO companies (symbol, name, exchange, sector, industry, currency, description, market_cap, last_updated)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                   ON CONFLICT (symbol) DO UPDATE SET
                     name = EXCLUDED.name, exchange = EXCLUDED.exchange,
                     sector = EXCLUDED.sector, industry = EXCLUDED.industry,
                     currency = EXCLUDED.currency, description = EXCLUDED.description,
                     market_cap = EXCLUDED.market_cap, last_updated = NOW()""",
                symbol,
                profile.get("companyName"),
                profile.get("exchangeShortName"),
                profile.get("sector"),
                profile.get("industry"),
                profile.get("currency", "USD"),
                profile.get("description"),
                profile.get("mktCap"),
            )

    async def ingest_fundamentals(self, symbol: str):
        """Fetch and store all quarterly statements for a symbol."""
        income_data, bs_data, cf_data = await asyncio.gather(
            self.fmp.get_income_statement(symbol),
            self.fmp.get_balance_sheet(symbol),
            self.fmp.get_cash_flow(symbol),
        )

        async with self.pool.acquire() as conn:
            # Income statements
            if income_data:
                sql = _upsert_sql("quarterly_income", INCOME_COLS)
                for raw in income_data:
                    row = _normalize_row(raw, INCOME_FIELDS, symbol)
                    if row["period_end_date"]:
                        vals = [row.get(c) for c in INCOME_COLS]
                        await conn.execute(sql, *vals)
                logger.info("%s: upserted %d income rows", symbol, len(income_data))

            # Balance sheets
            if bs_data:
                sql = _upsert_sql("quarterly_balance_sheet", BS_COLS)
                for raw in bs_data:
                    row = _normalize_row(raw, BALANCE_SHEET_FIELDS, symbol)
                    if row["period_end_date"]:
                        vals = [row.get(c) for c in BS_COLS]
                        await conn.execute(sql, *vals)
                logger.info("%s: upserted %d balance sheet rows", symbol, len(bs_data))

            # Cash flows
            if cf_data:
                sql = _upsert_sql("quarterly_cash_flow", CF_COLS)
                for raw in cf_data:
                    row = _normalize_row(raw, CASH_FLOW_FIELDS, symbol)
                    if row["period_end_date"]:
                        vals = [row.get(c) for c in CF_COLS]
                        await conn.execute(sql, *vals)
                logger.info("%s: upserted %d cash flow rows", symbol, len(cf_data))

    async def ingest_symbol(self, symbol: str, force: bool = False):
        """Full ingestion for a single symbol (profile + fundamentals)."""
        symbol = symbol.upper()
        if not force and await self.is_fresh(symbol):
            logger.info("%s: data is fresh, skipping", symbol)
            return

        await self.ingest_profile(symbol)
        await self.ingest_fundamentals(symbol)
        logger.info("%s: ingestion complete", symbol)


# We need asyncio import for gather
import asyncio


# ---------------------------------------------------------------------------
# Sync Ingestion (for CLI)
# ---------------------------------------------------------------------------

class IngestionServiceSync:
    """Synchronous ingestion service used by CLI commands."""

    def __init__(self, fmp: FMPClientSync, dsn: str):
        self.fmp = fmp
        self.dsn = dsn

    def _conn(self):
        return psycopg2.connect(self.dsn)

    def is_fresh(self, symbol: str) -> bool:
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT last_updated FROM companies WHERE symbol = %s", (symbol,))
                row = cur.fetchone()
                if not row or not row["last_updated"]:
                    return False
                age = datetime.now(timezone.utc) - row["last_updated"].replace(tzinfo=timezone.utc)
                return age.total_seconds() < FRESHNESS_HOURS * 3600
        finally:
            conn.close()

    def ingest_universe(self, exchanges: tuple[str, ...] = ("NYSE", "NASDAQ")):
        """Fetch all symbols from FMP and upsert into symbols table."""
        all_symbols = self.fmp.get_stock_list()
        filtered = [
            s for s in all_symbols
            if s.get("exchangeShortName") in exchanges
            and s.get("type", "stock") == "stock"
        ]
        logger.info("Fetched %d symbols (%d after filtering to %s)", len(all_symbols), len(filtered), exchanges)

        conn = self._conn()
        try:
            with conn.cursor() as cur:
                for s in filtered:
                    cur.execute(
                        """INSERT INTO symbols (symbol, name, exchange, type, is_active, updated_at)
                           VALUES (%s, %s, %s, %s, TRUE, NOW())
                           ON CONFLICT (symbol) DO UPDATE SET
                             name = EXCLUDED.name, exchange = EXCLUDED.exchange,
                             type = EXCLUDED.type, is_active = TRUE, updated_at = NOW()""",
                        (s.get("symbol"), s.get("name"), s.get("exchangeShortName"), s.get("type", "stock")),
                    )
            conn.commit()
            logger.info("Upserted %d symbols", len(filtered))
        finally:
            conn.close()

        return len(filtered)

    def ingest_profile(self, symbol: str):
        profile = self.fmp.get_profile(symbol)
        if not profile:
            logger.warning("No profile for %s", symbol)
            return

        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO companies (symbol, name, exchange, sector, industry, currency, description, market_cap, last_updated)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                       ON CONFLICT (symbol) DO UPDATE SET
                         name = EXCLUDED.name, exchange = EXCLUDED.exchange,
                         sector = EXCLUDED.sector, industry = EXCLUDED.industry,
                         currency = EXCLUDED.currency, description = EXCLUDED.description,
                         market_cap = EXCLUDED.market_cap, last_updated = NOW()""",
                    (
                        symbol,
                        profile.get("companyName"),
                        profile.get("exchangeShortName"),
                        profile.get("sector"),
                        profile.get("industry"),
                        profile.get("currency", "USD"),
                        profile.get("description"),
                        profile.get("mktCap"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def ingest_fundamentals(self, symbol: str):
        income_data = self.fmp.get_income_statement(symbol)
        bs_data = self.fmp.get_balance_sheet(symbol)
        cf_data = self.fmp.get_cash_flow(symbol)

        conn = self._conn()
        try:
            with conn.cursor() as cur:
                if income_data:
                    sql = _upsert_sql_psycopg2("quarterly_income", INCOME_COLS)
                    for raw in income_data:
                        row = _normalize_row(raw, INCOME_FIELDS, symbol)
                        if row["period_end_date"]:
                            cur.execute(sql, [row.get(c) for c in INCOME_COLS])

                if bs_data:
                    sql = _upsert_sql_psycopg2("quarterly_balance_sheet", BS_COLS)
                    for raw in bs_data:
                        row = _normalize_row(raw, BALANCE_SHEET_FIELDS, symbol)
                        if row["period_end_date"]:
                            cur.execute(sql, [row.get(c) for c in BS_COLS])

                if cf_data:
                    sql = _upsert_sql_psycopg2("quarterly_cash_flow", CF_COLS)
                    for raw in cf_data:
                        row = _normalize_row(raw, CASH_FLOW_FIELDS, symbol)
                        if row["period_end_date"]:
                            cur.execute(sql, [row.get(c) for c in CF_COLS])

            conn.commit()
            counts = (len(income_data or []), len(bs_data or []), len(cf_data or []))
            logger.info("%s: upserted %d income, %d bs, %d cf rows", symbol, *counts)
        finally:
            conn.close()

    def update_ingestion_state(self, symbol: str, job_type: str, status: str, error: str | None = None):
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO ingestion_state (symbol, job_type, status, last_updated, error_message)
                       VALUES (%s, %s, %s, NOW(), %s)
                       ON CONFLICT (symbol, job_type) DO UPDATE SET
                         status = EXCLUDED.status, last_updated = NOW(), error_message = EXCLUDED.error_message""",
                    (symbol, job_type, status, error),
                )
            conn.commit()
        finally:
            conn.close()

    def ingest_symbol(self, symbol: str, force: bool = False):
        """Full ingestion: profile + fundamentals for one symbol."""
        symbol = symbol.upper()
        if not force and self.is_fresh(symbol):
            logger.info("%s: data is fresh, skipping", symbol)
            return

        try:
            self.ingest_profile(symbol)
            self.ingest_fundamentals(symbol)
            self.update_ingestion_state(symbol, "fundamentals", "complete")
            logger.info("%s: ingestion complete", symbol)
        except Exception as e:
            self.update_ingestion_state(symbol, "fundamentals", "error", str(e))
            logger.error("%s: ingestion failed: %s", symbol, e)
            raise
