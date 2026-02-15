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
    SymbolMetaUpdate,
    TournamentStartResponse,
    TournamentCurrentResponse,
    TournamentMatch,
    TournamentMatchSide,
    TournamentPick,
    TournamentResultsResponse,
    TournamentResultRow,
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


def _next_power_of_two(n: int) -> int:
    return 1 << (n - 1).bit_length()


async def _get_active_tournament(conn):
    return await conn.fetchrow(
        "SELECT * FROM tournaments WHERE status = 'active' ORDER BY created_at DESC LIMIT 1"
    )


async def _place_winner(
    conn,
    tournament_id: int,
    round_num: int,
    match_index: int,
    winner_symbol: str,
    total_rounds: int,
):
    if round_num >= total_rounds:
        return
    parent_round = round_num + 1
    parent_index = match_index // 2
    if match_index % 2 == 0:
        await conn.execute(
            """UPDATE tournament_matches
               SET symbol_a = COALESCE(symbol_a, $1)
               WHERE tournament_id = $2 AND round = $3 AND match_index = $4""",
            winner_symbol,
            tournament_id,
            parent_round,
            parent_index,
        )
    else:
        await conn.execute(
            """UPDATE tournament_matches
               SET symbol_b = COALESCE(symbol_b, $1)
               WHERE tournament_id = $2 AND round = $3 AND match_index = $4""",
            winner_symbol,
            tournament_id,
            parent_round,
            parent_index,
        )


async def _advance_byes(conn, tournament_id: int, total_rounds: int) -> None:
    changed = True
    while changed:
        changed = False
        rows = await conn.fetch(
            """SELECT id, round, match_index, symbol_a, symbol_b, winner_symbol
               FROM tournament_matches
               WHERE tournament_id = $1
               ORDER BY round, match_index""",
            tournament_id,
        )
        for r in rows:
            if r["winner_symbol"] is not None:
                continue
            a = r["symbol_a"]
            b = r["symbol_b"]
            if (a and not b) or (b and not a):
                winner = a or b
                await conn.execute(
                    "UPDATE tournament_matches SET winner_symbol = $1, decided_at = NOW() WHERE id = $2",
                    winner,
                    r["id"],
                )
                await _place_winner(conn, tournament_id, r["round"], r["match_index"], winner, total_rounds)
                changed = True


async def _build_match_side(conn, symbol: str, side: str) -> TournamentMatchSide:
    metrics_row = await conn.fetchrow(
        "SELECT * FROM screener_metrics WHERE symbol = $1",
        symbol,
    )
    metrics_row = dict(metrics_row) if metrics_row else None
    income_rows = [dict(r) for r in await conn.fetch(
        "SELECT * FROM quarterly_income WHERE symbol = $1 ORDER BY period_end_date", symbol
    )]
    bs_rows = [dict(r) for r in await conn.fetch(
        "SELECT * FROM quarterly_balance_sheet WHERE symbol = $1 ORDER BY period_end_date", symbol
    )]
    cf_rows = [dict(r) for r in await conn.fetch(
        "SELECT * FROM quarterly_cash_flow WHERE symbol = $1 ORDER BY period_end_date", symbol
    )]
    metrics = compute_all_metrics(
        income_rows, bs_rows, cf_rows,
        market_cap=None, ev=None, last_close=None,
    )

    stats = {}
    if metrics_row:
        stats = {
            "median_roic": metrics_row.get("median_roic"),
            "median_roe": metrics_row.get("median_roe"),
            "median_roa": metrics_row.get("median_roa"),
            "median_operating_margin": metrics_row.get("median_operating_margin"),
            "median_fcf_margin": metrics_row.get("median_fcf_margin"),
            "median_revenue_growth": metrics_row.get("median_revenue_growth"),
            "median_eps_growth": metrics_row.get("median_eps_growth"),
            "pct_eps_yoy_positive": metrics_row.get("pct_eps_yoy_positive"),
            "eps_cagr": metrics_row.get("eps_cagr"),
            "revenue_cagr": metrics_row.get("revenue_cagr"),
            "median_debt_to_equity": metrics_row.get("median_debt_to_equity"),
        }

    return TournamentMatchSide(
        side=side,
        stats=stats,
        annual_table=[AnnualRow(**row) for row in metrics["annual_table"]],
    )


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
        rating=company_row["rating"],
        note=company_row["note"],
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


