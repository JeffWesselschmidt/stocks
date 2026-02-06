"""
Metrics computation engine.

Computes all derived metrics from quarterly fundamental data:
- Annual aggregation (sum quarters / fiscal-year-end balance sheet)
- TTM (trailing twelve months)
- Valuation ratios (P/E, P/B, P/S, EV/*)
- Return metrics (ROA, ROE, ROIC) -- per-year and 10-year median
- Margin metrics -- per-year and 10-year median
- 10-Year CAGR (Revenue, Assets, EPS)
- Capital structure (10-year median)
- YoY growth rates

All formulas are documented inline for explainability (Goal G4).
"""

import logging
from statistics import median
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_div(a: Any, b: Any) -> float | None:
    """Safely divide, returning None if b is zero or either is None."""
    if a is None or b is None:
        return None
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return None
    if b == 0:
        return None
    return a / b


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _pct(val: float | None) -> float | None:
    """Convert ratio to percentage."""
    if val is None:
        return None
    return round(val * 100, 2)


def _round2(val: float | None) -> float | None:
    if val is None:
        return None
    return round(val, 2)


def _median_of(values: list[float | None]) -> float | None:
    """Compute median, filtering out None values."""
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(median(clean), 2)


# ---------------------------------------------------------------------------
# Annual aggregation from quarterly data
# ---------------------------------------------------------------------------

def compute_annual_from_quarters(
    income_rows: list[dict],
    bs_rows: list[dict],
    cf_rows: list[dict],
) -> list[dict]:
    """
    Group quarterly data by fiscal year and compute annual values.

    Flow items (income statement, cash flow): sum of Q1-Q4.
    Point-in-time items (balance sheet): use the latest quarter in the fiscal year (Q4).

    Returns a list of dicts, one per fiscal year, sorted ascending.
    """
    # Group by fiscal year
    income_by_fy: dict[int, list[dict]] = {}
    for row in income_rows:
        fy = row.get("fiscal_year")
        if fy:
            income_by_fy.setdefault(int(fy), []).append(row)

    bs_by_fy: dict[int, list[dict]] = {}
    for row in bs_rows:
        fy = row.get("fiscal_year")
        if fy:
            bs_by_fy.setdefault(int(fy), []).append(row)

    cf_by_fy: dict[int, list[dict]] = {}
    for row in cf_rows:
        fy = row.get("fiscal_year")
        if fy:
            cf_by_fy.setdefault(int(fy), []).append(row)

    all_years = sorted(set(income_by_fy.keys()) | set(bs_by_fy.keys()) | set(cf_by_fy.keys()))

    annuals = []
    for fy in all_years:
        inc_quarters = income_by_fy.get(fy, [])
        bs_quarters = bs_by_fy.get(fy, [])
        cf_quarters = cf_by_fy.get(fy, [])

        # Only include years with all 4 quarters (exclude incomplete fiscal years)
        if len(inc_quarters) < 4:
            continue

        annual: dict[str, Any] = {"fiscal_year": fy, "quarters_count": len(inc_quarters)}

        # Sum flow items from income statement
        for col in ["revenue", "cost_of_revenue", "gross_profit", "operating_income",
                     "income_before_tax", "income_tax_expense", "net_income", "ebitda",
                     "interest_expense"]:
            vals = [_safe_float(q.get(col)) for q in inc_quarters]
            clean = [v for v in vals if v is not None]
            annual[col] = sum(clean) if clean else None

        # EPS: sum of quarterly EPS
        eps_vals = [_safe_float(q.get("eps_diluted")) for q in inc_quarters]
        eps_clean = [v for v in eps_vals if v is not None]
        annual["eps_diluted"] = round(sum(eps_clean), 4) if eps_clean else None

        # Shares: use latest quarter's share count
        shares_q = [q for q in inc_quarters if q.get("weighted_avg_shares_diluted")]
        if shares_q:
            shares_q.sort(key=lambda x: x.get("period_end_date", ""))
            annual["weighted_avg_shares_diluted"] = shares_q[-1].get("weighted_avg_shares_diluted")

        # Balance sheet: use latest quarter (Q4 or latest available)
        if bs_quarters:
            bs_quarters.sort(key=lambda x: x.get("period_end_date", ""))
            latest_bs = bs_quarters[-1]
            for col in ["total_assets", "total_liabilities", "total_equity",
                         "cash_and_equivalents", "short_term_investments",
                         "total_current_assets", "total_current_liabilities",
                         "long_term_debt", "short_term_debt", "goodwill", "intangible_assets"]:
                annual[col] = latest_bs.get(col)

        # Sum flow items from cash flow
        for col in ["net_cash_operating", "capex", "free_cash_flow",
                     "dividends_paid", "common_stock_repurchased", "depreciation_amortization"]:
            vals = [_safe_float(q.get(col)) for q in cf_quarters]
            clean = [v for v in vals if v is not None]
            annual[col] = sum(clean) if clean else None

        annuals.append(annual)

    return annuals


