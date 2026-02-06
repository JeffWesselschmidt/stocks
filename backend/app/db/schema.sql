-- Symbol Page MVP: Database Schema
-- All tables use ON CONFLICT for safe concurrent access.

-- =====================================================
-- SYMBOLS (Universe of NYSE/NASDAQ tickers)
-- =====================================================
CREATE TABLE IF NOT EXISTS symbols (
    symbol VARCHAR(20) PRIMARY KEY,
    name VARCHAR(255),
    exchange VARCHAR(20),
    type VARCHAR(20) DEFAULT 'stock',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_symbols_exchange ON symbols(exchange);
CREATE INDEX IF NOT EXISTS idx_symbols_active ON symbols(is_active);

-- =====================================================
-- COMPANIES (Profile data from FMP)
-- =====================================================
CREATE TABLE IF NOT EXISTS companies (
    symbol VARCHAR(20) PRIMARY KEY,
    name VARCHAR(255),
    exchange VARCHAR(20),
    sector VARCHAR(100),
    industry VARCHAR(200),
    currency VARCHAR(10) DEFAULT 'USD',
    description TEXT,
    market_cap BIGINT,
    last_updated TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_companies_sector ON companies(sector);
CREATE INDEX IF NOT EXISTS idx_companies_industry ON companies(industry);

-- =====================================================
-- QUARTERLY INCOME STATEMENTS
-- =====================================================
CREATE TABLE IF NOT EXISTS quarterly_income (
    symbol VARCHAR(20) NOT NULL,
    period_end_date DATE NOT NULL,
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    filing_date DATE,
    revenue BIGINT,
    cost_of_revenue BIGINT,
    gross_profit BIGINT,
    operating_income BIGINT,
    income_before_tax BIGINT,
    income_tax_expense BIGINT,
    net_income BIGINT,
    eps_basic NUMERIC(12,4),
    eps_diluted NUMERIC(12,4),
    weighted_avg_shares_diluted BIGINT,
    ebitda BIGINT,
    interest_expense BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (symbol, period_end_date)
);

CREATE INDEX IF NOT EXISTS idx_qi_symbol ON quarterly_income(symbol);
CREATE INDEX IF NOT EXISTS idx_qi_fiscal_year ON quarterly_income(symbol, fiscal_year);

-- =====================================================
-- QUARTERLY BALANCE SHEETS
-- =====================================================
CREATE TABLE IF NOT EXISTS quarterly_balance_sheet (
    symbol VARCHAR(20) NOT NULL,
    period_end_date DATE NOT NULL,
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    filing_date DATE,
    total_assets BIGINT,
    total_liabilities BIGINT,
    total_equity BIGINT,
    cash_and_equivalents BIGINT,
    short_term_investments BIGINT,
    total_current_assets BIGINT,
    total_current_liabilities BIGINT,
    long_term_debt BIGINT,
    short_term_debt BIGINT,
    goodwill BIGINT,
    intangible_assets BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (symbol, period_end_date)
);

CREATE INDEX IF NOT EXISTS idx_qbs_symbol ON quarterly_balance_sheet(symbol);
CREATE INDEX IF NOT EXISTS idx_qbs_fiscal_year ON quarterly_balance_sheet(symbol, fiscal_year);

-- =====================================================
-- QUARTERLY CASH FLOW STATEMENTS
-- =====================================================
CREATE TABLE IF NOT EXISTS quarterly_cash_flow (
    symbol VARCHAR(20) NOT NULL,
    period_end_date DATE NOT NULL,
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    filing_date DATE,
    net_cash_operating BIGINT,
    capex BIGINT,
    free_cash_flow BIGINT,
    dividends_paid BIGINT,
    common_stock_repurchased BIGINT,
    depreciation_amortization BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (symbol, period_end_date)
);

CREATE INDEX IF NOT EXISTS idx_qcf_symbol ON quarterly_cash_flow(symbol);
CREATE INDEX IF NOT EXISTS idx_qcf_fiscal_year ON quarterly_cash_flow(symbol, fiscal_year);

-- =====================================================
-- INGESTION STATE (for resumable bulk jobs)
-- =====================================================
CREATE TABLE IF NOT EXISTS ingestion_state (
    symbol VARCHAR(20) NOT NULL,
    job_type VARCHAR(30) NOT NULL,  -- 'fundamentals', 'profile'
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending', 'complete', 'error'
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    error_message TEXT,

    PRIMARY KEY (symbol, job_type)
);

CREATE INDEX IF NOT EXISTS idx_ingestion_status ON ingestion_state(job_type, status);