@router.patch("/symbol/{symbol}/meta", response_model=CompanyInfo)
async def update_symbol_meta(symbol: str, body: SymbolMetaUpdate):
    """Update per-symbol metadata (rating/note)."""
    symbol = symbol.upper().strip()
    if not symbol:
        raise HTTPException(400, "Symbol is required")

    updates = body.dict(exclude_unset=True)
    if "note" in updates and updates["note"] is not None:
        note = updates["note"].strip()
        updates["note"] = note if note else None

    if not updates:
        raise HTTPException(400, "No fields to update")

    set_clauses: list[str] = []
    params: list[object] = []
    idx = 1
    for field in ("rating", "note"):
        if field in updates:
            set_clauses.append(f"{field} = ${idx}")
            params.append(updates[field])
            idx += 1
    set_clauses.append("last_updated = NOW()")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE companies SET {', '.join(set_clauses)} WHERE symbol = ${idx} RETURNING *",
            *params,
            symbol,
        )

    if not row:
        raise HTTPException(404, f"Symbol {symbol} not found")

    return CompanyInfo(
        symbol=symbol,
        name=row["name"],
        exchange=row["exchange"],
        sector=row["sector"],
        industry=row["industry"],
        currency=row["currency"],
        description=row["description"],
        rating=row["rating"],
        note=row["note"],
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
    "symbol", "name", "rating", "note", "sector", "industry", "pct_eps_yoy_positive",
}

_SCREENER_SORT_SQL: dict[str, str] = {col: f"sm.{col}" for col in _SCREENER_FILTER_COLS}
_SCREENER_SORT_SQL.update({
    "symbol": "sm.symbol",
    "name": "sm.name",
    "sector": "sm.sector",
    "industry": "sm.industry",
    "rating": "c.rating",
    "note": "c.note",
    "pct_eps_yoy_positive": "sm.pct_eps_yoy_positive",
})

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
    rating: str | None = Query(None, description="Rating filter: good, bad, all (default hides bad)"),
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
                cond = f"sm.{col} >= ${idx}"
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
                cond = f"sm.{col} <= ${idx}"
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
        and_conditions.append(f"sm.sector ILIKE ${idx}")
        params.append(sector)
        idx += 1

    if industry:
        and_conditions.append(f"sm.industry ILIKE ${idx}")
        params.append(industry)
        idx += 1

    if rating == "good":
        and_conditions.append(f"c.rating = ${idx}")
        params.append("good")
        idx += 1
    elif rating == "bad":
        and_conditions.append(f"c.rating = ${idx}")
        params.append("bad")
        idx += 1
    elif rating == "all":
        pass
    else:
        and_conditions.append("c.rating IS DISTINCT FROM 'bad'")

    where = "WHERE " + " AND ".join(and_conditions) if and_conditions else ""

    # ---- validate sort ----
    if sort_by not in _SCREENER_SORT_COLS:
        sort_by = "symbol"
    if sort_dir.lower() not in ("asc", "desc"):
        sort_dir = "asc"
    sort_expr = _SCREENER_SORT_SQL.get(sort_by, "sm.symbol")
    order = f"ORDER BY {sort_expr} {sort_dir} NULLS LAST"

    # ---- execute queries ----
    async with pool.acquire() as conn:
        # Check if the materialized view exists and has data
        try:
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM screener_metrics sm LEFT JOIN companies c ON sm.symbol = c.symbol {where}", *params
            )
        except Exception:
            # View may not exist or be empty yet
            return ScreenerResponse(results=[], total=0)

        rows = await conn.fetch(
            f"SELECT sm.*, c.rating AS rating, c.note AS note "
            f"FROM screener_metrics sm LEFT JOIN companies c ON sm.symbol = c.symbol "
            f"{where} {order} "
            f"LIMIT ${idx} OFFSET ${idx + 1}",
            *params, limit, offset,
        )

    return ScreenerResponse(
        results=[ScreenerRow(**dict(r)) for r in rows],
        total=total,
    )


# ---------------------------------------------------------------------------
# Tournament (single active)
# ---------------------------------------------------------------------------


