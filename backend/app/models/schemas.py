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
    roic_chart: list[ROICPoint]


class SearchResult(BaseModel):
    symbol: str
    name: str | None = None
    exchange: str | None = None