# ---------------------------------------------------------------------------
# TTM computation
# ---------------------------------------------------------------------------

def compute_ttm(
    income_rows: list[dict],
    bs_rows: list[dict],
    cf_rows: list[dict],
) -> dict:
    """
    Compute trailing twelve months from the most recent 4 quarters.

    Flow items: sum of last 4 quarters.
    Balance sheet: latest quarter's values.
    """
    # Sort by period_end_date descending, take latest 4
    def _sort_key(r):
        return r.get("period_end_date", "")

    inc_sorted = sorted(income_rows, key=_sort_key, reverse=True)[:4]
    bs_sorted = sorted(bs_rows, key=_sort_key, reverse=True)
    cf_sorted = sorted(cf_rows, key=_sort_key, reverse=True)[:4]

    ttm: dict[str, Any] = {"quarters_used": len(inc_sorted)}

    # Sum flow items
    for col in ["revenue", "cost_of_revenue", "gross_profit", "operating_income",
                 "income_before_tax", "income_tax_expense", "net_income", "ebitda",
                 "interest_expense"]:
        vals = [_safe_float(q.get(col)) for q in inc_sorted]
        clean = [v for v in vals if v is not None]
        ttm[col] = sum(clean) if clean else None

    # EPS sum
    eps_vals = [_safe_float(q.get("eps_diluted")) for q in inc_sorted]
    eps_clean = [v for v in eps_vals if v is not None]
    ttm["eps_diluted"] = round(sum(eps_clean), 4) if eps_clean else None

    # Latest shares
    shares_q = [q for q in inc_sorted if q.get("weighted_avg_shares_diluted")]
    if shares_q:
        ttm["weighted_avg_shares_diluted"] = shares_q[0].get("weighted_avg_shares_diluted")

    # Balance sheet: use latest
    if bs_sorted:
        latest = bs_sorted[0]
        for col in ["total_assets", "total_liabilities", "total_equity",
                     "cash_and_equivalents", "short_term_investments",
                     "total_current_assets", "total_current_liabilities",
                     "long_term_debt", "short_term_debt"]:
            ttm[col] = latest.get(col)

    # Cash flow sum
    for col in ["net_cash_operating", "capex", "free_cash_flow",
                 "dividends_paid", "common_stock_repurchased"]:
        vals = [_safe_float(q.get(col)) for q in cf_sorted]
        clean = [v for v in vals if v is not None]
        ttm[col] = sum(clean) if clean else None

    return ttm


# ---------------------------------------------------------------------------
# Valuation ratios
# ---------------------------------------------------------------------------

def compute_valuation_ratios(ttm: dict, market_cap: float | None, ev: float | None) -> dict:
    """
    Compute current valuation ratios using live market data.

    P/E  = market_cap / ttm_net_income
    P/B  = market_cap / total_equity
    P/S  = market_cap / ttm_revenue
    EV/S = ev / ttm_revenue
    EV/EBITDA = ev / ttm_ebitda
    EV/EBIT   = ev / ttm_operating_income
    EV/Pretax = ev / ttm_income_before_tax
    EV/FCF    = ev / ttm_free_cash_flow
    """
    return {
        "pe": _round2(_safe_div(market_cap, ttm.get("net_income"))),
        "pb": _round2(_safe_div(market_cap, ttm.get("total_equity"))),
        "ps": _round2(_safe_div(market_cap, ttm.get("revenue"))),
        "ev_s": _round2(_safe_div(ev, ttm.get("revenue"))),
        "ev_ebitda": _round2(_safe_div(ev, ttm.get("ebitda"))),
        "ev_ebit": _round2(_safe_div(ev, ttm.get("operating_income"))),
        "ev_pretax": _round2(_safe_div(ev, ttm.get("income_before_tax"))),
        "ev_fcf": _round2(_safe_div(ev, ttm.get("free_cash_flow"))),
    }


# ---------------------------------------------------------------------------
# Return metrics (per-year + 10-year median)
# ---------------------------------------------------------------------------