@router.post("/tournament/start", response_model=TournamentStartResponse)
async def start_tournament():
    pool = await get_pool()
    async with pool.acquire() as conn:
        active = await _get_active_tournament(conn)
        if active:
            return TournamentStartResponse(
                tournament_id=active["id"],
                status=active["status"],
                total_stocks=active["total_stocks"],
                bracket_size=active["bracket_size"],
                total_rounds=active["total_rounds"],
            )

        rows = await conn.fetch(
            """SELECT sm.symbol,
                      sm.eps_cagr,
                      sm.pct_eps_yoy_positive
               FROM screener_metrics sm
               INNER JOIN companies c ON sm.symbol = c.symbol
               WHERE c.rating = 'good'
                 AND sm.eps_cagr IS NOT NULL
                 AND sm.pct_eps_yoy_positive IS NOT NULL
               ORDER BY (sm.eps_cagr * (sm.pct_eps_yoy_positive / 100.0)) DESC"""
        )

        if len(rows) < 2:
            raise HTTPException(400, "Need at least 2 good-rated stocks with EPS metrics")

        entries = []
        for idx, r in enumerate(rows, start=1):
            seed_score = float(r["eps_cagr"]) * (float(r["pct_eps_yoy_positive"]) / 100.0)
            entries.append((r["symbol"], idx, seed_score))

        total_stocks = len(entries)
        bracket_size = _next_power_of_two(total_stocks)
        total_rounds = bracket_size.bit_length() - 1

        tournament = await conn.fetchrow(
            """INSERT INTO tournaments (status, seed_formula, total_stocks, bracket_size, total_rounds)
               VALUES ('active', $1, $2, $3, $4)
               RETURNING *""",
            "eps_cagr * (pct_eps_yoy_positive / 100)",
            total_stocks,
            bracket_size,
            total_rounds,
        )

        await conn.executemany(
            """INSERT INTO tournament_entries (tournament_id, symbol, seed_rank, seed_score)
               VALUES ($1, $2, $3, $4)""",
            [(tournament["id"], sym, rank, score) for sym, rank, score in entries],
        )

        seeds = [sym for sym, _rank, _score in entries]
        seeds.extend([None] * (bracket_size - total_stocks))
        round1_matches = []
        match_count = bracket_size // 2
        for i in range(match_count):
            a = seeds[i]
            b = seeds[bracket_size - 1 - i]
            round1_matches.append((tournament["id"], 1, i, a, b))

        await conn.executemany(
            """INSERT INTO tournament_matches (tournament_id, round, match_index, symbol_a, symbol_b)
               VALUES ($1, $2, $3, $4, $5)""",
            round1_matches,
        )

        # Create empty matches for remaining rounds
        for round_num in range(2, total_rounds + 1):
            match_count = bracket_size // (2 ** round_num)
            await conn.executemany(
                """INSERT INTO tournament_matches (tournament_id, round, match_index)
                   VALUES ($1, $2, $3)""",
                [(tournament["id"], round_num, i) for i in range(match_count)],
            )

        await _advance_byes(conn, tournament["id"], total_rounds)

        return TournamentStartResponse(
            tournament_id=tournament["id"],
            status=tournament["status"],
            total_stocks=total_stocks,
            bracket_size=bracket_size,
            total_rounds=total_rounds,
        )


@router.get("/tournament/current", response_model=TournamentCurrentResponse)
async def get_current_tournament():
    pool = await get_pool()
    async with pool.acquire() as conn:
        active = await _get_active_tournament(conn)
        if not active:
            raise HTTPException(404, "No active tournament")

        await _advance_byes(conn, active["id"], active["total_rounds"])

        total_matches = await conn.fetchval(
            "SELECT COUNT(*) FROM tournament_matches WHERE tournament_id = $1",
            active["id"],
        )
        decided_matches = await conn.fetchval(
            "SELECT COUNT(*) FROM tournament_matches WHERE tournament_id = $1 AND winner_symbol IS NOT NULL",
            active["id"],
        )

        match_row = await conn.fetchrow(
            """SELECT * FROM tournament_matches
               WHERE tournament_id = $1
                 AND winner_symbol IS NULL
                 AND symbol_a IS NOT NULL
                 AND symbol_b IS NOT NULL
               ORDER BY round, match_index
               LIMIT 1""",
            active["id"],
        )

        next_match = None
        if match_row:
            side_a = await _build_match_side(conn, match_row["symbol_a"], "A")
            side_b = await _build_match_side(conn, match_row["symbol_b"], "B")
            next_match = TournamentMatch(
                match_id=match_row["id"],
                round=match_row["round"],
                match_index=match_row["match_index"],
                side_a=side_a,
                side_b=side_b,
            )

        return TournamentCurrentResponse(
            tournament_id=active["id"],
            status=active["status"],
            total_stocks=active["total_stocks"],
            bracket_size=active["bracket_size"],
            total_rounds=active["total_rounds"],
            decided_matches=decided_matches,
            total_matches=total_matches,
            next_match=next_match,
        )


