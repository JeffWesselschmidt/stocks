export interface CompanyInfo {
  symbol: string;
  name: string | null;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  currency: string | null;
  description: string | null;
  rating: 'good' | 'bad' | null;
  note: string | null;
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

export interface QuarterlyRow {
  label: string;
  fiscal_year: number;
  fiscal_quarter: number;
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
  quarterly_table: QuarterlyRow[];
  roic_chart: ROICPoint[];
}

export interface SearchResult {
  symbol: string;
  name: string | null;
  exchange: string | null;
}

// ---------------------------------------------------------------------------
// Screener
// ---------------------------------------------------------------------------

export interface ScreenerRow {
  symbol: string;
  name: string | null;
  rating: 'good' | 'bad' | null;
  note: string | null;
  sector: string | null;
  industry: string | null;
  years_of_data: number | null;

  // Returns (10yr medians, %)
  median_roa: number | null;
  median_roe: number | null;
  median_roic: number | null;

  // Profitability
  profit_pct: number | null;
  pct_gm_yoy_positive: number | null;

  // Margins (10yr medians, %)
  median_gross_margin: number | null;
  median_operating_margin: number | null;
  median_net_margin: number | null;
  median_fcf_margin: number | null;

  // Growth — median YoY (%)
  median_revenue_growth: number | null;
  median_ni_growth: number | null;
  median_eps_growth: number | null;
  median_ocf_growth: number | null;
  median_fcf_growth: number | null;
  pct_eps_yoy_positive: number | null;

  // Growth — CAGR (%)
  revenue_cagr: number | null;
  eps_cagr: number | null;
  ocf_cagr: number | null;
  fcf_cagr: number | null;

  // Debt
  latest_long_term_debt: number | null;
  median_debt_to_equity: number | null;

  // Liquidity
  latest_current_ratio: number | null;
}

export interface ScreenerResponse {
  results: ScreenerRow[];
  total: number;
}

export interface ScreenerFilters {
  [key: string]: string | undefined;
}

// ---------------------------------------------------------------------------
// Saved Screens
// ---------------------------------------------------------------------------

export interface SavedScreen {
  id: number;
  name: string;
  filters: Record<string, string>;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Tournament
// ---------------------------------------------------------------------------

export interface TournamentStartResponse {
  tournament_id: number;
  status: string;
  total_stocks: number;
  bracket_size: number;
  total_rounds: number;
}

export interface TournamentMatchSide {
  side: 'A' | 'B';
  stats: Record<string, number | null>;
  annual_table: AnnualRow[];
}

export interface TournamentMatch {
  match_id: number;
  round: number;
  match_index: number;
  side_a: TournamentMatchSide;
  side_b: TournamentMatchSide;
}

export interface TournamentCurrentResponse {
  tournament_id: number;
  status: string;
  total_stocks: number;
  bracket_size: number;
  total_rounds: number;
  decided_matches: number;
  total_matches: number;
  next_match: TournamentMatch | null;
}

export interface TournamentResultRow {
  symbol: string;
  name: string | null;
  rank: number;
  seed_rank: number;
  seed_score: number;
}

export interface TournamentResultsResponse {
  tournament_id: number;
  status: string;
  results: TournamentResultRow[];
}