def _compute_annual_returns(annuals: list[dict]) -> list[dict]:
    """
    Compute per-year return metrics.

    ROA  = net_income / total_assets
    ROE  = net_income / total_equity
    ROIC = NOPAT / invested_capital
        NOPAT = operating_income * (1 - effective_tax_rate)
        effective_tax_rate = income_tax_expense / income_before_tax
        invested_capital = total_equity + total_debt - cash
        total_debt = long_term_debt + short_term_debt
    """
    results = []
    for a in annuals:
        ni = _safe_float(a.get("net_income"))
        ta = _safe_float(a.get("total_assets"))
        te = _safe_float(a.get("total_equity"))
        oi = _safe_float(a.get("operating_income"))
        ibt = _safe_float(a.get("income_before_tax"))
        ite = _safe_float(a.get("income_tax_expense"))
        ltd = _safe_float(a.get("long_term_debt")) or 0.0
        std = _safe_float(a.get("short_term_debt")) or 0.0
        cash = _safe_float(a.get("cash_and_equivalents")) or 0.0

        roa = _safe_div(ni, ta)
        roe = _safe_div(ni, te)

        # ROIC
        if oi is not None and ibt and ite is not None:
            tax_rate = _safe_div(ite, ibt)
            if tax_rate is not None:
                tax_rate = max(0, min(tax_rate, 1))  # clamp 0-100%
                nopat = oi * (1 - tax_rate)
            else:
                nopat = None
        else:
            nopat = None

        total_debt = ltd + std
        invested_capital = (te or 0) + total_debt - cash if te is not None else None

        roic = _safe_div(nopat, invested_capital)

        results.append({
            "fiscal_year": a["fiscal_year"],
            "roa": _pct(roa),
            "roe": _pct(roe),
            "roic": _pct(roic),
        })

    return results


# ---------------------------------------------------------------------------
# Margin metrics
# ---------------------------------------------------------------------------

def _compute_annual_margins(annuals: list[dict]) -> list[dict]:
    """
    Compute per-year margin metrics.

    Gross margin     = gross_profit / revenue
    Operating margin = operating_income / revenue
    Pre-tax margin   = income_before_tax / revenue
    FCF margin       = free_cash_flow / revenue
    """
    results = []
    for a in annuals:
        rev = _safe_float(a.get("revenue"))
        results.append({
            "fiscal_year": a["fiscal_year"],
            "gross_margin": _pct(_safe_div(a.get("gross_profit"), rev)),
            "operating_margin": _pct(_safe_div(a.get("operating_income"), rev)),
            "pretax_margin": _pct(_safe_div(a.get("income_before_tax"), rev)),
            "fcf_margin": _pct(_safe_div(a.get("free_cash_flow"), rev)),
        })
    return results


# ---------------------------------------------------------------------------
# 10-Year CAGR
# ---------------------------------------------------------------------------

def _compute_cagr(values: list[tuple[int, float | None]], years: int = 10) -> float | None:
    """
    Compute CAGR over the given number of years.

    CAGR = (end / start) ^ (1/years) - 1

    Uses the earliest and latest values within the window.
    """
    clean = [(y, v) for y, v in values if v is not None and v > 0]
    if len(clean) < 2:
        return None

    clean.sort(key=lambda x: x[0])
    start_year, start_val = clean[0]
    end_year, end_val = clean[-1]

    actual_years = end_year - start_year
    if actual_years <= 0 or start_val <= 0:
        return None

    return _pct(((end_val / start_val) ** (1.0 / actual_years)) - 1)


def compute_10yr_cagr(annuals: list[dict]) -> dict:
    """
    Compute 10-year CAGR for Revenue, Assets, EPS.

    Uses the most recent 10 (or fewer) annual data points.
    """
    recent = annuals[-11:] if len(annuals) >= 11 else annuals  # last 11 gives 10 year span

    rev_pairs = [(a["fiscal_year"], _safe_float(a.get("revenue"))) for a in recent]
    asset_pairs = [(a["fiscal_year"], _safe_float(a.get("total_assets"))) for a in recent]
    eps_pairs = [(a["fiscal_year"], _safe_float(a.get("eps_diluted"))) for a in recent]

    return {
        "revenue_cagr": _compute_cagr(rev_pairs),
        "assets_cagr": _compute_cagr(asset_pairs),
        "eps_cagr": _compute_cagr(eps_pairs),
    }


# ---------------------------------------------------------------------------
# Capital structure (10-year median)
# ---------------------------------------------------------------------------

