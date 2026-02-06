"""
API routes for the symbol page.

GET /api/symbol/{symbol}  -- full symbol page data
GET /api/search?q=...     -- symbol search
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.app.db.connection import get_pool
from backend.app.services.fmp_client import FMPClient
from backend.app.services.ingestion import IngestionService
from backend.app.services.metrics import compute_all_metrics
from backend.app.models.schemas import (
    SymbolPageResponse,
    CompanyInfo,
    MarketData,
    KeyStatistics,
    ValuationRatios,
    MedianReturns,
    MedianMargins,
    CAGR10yr,
    CapitalStructure,
    AnnualRow,
    ROICPoint,
    SearchResult,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Shared FMP client instance (created on first use)
_fmp: FMPClient | None = None


def _get_fmp() -> FMPClient:
    global _fmp
    if _fmp is None:
        _fmp = FMPClient()
    return _fmp


# ---------------------------------------------------------------------------
# GET /api/symbol/{symbol}
# ---------------------------------------------------------------------------

@router.get("/symbol/{symbol}", response_model=SymbolPageResponse)
async def get_symbol_page(symbol: str):
    """Return all data needed to render the symbol page."""
    symbol = symbol.upper().strip()
    if not symbol:
        raise HTTPException(400, "Symbol is required")

    pool = await get_pool()
    fmp = _get_fmp()
    ingestion = IngestionService(fmp, pool)

    # 1. Ensure we have data (ingest on-demand if needed)
    if not await ingestion.is_fresh(symbol):
        try:
            await ingestion.ingest_symbol(symbol, force=False)
        except Exception as e:
            logger.error("Ingestion failed for %s: %s", symbol, e)
            # Continue anyway -- we might have stale data

    # 2. Fetch company info from DB
    async with pool.acquire() as conn:
        company_row = await conn.fetchrow(
            "SELECT * FROM companies WHERE symbol = $1", symbol
        )

    if not company_row:
        raise HTTPException(404, f"Symbol {symbol} not found")

    company = CompanyInfo(
        symbol=symbol,
        name=company_row["name"],
        exchange=company_row["exchange"],
        sector=company_row["sector"],
        industry=company_row["industry"],
        currency=company_row["currency"],
        description=company_row["description"],
    )

    # 3. Fetch live market data from FMP
    quote = await fmp.get_quote(symbol)
    last_close = None
    market_cap = None
    ev_value = None
    shares = None
    change_pct = None

    if quote:
        last_close = quote.get("previousClose") or quote.get("price")
        market_cap = quote.get("marketCap")
        shares = quote.get("sharesOutstanding")
        change_pct = quote.get("changesPercentage")

        # Compute EV: market_cap + total_debt - cash
        # We'll get this from the latest balance sheet
        async with pool.acquire() as conn:
            bs_latest = await conn.fetchrow(
                """SELECT long_term_debt, short_term_debt, cash_and_equivalents
                   FROM quarterly_balance_sheet
                   WHERE symbol = $1
                   ORDER BY period_end_date DESC LIMIT 1""",
                symbol,
            )
        if bs_latest and market_cap:
            ltd = bs_latest["long_term_debt"] or 0
            std = bs_latest["short_term_debt"] or 0
            cash = bs_latest["cash_and_equivalents"] or 0
            ev_value = market_cap + ltd + std - cash

    market_data = MarketData(
        last_close=last_close,
        market_cap=market_cap,
        ev=ev_value,
        shares_outstanding=shares,
        price_change_pct=change_pct,
    )

    # 4. Fetch quarterly data from DB
    async with pool.acquire() as conn:
        income_rows = [dict(r) for r in await conn.fetch(
            "SELECT * FROM quarterly_income WHERE symbol = $1 ORDER BY period_end_date", symbol
        )]
        bs_rows = [dict(r) for r in await conn.fetch(
            "SELECT * FROM quarterly_balance_sheet WHERE symbol = $1 ORDER BY period_end_date", symbol
        )]
        cf_rows = [dict(r) for r in await conn.fetch(
            "SELECT * FROM quarterly_cash_flow WHERE symbol = $1 ORDER BY period_end_date", symbol
        )]

    # 5. Compute all metrics
    metrics = compute_all_metrics(
        income_rows, bs_rows, cf_rows,
        market_cap=market_cap, ev=ev_value, last_close=last_close,
    )

    # 6. Build response
    return SymbolPageResponse(
        company=company,
        market_data=market_data,
        key_statistics=KeyStatistics(
            valuation_ratios=ValuationRatios(**metrics["valuation_ratios"]),
            median_returns=MedianReturns(**metrics["median_returns"]),
            median_margins=MedianMargins(**metrics["median_margins"]),
            cagr_10yr=CAGR10yr(**metrics["cagr_10yr"]),
            capital_structure=CapitalStructure(**metrics["capital_structure"]),
        ),
        annual_table=[AnnualRow(**row) for row in metrics["annual_table"]],
        roic_chart=[ROICPoint(**pt) for pt in metrics["roic_chart"]],
    )


# ---------------------------------------------------------------------------
# GET /api/search?q=...
# ---------------------------------------------------------------------------

@router.get("/search", response_model=list[SearchResult])
async def search_symbols(q: str = Query(..., min_length=1)):
    """Search for symbols by ticker or company name."""
    pool = await get_pool()

    # First try local DB
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT s.symbol, COALESCE(c.name, s.name) as name, COALESCE(c.exchange, s.exchange) as exchange
               FROM symbols s
               LEFT JOIN companies c ON s.symbol = c.symbol
               WHERE s.symbol ILIKE $1 OR s.name ILIKE $2
               ORDER BY
                 CASE WHEN s.symbol ILIKE $1 THEN 0 ELSE 1 END,
                 s.symbol
               LIMIT 15""",
            f"{q}%",
            f"%{q}%",
        )

    if rows:
        return [SearchResult(symbol=r["symbol"], name=r["name"], exchange=r["exchange"]) for r in rows]

    # Fall back to FMP: try ticker search first, then name search
    fmp = _get_fmp()

    def _normalize_fmp_result(r: dict) -> SearchResult:
        return SearchResult(
            symbol=r.get("symbol", ""),
            name=r.get("name"),
            exchange=r.get("exchangeShortName") or r.get("exchange"),
        )

    try:
        # search-symbol matches ticker prefixes (e.g. "AAPL")
        results = await fmp.search_symbol(q, limit=10)
        if not results:
            # search-name matches company names (e.g. "Apple")
            results = await fmp.search_name(q, limit=10)
        if results:
            return [_normalize_fmp_result(r) for r in results]
    except Exception as e:
        logger.error("FMP search failed: %s", e)

    return []
