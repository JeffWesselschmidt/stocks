"""
API routes for the symbol page and screener.

GET  /api/symbol/{symbol}  -- full symbol page data
GET  /api/search?q=...     -- symbol search
GET  /api/screener         -- screener with filters, sorting, pagination
GET  /api/screens          -- list saved screens
POST /api/screens          -- create a saved screen
DELETE /api/screens/{id}   -- delete a saved screen
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request

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
    QuarterlyRow,
    ROICPoint,
    SearchResult,
    ScreenerRow,
    ScreenerResponse,
    SavedScreen,
    SavedScreenCreate,
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
        quarterly_table=[QuarterlyRow(**row) for row in metrics["quarterly_table"]],
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


# ---------------------------------------------------------------------------
# GET /api/screener
# ---------------------------------------------------------------------------

# Numeric columns that support min_* / max_* query-param filters.
_SCREENER_FILTER_COLS: set[str] = {
    "median_roa", "median_roe", "median_roic",
    "profit_pct",
    "median_gross_margin", "median_operating_margin", "median_net_margin", "median_fcf_margin",
    "median_revenue_growth", "median_ni_growth", "median_eps_growth",
    "median_ocf_growth", "median_fcf_growth",
    "revenue_cagr", "eps_cagr", "ocf_cagr", "fcf_cagr",
    "latest_long_term_debt", "median_debt_to_equity", "latest_current_ratio",
    "years_of_data",
}

# All columns valid for ORDER BY.
_SCREENER_SORT_COLS: set[str] = _SCREENER_FILTER_COLS | {
    "symbol", "name", "sector", "industry",
}

# Filter groups: map group key -> set of column names.
# When a group key appears in the `or_groups` query param, conditions for
# its columns are OR'd together instead of AND'd.
_SCREENER_FILTER_GROUPS: dict[str, set[str]] = {
    "returns": {"median_roa", "median_roe", "median_roic"},
    "profitability": {"profit_pct"},
    "margins": {"median_gross_margin", "median_operating_margin", "median_net_margin", "median_fcf_margin"},
    "growth_yoy": {"median_revenue_growth", "median_ni_growth", "median_eps_growth", "median_ocf_growth", "median_fcf_growth"},
    "growth_cagr": {"revenue_cagr", "eps_cagr", "ocf_cagr", "fcf_cagr"},
    "debt": {"median_debt_to_equity", "latest_current_ratio"},
}

# Reverse lookup: column -> group key
_COL_TO_GROUP: dict[str, str] = {}
for _gk, _cols in _SCREENER_FILTER_GROUPS.items():
    for _c in _cols:
        _COL_TO_GROUP[_c] = _gk


@router.get("/screener", response_model=ScreenerResponse)
async def get_screener(
    request: Request,
    sector: str | None = Query(None, description="Filter by sector (case-insensitive)"),
    industry: str | None = Query(None, description="Filter by industry (case-insensitive)"),
    or_groups: str | None = Query(None, description="Comma-separated group keys to OR within (e.g. returns,growth_yoy)"),
    sort_by: str = Query("symbol", description="Column to sort by"),
    sort_dir: str = Query("asc", description="Sort direction: asc or desc"),
    limit: int = Query(50, ge=1, le=200, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """Screen stocks by fundamental metrics.

    Dynamic numeric filters are passed as query params:
      min_<column>=N  and/or  max_<column>=N
    For example: ?min_median_roic=15&max_median_debt_to_equity=0.5

    Use or_groups to OR conditions within a filter group:
      ?or_groups=returns,growth_yoy&min_median_roic=15&min_median_roe=15
    This means: (ROIC >= 15 OR ROE >= 15) instead of (ROIC >= 15 AND ROE >= 15).
    Groups not listed in or_groups remain AND'd as usual.
    """
    pool = await get_pool()

    # Parse which groups should use OR logic
    or_group_set: set[str] = set()
    if or_groups:
        or_group_set = {g.strip() for g in or_groups.split(",") if g.strip() in _SCREENER_FILTER_GROUPS}

    # ---- build WHERE clause from query params ----
    # Conditions that are AND'd at the top level
    and_conditions: list[str] = []
    # Conditions bucketed by OR group key
    or_buckets: dict[str, list[str]] = {}
    params: list[object] = []
    idx = 1  # asyncpg uses $1, $2, … placeholders

    for col in _SCREENER_FILTER_COLS:
        group_key = _COL_TO_GROUP.get(col)
        use_or = group_key is not None and group_key in or_group_set

        min_val = request.query_params.get(f"min_{col}")
        if min_val is not None:
            try:
                cond = f"{col} >= ${idx}"
                params.append(float(min_val))
                idx += 1
                if use_or:
                    or_buckets.setdefault(group_key, []).append(cond)
                else:
                    and_conditions.append(cond)
            except ValueError:
                pass
        max_val = request.query_params.get(f"max_{col}")
        if max_val is not None:
            try:
                cond = f"{col} <= ${idx}"
                params.append(float(max_val))
                idx += 1
                if use_or:
                    or_buckets.setdefault(group_key, []).append(cond)
                else:
                    and_conditions.append(cond)
            except ValueError:
                pass

    # Collapse each OR bucket into a single parenthesized condition
    for _gk, bucket in or_buckets.items():
        if len(bucket) == 1:
            and_conditions.append(bucket[0])
        else:
            and_conditions.append(f"({' OR '.join(bucket)})")

    if sector:
        and_conditions.append(f"sector ILIKE ${idx}")
        params.append(sector)
        idx += 1

    if industry:
        and_conditions.append(f"industry ILIKE ${idx}")
        params.append(industry)
        idx += 1

    where = "WHERE " + " AND ".join(and_conditions) if and_conditions else ""

    # ---- validate sort ----
    if sort_by not in _SCREENER_SORT_COLS:
        sort_by = "symbol"
    if sort_dir.lower() not in ("asc", "desc"):
        sort_dir = "asc"
    order = f"ORDER BY {sort_by} {sort_dir} NULLS LAST"

    # ---- execute queries ----
    async with pool.acquire() as conn:
        # Check if the materialized view exists and has data
        try:
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM screener_metrics {where}", *params
            )
        except Exception:
            # View may not exist or be empty yet
            return ScreenerResponse(results=[], total=0)

        rows = await conn.fetch(
            f"SELECT * FROM screener_metrics {where} {order} "
            f"LIMIT ${idx} OFFSET ${idx + 1}",
            *params, limit, offset,
        )

    return ScreenerResponse(
        results=[ScreenerRow(**dict(r)) for r in rows],
        total=total,
    )


# ---------------------------------------------------------------------------
# Saved Screens  (GET / POST / DELETE)
# ---------------------------------------------------------------------------

@router.get("/screens", response_model=list[SavedScreen])
async def list_screens():
    """List all saved screens, newest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, filters, created_at FROM saved_screens ORDER BY created_at DESC"
        )
    return [
        SavedScreen(
            id=r["id"],
            name=r["name"],
            filters=json.loads(r["filters"]) if isinstance(r["filters"], str) else dict(r["filters"]),
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


@router.post("/screens", response_model=SavedScreen, status_code=201)
async def create_screen(body: SavedScreenCreate):
    """Save the current screener filters with a name."""
    if not body.name.strip():
        raise HTTPException(400, "Name is required")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO saved_screens (name, filters) VALUES ($1, $2::jsonb) RETURNING id, name, filters, created_at",
            body.name.strip(),
            json.dumps(body.filters),
        )

    return SavedScreen(
        id=row["id"],
        name=row["name"],
        filters=json.loads(row["filters"]) if isinstance(row["filters"], str) else dict(row["filters"]),
        created_at=row["created_at"].isoformat(),
    )


@router.delete("/screens/{screen_id}", status_code=204)
async def delete_screen(screen_id: int):
    """Delete a saved screen by ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM saved_screens WHERE id = $1", screen_id
        )
    if result == "DELETE 0":
        raise HTTPException(404, "Screen not found")