def compute_capital_structure(annuals: list[dict]) -> dict:
    """
    Compute 10-year median capital structure ratios.

    Assets / Equity
    Debt / Equity  = (long_term_debt + short_term_debt) / total_equity
    Debt / Assets  = (long_term_debt + short_term_debt) / total_assets
    """
    recent = annuals[-10:] if len(annuals) >= 10 else annuals

    ae_vals, de_vals, da_vals = [], [], []
    for a in recent:
        ta = _safe_float(a.get("total_assets"))
        te = _safe_float(a.get("total_equity"))
        ltd = _safe_float(a.get("long_term_debt")) or 0
        std = _safe_float(a.get("short_term_debt")) or 0
        total_debt = ltd + std

        ae_vals.append(_safe_div(ta, te))
        de_vals.append(_safe_div(total_debt, te))
        da_vals.append(_safe_div(total_debt, ta))

    return {
        "assets_to_equity": _round2(_median_of(ae_vals)),
        "debt_to_equity": _round2(_median_of(de_vals)),
        "debt_to_assets": _round2(_median_of(da_vals)),
    }


# ---------------------------------------------------------------------------
# Growth rates
# ---------------------------------------------------------------------------

def _compute_yoy_growth(annuals: list[dict], field: str) -> list[dict]:
    """Compute year-over-year growth for a field across annual data."""
    results = []
    for i, a in enumerate(annuals):
        growth = None
        if i > 0:
            prev = _safe_float(annuals[i - 1].get(field))
            curr = _safe_float(a.get(field))
            if prev and curr is not None and prev != 0:
                growth = _pct((curr - prev) / abs(prev))
        results.append({"fiscal_year": a["fiscal_year"], f"{field}_growth": growth})
    return results


# ---------------------------------------------------------------------------
# Annual table data
# ---------------------------------------------------------------------------

def build_annual_table(annuals: list[dict]) -> list[dict]:
    """
    Build the annual table rows combining raw data + computed metrics.

    Each row has: fiscal_year, revenue, revenue_growth, gross_profit,
    gross_margin, operating_profit, operating_margin, eps, eps_growth,
    roa, roe, roic  (all in display-ready format).
    """
    returns = _compute_annual_returns(annuals)
    margins = _compute_annual_margins(annuals)
    rev_growth = _compute_yoy_growth(annuals, "revenue")
    eps_growth = _compute_yoy_growth(annuals, "eps_diluted")

    rows = []
    for i, a in enumerate(annuals):
        fy = a["fiscal_year"]
        ret = returns[i] if i < len(returns) else {}
        mar = margins[i] if i < len(margins) else {}
        rg = rev_growth[i] if i < len(rev_growth) else {}
        eg = eps_growth[i] if i < len(eps_growth) else {}

        rows.append({
            "fiscal_year": fy,
            "revenue": a.get("revenue"),
            "revenue_growth": rg.get("revenue_growth"),
            "gross_profit": a.get("gross_profit"),
            "gross_margin": mar.get("gross_margin"),
            "operating_profit": a.get("operating_income"),
            "operating_margin": mar.get("operating_margin"),
            "eps": a.get("eps_diluted"),
            "eps_growth": eg.get("eps_diluted_growth"),
            "roa": ret.get("roa"),
            "roe": ret.get("roe"),
            "roic": ret.get("roic"),
        })

    return rows


# ---------------------------------------------------------------------------
# 10-year median returns and margins
# ---------------------------------------------------------------------------

def compute_10yr_median_returns(annuals: list[dict]) -> dict:
    """10-year median ROA, ROE, ROIC."""
    returns = _compute_annual_returns(annuals[-10:] if len(annuals) >= 10 else annuals)
    return {
        "roa": _median_of([r["roa"] for r in returns]),
        "roe": _median_of([r["roe"] for r in returns]),
        "roic": _median_of([r["roic"] for r in returns]),
    }


def compute_10yr_median_margins(annuals: list[dict]) -> dict:
    """10-year median gross, operating, pre-tax, FCF margins."""
    margins = _compute_annual_margins(annuals[-10:] if len(annuals) >= 10 else annuals)
    return {
        "gross_margin": _median_of([m["gross_margin"] for m in margins]),
        "operating_margin": _median_of([m["operating_margin"] for m in margins]),
        "pretax_margin": _median_of([m["pretax_margin"] for m in margins]),
        "fcf_margin": _median_of([m["fcf_margin"] for m in margins]),
    }


# ---------------------------------------------------------------------------
# ROIC chart data
# ---------------------------------------------------------------------------