@router.post("/tournament/pick", response_model=TournamentCurrentResponse)
async def pick_tournament_winner(body: TournamentPick):
    pool = await get_pool()
    async with pool.acquire() as conn:
        active = await _get_active_tournament(conn)
        if not active:
            raise HTTPException(404, "No active tournament")

        match_row = await conn.fetchrow(
            "SELECT * FROM tournament_matches WHERE id = $1 AND tournament_id = $2",
            body.match_id,
            active["id"],
        )
        if not match_row:
            raise HTTPException(404, "Match not found")
        if match_row["winner_symbol"] is not None:
            raise HTTPException(400, "Match already decided")

        winner_symbol = match_row["symbol_a"] if body.winner_side == "A" else match_row["symbol_b"]
        if winner_symbol is None:
            raise HTTPException(400, "Invalid winner side")

        await conn.execute(
            "UPDATE tournament_matches SET winner_symbol = $1, decided_at = NOW() WHERE id = $2",
            winner_symbol,
            match_row["id"],
        )
        await _place_winner(
            conn,
            active["id"],
            match_row["round"],
            match_row["match_index"],
            winner_symbol,
            active["total_rounds"],
        )
        await _advance_byes(conn, active["id"], active["total_rounds"])

    return await get_current_tournament()


@router.get("/tournament/results", response_model=TournamentResultsResponse)
async def get_tournament_results():
    pool = await get_pool()
    async with pool.acquire() as conn:
        active = await _get_active_tournament(conn)
        if not active:
            raise HTTPException(404, "No active tournament")

        entries = await conn.fetch(
            """SELECT te.symbol, te.seed_rank, te.seed_score, c.name
               FROM tournament_entries te
               LEFT JOIN companies c ON te.symbol = c.symbol
               WHERE te.tournament_id = $1""",
            active["id"],
        )
        total_stocks = active["total_stocks"]
        if total_stocks <= 20:
            results = sorted(entries, key=lambda r: r["seed_rank"])
            return TournamentResultsResponse(
                tournament_id=active["id"],
                status=active["status"],
                results=[
                    TournamentResultRow(
                        symbol=r["symbol"],
                        name=r["name"],
                        rank=idx + 1,
                        seed_rank=r["seed_rank"],
                        seed_score=float(r["seed_score"]),
                    )
                    for idx, r in enumerate(results)
                ],
            )

        target_round = max(1, active["total_rounds"] - 4)
        matches = await conn.fetch(
            """SELECT * FROM tournament_matches
               WHERE tournament_id = $1 AND round = $2""",
            active["id"],
            target_round,
        )
        winners = []
        losers = []
        for m in matches:
            if m["winner_symbol"] is None:
                continue
            winners.append(m["winner_symbol"])
            loser = m["symbol_b"] if m["winner_symbol"] == m["symbol_a"] else m["symbol_a"]
            if loser:
                losers.append(loser)

        if len(winners) < 16:
            raise HTTPException(400, "Tournament not far enough to compute top 20")

        entry_map = {r["symbol"]: r for r in entries}
        losers_sorted = sorted(
            [entry_map[s] for s in losers if s in entry_map],
            key=lambda r: r["seed_rank"],
        )
        top20_symbols = winners + [r["symbol"] for r in losers_sorted[:4]]
        results = [entry_map[s] for s in top20_symbols if s in entry_map]
        results_sorted = sorted(results, key=lambda r: r["seed_rank"])

        return TournamentResultsResponse(
            tournament_id=active["id"],
            status=active["status"],
            results=[
                TournamentResultRow(
                    symbol=r["symbol"],
                    name=r["name"],
                    rank=idx + 1,
                    seed_rank=r["seed_rank"],
                    seed_score=float(r["seed_score"]),
                )
                for idx, r in enumerate(results_sorted)
            ],
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
