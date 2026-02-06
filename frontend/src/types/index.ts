export interface CompanyInfo {
  symbol: string;
  name: string | null;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  currency: string | null;
  description: string | null;
}

export interface MarketData {
  last_close: number | null;
  market_cap: number | null;
  ev: number | null;
  shares_outstanding: number | null;
  price_change_pct: number | null;
}

export interface ValuationRatios {
  pe: number | null;
  pb: number | null;
  ps: number | null;
  ev_s: number | null;
  ev_ebitda: number | null;
  ev_ebit: number | null;
  ev_pretax: number | null;
  ev_fcf: number | null;
}

export interface MedianReturns {
  roa: number | null;
  roe: number | null;
  roic: number | null;
}

export interface MedianMargins {
  gross_margin: number | null;
  operating_margin: number | null;
  pretax_margin: number | null;
  fcf_margin: number | null;
}

export interface CAGR10yr {
  revenue_cagr: number | null;
  assets_cagr: number | null;
  eps_cagr: number | null;
}

export interface CapitalStructure {
  assets_to_equity: number | null;
  debt_to_equity: number | null;
  debt_to_assets: number | null;
}

export interface KeyStatistics {
  valuation_ratios: ValuationRatios;
  median_returns: MedianReturns;
  median_margins: MedianMargins;
  cagr_10yr: CAGR10yr;
  capital_structure: CapitalStructure;
}

export interface AnnualRow {
  fiscal_year: number;
  revenue: number | null;
  revenue_growth: number | null;
  gross_profit: number | null;
  gross_margin: number | null;
  operating_profit: number | null;
  operating_margin: number | null;
  eps: number | null;
  eps_growth: number | null;
  roa: number | null;
  roe: number | null;
  roic: number | null;
}

export interface ROICPoint {
  year: number;
  roic: number | null;
}

export interface SymbolPageData {
  company: CompanyInfo;
  market_data: MarketData;
  key_statistics: KeyStatistics;
  annual_table: AnnualRow[];
  roic_chart: ROICPoint[];
}

export interface SearchResult {
  symbol: string;
  name: string | null;
  exchange: string | null;
}
