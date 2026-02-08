"""Pydantic response models for the API."""

from pydantic import BaseModel


class CompanyInfo(BaseModel):
    symbol: str
    name: str | None = None
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    currency: str | None = "USD"
    description: str | None = None


class MarketData(BaseModel):
    last_close: float | None = None
    market_cap: float | None = None
    ev: float | None = None
    shares_outstanding: float | None = None
    price_change_pct: float | None = None


class ValuationRatios(BaseModel):
    pe: float | None = None
    pb: float | None = None
    ps: float | None = None
    ev_s: float | None = None
    ev_ebitda: float | None = None
    ev_ebit: float | None = None
    ev_pretax: float | None = None
    ev_fcf: float | None = None


class MedianReturns(BaseModel):
    roa: float | None = None
    roe: float | None = None
    roic: float | None = None


class MedianMargins(BaseModel):
    gross_margin: float | None = None
    operating_margin: float | None = None
    pretax_margin: float | None = None
    fcf_margin: float | None = None


class CAGR10yr(BaseModel):
    revenue_cagr: float | None = None
    assets_cagr: float | None = None
    eps_cagr: float | None = None


class CapitalStructure(BaseModel):
    assets_to_equity: float | None = None
    debt_to_equity: float | None = None
    debt_to_assets: float | None = None


class AnnualRow(BaseModel):
    fiscal_year: int
    revenue: float | None = None
    revenue_growth: float | None = None
    gross_profit: float | None = None
    gross_margin: float | None = None
    operating_profit: float | None = None
    operating_margin: float | None = None
    eps: float | None = None
    eps_growth: float | None = None
    roa: float | None = None
    roe: float | None = None
    roic: float | None = None


class QuarterlyRow(BaseModel):
    label: str  # e.g. "Q1'24"
    fiscal_year: int
    fiscal_quarter: int
    revenue: float | None = None
    revenue_growth: float | None = None
    gross_profit: float | None = None
    gross_margin: float | None = None
    operating_profit: float | None = None
    operating_margin: float | None = None
    eps: float | None = None
    eps_growth: float | None = None
    roa: float | None = None
    roe: float | None = None
    roic: float | None = None


class ROICPoint(BaseModel):
    year: int
    roic: float | None = None


class KeyStatistics(BaseModel):
    valuation_ratios: ValuationRatios
    median_returns: MedianReturns
    median_margins: MedianMargins
    cagr_10yr: CAGR10yr
    capital_structure: CapitalStructure


class SymbolPageResponse(BaseModel):
    company: CompanyInfo
    market_data: MarketData
    key_statistics: KeyStatistics
    annual_table: list[AnnualRow]
    quarterly_table: list[QuarterlyRow]
    roic_chart: list[ROICPoint]


class SearchResult(BaseModel):
    symbol: str
    name: str | None = None
    exchange: str | None = None


# ---------------------------------------------------------------------------
# Screener
# ---------------------------------------------------------------------------

class ScreenerRow(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    years_of_data: int | None = None

    # Returns (10yr medians, %)
    median_roa: float | None = None
    median_roe: float | None = None
    median_roic: float | None = None

    # Profitability
    profit_pct: float | None = None

    # Margins (10yr medians, %)
    median_gross_margin: float | None = None
    median_operating_margin: float | None = None
    median_net_margin: float | None = None
    median_fcf_margin: float | None = None

    # Growth — median YoY (%)
    median_revenue_growth: float | None = None
    median_ni_growth: float | None = None
    median_eps_growth: float | None = None
    median_ocf_growth: float | None = None
    median_fcf_growth: float | None = None

    # Growth — CAGR (%)
    revenue_cagr: float | None = None
    eps_cagr: float | None = None
    ocf_cagr: float | None = None
    fcf_cagr: float | None = None

    # Debt
    latest_long_term_debt: float | None = None
    median_debt_to_equity: float | None = None

    # Liquidity
    latest_current_ratio: float | None = None


class ScreenerResponse(BaseModel):
    results: list[ScreenerRow]
    total: int


# ---------------------------------------------------------------------------
# Saved Screens
# ---------------------------------------------------------------------------

class SavedScreenCreate(BaseModel):
    name: str
    filters: dict[str, str]


class SavedScreen(BaseModel):
    id: int
    name: str
    filters: dict[str, str]
    created_at: str