def build_roic_chart(annuals: list[dict]) -> list[dict]:
    """Build ROIC chart data points (fiscal_year, roic)."""
    returns = _compute_annual_returns(annuals)
    return [{"year": r["fiscal_year"], "roic": r["roic"]} for r in returns]


def build_ttm_row(ttm: dict, last_annual: dict | None = None) -> dict:
    """
    Build a TTM row in the same shape as an annual table row.

    The TTM row uses fiscal_year=0 as a sentinel (frontend displays "TTM" instead).
    Growth rates compare TTM to the last complete fiscal year.
    """
    rev = _safe_float(ttm.get("revenue"))
    ni = _safe_float(ttm.get("net_income"))
    ta = _safe_float(ttm.get("total_assets"))
    te = _safe_float(ttm.get("total_equity"))
    oi = _safe_float(ttm.get("operating_income"))
    ibt = _safe_float(ttm.get("income_before_tax"))
    ite = _safe_float(ttm.get("income_tax_expense"))
    ltd = _safe_float(ttm.get("long_term_debt")) or 0
    std = _safe_float(ttm.get("short_term_debt")) or 0
    cash = _safe_float(ttm.get("cash_and_equivalents")) or 0
    fcf = _safe_float(ttm.get("free_cash_flow"))

    roa = _safe_div(ni, ta)
    roe = _safe_div(ni, te)

    # ROIC
    nopat = None
    if oi is not None and ibt and ite is not None:
        tax_rate = _safe_div(ite, ibt)
        if tax_rate is not None:
            tax_rate = max(0, min(tax_rate, 1))
            nopat = oi * (1 - tax_rate)
    total_debt = ltd + std
    invested_capital = (te or 0) + total_debt - cash if te is not None else None
    roic = _safe_div(nopat, invested_capital)

    # Growth vs last complete fiscal year
    rev_growth = None
    eps_growth = None
    if last_annual:
        prev_rev = _safe_float(last_annual.get("revenue"))
        if prev_rev and rev and prev_rev != 0:
            rev_growth = _pct((rev - prev_rev) / abs(prev_rev))
        prev_eps = _safe_float(last_annual.get("eps_diluted"))
        ttm_eps = _safe_float(ttm.get("eps_diluted"))
        if prev_eps and ttm_eps is not None and prev_eps != 0:
            eps_growth = _pct((ttm_eps - prev_eps) / abs(prev_eps))

    return {
        "fiscal_year": 0,  # sentinel for TTM
        "revenue": rev,
        "revenue_growth": rev_growth,
        "gross_profit": _safe_float(ttm.get("gross_profit")),
        "gross_margin": _pct(_safe_div(ttm.get("gross_profit"), rev)),
        "operating_profit": oi,
        "operating_margin": _pct(_safe_div(oi, rev)),
        "eps": _safe_float(ttm.get("eps_diluted")),
        "eps_growth": eps_growth,
        "roa": _pct(roa),
        "roe": _pct(roe),
        "roic": _pct(roic),
    }


# ---------------------------------------------------------------------------
# Master: compute all metrics for a symbol
# ---------------------------------------------------------------------------

def compute_all_metrics(
    income_rows: list[dict],
    bs_rows: list[dict],
    cf_rows: list[dict],
    market_cap: float | None = None,
    ev: float | None = None,
    last_close: float | None = None,  # noqa: ARG001 - reserved for future use
) -> dict:
    """
    Compute all metrics for a symbol page.

    Returns a dict with all sections:
    - valuation_ratios
    - median_returns (10yr)
    - median_margins (10yr)
    - cagr_10yr
    - capital_structure
    - annual_table
    - roic_chart
    - ttm (raw TTM values)
    """
    annuals = compute_annual_from_quarters(income_rows, bs_rows, cf_rows)
    ttm = compute_ttm(income_rows, bs_rows, cf_rows)

    annual_table = build_annual_table(annuals)

    # Append TTM as the rightmost column
    last_annual = annuals[-1] if annuals else None
    ttm_row = build_ttm_row(ttm, last_annual)
    annual_table.append(ttm_row)

    return {
        "valuation_ratios": compute_valuation_ratios(ttm, market_cap, ev),
        "median_returns": compute_10yr_median_returns(annuals),
        "median_margins": compute_10yr_median_margins(annuals),
        "cagr_10yr": compute_10yr_cagr(annuals),
        "capital_structure": compute_capital_structure(annuals),
        "annual_table": annual_table,
        "roic_chart": build_roic_chart(annuals),
        "ttm": ttm,
    }
