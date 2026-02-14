-- =============================================================
-- Screener Materialized View
-- Pre-computes 10-year fundamental screening metrics per symbol.
--
-- Drops and recreates on every migration so definition stays
-- current.  Populate / refresh with:
--   REFRESH MATERIALIZED VIEW CONCURRENTLY screener_metrics;
-- =============================================================

DROP MATERIALIZED VIEW IF EXISTS screener_metrics;

CREATE MATERIALIZED VIEW screener_metrics AS

WITH

-- =============================================================
-- Step 0: Only include symbols that are still actively filing.
-- A symbol whose most recent quarterly income is older than
-- 2 years is considered delisted / acquired and excluded.
-- =============================================================

active_symbols AS (
  SELECT symbol
  FROM quarterly_income
  WHERE symbol NOT LIKE '%-%'          -- exclude preferred / warrants / units
  GROUP BY symbol
  HAVING MAX(period_end_date) >= CURRENT_DATE - INTERVAL '2 years'
),

-- =============================================================
-- Step 1: Annual aggregation from quarterly data (10yr window)
-- Only includes fiscal years with all 4 quarters reported.
-- =============================================================

annual_income AS (
  SELECT
    qi.symbol,
    qi.fiscal_year,
    SUM(qi.revenue) AS revenue,
    SUM(qi.gross_profit) AS gross_profit,
    SUM(qi.operating_income) AS operating_income,
    SUM(qi.income_before_tax) AS income_before_tax,
    SUM(qi.income_tax_expense) AS income_tax_expense,
    SUM(qi.net_income) AS net_income,
    SUM(qi.eps_diluted) AS eps_diluted
  FROM quarterly_income qi
  INNER JOIN active_symbols a ON qi.symbol = a.symbol
  WHERE qi.fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 10
  GROUP BY qi.symbol, qi.fiscal_year
  HAVING COUNT(*) = 4
),

-- Latest-quarter balance sheet per fiscal year (Q4 proxy via DISTINCT ON)
annual_bs AS (
  SELECT DISTINCT ON (qbs.symbol, qbs.fiscal_year)
    qbs.symbol,
    qbs.fiscal_year,
    qbs.total_assets,
    qbs.total_equity,
    qbs.cash_and_equivalents,
    qbs.long_term_debt,
    qbs.short_term_debt,
    qbs.total_current_assets,
    qbs.total_current_liabilities
  FROM quarterly_balance_sheet qbs
  INNER JOIN active_symbols a ON qbs.symbol = a.symbol
  WHERE qbs.fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 10
  ORDER BY qbs.symbol, qbs.fiscal_year, qbs.period_end_date DESC
),

-- Annual cash flow (sum of quarters, only complete years)
annual_cf AS (
  SELECT
    qcf.symbol,
    qcf.fiscal_year,
    SUM(qcf.net_cash_operating) AS net_cash_operating,
    SUM(qcf.free_cash_flow) AS free_cash_flow
  FROM quarterly_cash_flow qcf
  INNER JOIN active_symbols a ON qcf.symbol = a.symbol
  WHERE qcf.fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 10
  GROUP BY qcf.symbol, qcf.fiscal_year
  HAVING COUNT(*) = 4
),

-- =============================================================
-- Step 2: Per-year derived metrics (returns, margins, leverage)
-- =============================================================

annual_metrics AS (
  SELECT
    ai.symbol,
    ai.fiscal_year,
    ai.revenue,
    ai.net_income,
    ai.eps_diluted,
    acf.net_cash_operating,
    acf.free_cash_flow,

    -- ROA = net_income / total_assets  (%)
    CASE WHEN NULLIF(ab.total_assets, 0) IS NOT NULL
      THEN ai.net_income::numeric / ab.total_assets * 100
    END AS roa,

    -- ROE = net_income / total_equity  (%)
    CASE WHEN NULLIF(ab.total_equity, 0) IS NOT NULL
      THEN ai.net_income::numeric / ab.total_equity * 100
    END AS roe,

    -- ROIC = NOPAT / invested_capital  (%)
    --   NOPAT = operating_income * (1 - effective_tax_rate)
    --   effective_tax_rate = tax_expense / income_before_tax  clamped [0, 1]
    --   invested_capital  = equity + LTD + STD - cash
    CASE
      WHEN ai.operating_income IS NOT NULL
        AND NULLIF(ai.income_before_tax, 0) IS NOT NULL
        AND NULLIF(
              ab.total_equity
                + COALESCE(ab.long_term_debt, 0)
                + COALESCE(ab.short_term_debt, 0)
                - COALESCE(ab.cash_and_equivalents, 0),
              0) IS NOT NULL
      THEN (
        ai.operating_income::numeric
        * (1.0 - GREATEST(0, LEAST(1,
            ai.income_tax_expense::numeric / ai.income_before_tax
          )))
      ) / (
        ab.total_equity
          + COALESCE(ab.long_term_debt, 0)
          + COALESCE(ab.short_term_debt, 0)
          - COALESCE(ab.cash_and_equivalents, 0)
      ) * 100
    END AS roic,

    -- Gross margin (%)
    CASE WHEN NULLIF(ai.revenue, 0) IS NOT NULL
      THEN ai.gross_profit::numeric / ai.revenue * 100
    END AS gross_margin,

    -- Operating margin (%)
    CASE WHEN NULLIF(ai.revenue, 0) IS NOT NULL
      THEN ai.operating_income::numeric / ai.revenue * 100
    END AS operating_margin,

    -- Net margin (%)
    CASE WHEN NULLIF(ai.revenue, 0) IS NOT NULL
      THEN ai.net_income::numeric / ai.revenue * 100
    END AS net_margin,

    -- FCF margin (%)
    CASE WHEN NULLIF(ai.revenue, 0) IS NOT NULL AND acf.free_cash_flow IS NOT NULL
      THEN acf.free_cash_flow::numeric / ai.revenue * 100
    END AS fcf_margin,

    -- Debt / Equity ratio
    CASE WHEN NULLIF(ab.total_equity, 0) IS NOT NULL
      THEN (COALESCE(ab.long_term_debt, 0) + COALESCE(ab.short_term_debt, 0))::numeric
           / ab.total_equity
    END AS debt_to_equity

  FROM annual_income ai
  LEFT JOIN annual_bs ab   ON ai.symbol = ab.symbol AND ai.fiscal_year = ab.fiscal_year
  LEFT JOIN annual_cf acf  ON ai.symbol = acf.symbol AND ai.fiscal_year = acf.fiscal_year
),

-- =============================================================
-- Step 3: Year-over-year growth rates via LAG()
-- =============================================================

annual_growth AS (
  SELECT
    am.symbol,
    am.fiscal_year,

    CASE WHEN LAG(am.revenue) OVER w IS NOT NULL
          AND LAG(am.revenue) OVER w != 0
          AND am.revenue IS NOT NULL
      THEN (am.revenue - LAG(am.revenue) OVER w)::numeric
           / ABS(LAG(am.revenue) OVER w) * 100
    END AS revenue_growth,

    CASE WHEN LAG(am.net_income) OVER w IS NOT NULL
          AND LAG(am.net_income) OVER w != 0
          AND am.net_income IS NOT NULL
      THEN (am.net_income - LAG(am.net_income) OVER w)::numeric
           / ABS(LAG(am.net_income) OVER w) * 100
    END AS ni_growth,

    CASE WHEN LAG(am.eps_diluted) OVER w IS NOT NULL
          AND LAG(am.eps_diluted) OVER w != 0
          AND am.eps_diluted IS NOT NULL
      THEN (am.eps_diluted - LAG(am.eps_diluted) OVER w)::numeric
           / ABS(LAG(am.eps_diluted) OVER w) * 100
    END AS eps_growth,

    CASE WHEN LAG(am.net_cash_operating) OVER w IS NOT NULL
          AND LAG(am.net_cash_operating) OVER w != 0
          AND am.net_cash_operating IS NOT NULL
      THEN (am.net_cash_operating - LAG(am.net_cash_operating) OVER w)::numeric
           / ABS(LAG(am.net_cash_operating) OVER w) * 100
    END AS ocf_growth,

    CASE WHEN LAG(am.free_cash_flow) OVER w IS NOT NULL
          AND LAG(am.free_cash_flow) OVER w != 0
          AND am.free_cash_flow IS NOT NULL
      THEN (am.free_cash_flow - LAG(am.free_cash_flow) OVER w)::numeric
           / ABS(LAG(am.free_cash_flow) OVER w) * 100
    END AS fcf_growth

  FROM annual_metrics am
  WINDOW w AS (PARTITION BY am.symbol ORDER BY am.fiscal_year)
),

-- =============================================================
-- Step 3b: Quarterly YoY EPS growth positivity (% of quarters)
-- =============================================================

quarterly_eps_yoy AS (
  SELECT
    qi.symbol,
    qi.period_end_date,
    qi.eps_diluted,
    LAG(qi.eps_diluted, 4) OVER w AS eps_prev_year
  FROM quarterly_income qi
  INNER JOIN active_symbols a ON qi.symbol = a.symbol
  WINDOW w AS (PARTITION BY qi.symbol ORDER BY qi.period_end_date)
),

eps_yoy_positive AS (
  SELECT
    symbol,
    ROUND(
      COUNT(*) FILTER (
        WHERE eps_diluted IS NOT NULL
          AND eps_prev_year IS NOT NULL
          AND eps_diluted > eps_prev_year
      )::numeric
      / NULLIF(COUNT(*) FILTER (
        WHERE eps_diluted IS NOT NULL
          AND eps_prev_year IS NOT NULL
      ), 0) * 100,
      2
    ) AS pct_eps_yoy_positive
  FROM quarterly_eps_yoy
  GROUP BY symbol
),

-- =============================================================
-- Step 4: CAGR inputs — first/last positive values per symbol
--   Uses DISTINCT ON for efficient first/last row selection.
-- =============================================================

rev_first  AS (SELECT DISTINCT ON (symbol) symbol, fiscal_year AS yr, revenue            AS val FROM annual_metrics WHERE revenue            > 0 ORDER BY symbol, fiscal_year),
rev_last   AS (SELECT DISTINCT ON (symbol) symbol, fiscal_year AS yr, revenue            AS val FROM annual_metrics WHERE revenue            > 0 ORDER BY symbol, fiscal_year DESC),
eps_first  AS (SELECT DISTINCT ON (symbol) symbol, fiscal_year AS yr, eps_diluted        AS val FROM annual_metrics WHERE eps_diluted        > 0 ORDER BY symbol, fiscal_year),
eps_last   AS (SELECT DISTINCT ON (symbol) symbol, fiscal_year AS yr, eps_diluted        AS val FROM annual_metrics WHERE eps_diluted        > 0 ORDER BY symbol, fiscal_year DESC),
ocf_first  AS (SELECT DISTINCT ON (symbol) symbol, fiscal_year AS yr, net_cash_operating AS val FROM annual_metrics WHERE net_cash_operating > 0 ORDER BY symbol, fiscal_year),
ocf_last   AS (SELECT DISTINCT ON (symbol) symbol, fiscal_year AS yr, net_cash_operating AS val FROM annual_metrics WHERE net_cash_operating > 0 ORDER BY symbol, fiscal_year DESC),
fcf_first  AS (SELECT DISTINCT ON (symbol) symbol, fiscal_year AS yr, free_cash_flow     AS val FROM annual_metrics WHERE free_cash_flow     > 0 ORDER BY symbol, fiscal_year),
fcf_last   AS (SELECT DISTINCT ON (symbol) symbol, fiscal_year AS yr, free_cash_flow     AS val FROM annual_metrics WHERE free_cash_flow     > 0 ORDER BY symbol, fiscal_year DESC),

-- =============================================================
-- Step 5: Latest balance sheet snapshot (most recent quarter)
-- =============================================================

latest_bs AS (
  SELECT DISTINCT ON (qbs.symbol)
    qbs.symbol,
    qbs.long_term_debt AS latest_long_term_debt,
    CASE WHEN NULLIF(qbs.total_current_liabilities, 0) IS NOT NULL
      THEN ROUND(qbs.total_current_assets::numeric / qbs.total_current_liabilities, 2)
    END AS current_ratio
  FROM quarterly_balance_sheet qbs
  INNER JOIN active_symbols a ON qbs.symbol = a.symbol
  ORDER BY qbs.symbol, qbs.period_end_date DESC
),

-- =============================================================
-- Step 6: Aggregate medians & percentages per symbol
-- =============================================================

symbol_agg AS (
  SELECT
    am.symbol,
    COUNT(DISTINCT am.fiscal_year)::int AS years_of_data,

    -- 10yr median returns (%)
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY am.roa))::numeric, 2)  AS median_roa,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY am.roe))::numeric, 2)  AS median_roe,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY am.roic))::numeric, 2) AS median_roic,

    -- Profit percentage (% of years with net_income > 0)
    ROUND(
      COUNT(*) FILTER (WHERE am.net_income > 0)::numeric
      / NULLIF(COUNT(*), 0) * 100, 2
    ) AS profit_pct,

    -- 10yr median margins (%)
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY am.gross_margin))::numeric, 2)     AS median_gross_margin,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY am.operating_margin))::numeric, 2) AS median_operating_margin,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY am.net_margin))::numeric, 2)       AS median_net_margin,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY am.fcf_margin))::numeric, 2)       AS median_fcf_margin,

    -- Median YoY growth (%)
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY ag.revenue_growth))::numeric, 2) AS median_revenue_growth,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY ag.ni_growth))::numeric, 2)      AS median_ni_growth,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY ag.eps_growth))::numeric, 2)     AS median_eps_growth,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY ag.ocf_growth))::numeric, 2)     AS median_ocf_growth,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY ag.fcf_growth))::numeric, 2)     AS median_fcf_growth,

    -- Median debt/equity
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY am.debt_to_equity))::numeric, 2) AS median_debt_to_equity

  FROM annual_metrics am
  LEFT JOIN annual_growth ag ON am.symbol = ag.symbol AND am.fiscal_year = ag.fiscal_year
  GROUP BY am.symbol
)

-- =============================================================
-- Final: assemble one row per symbol with all screening columns
-- =============================================================

SELECT DISTINCT ON (COALESCE(c.name, sa.symbol))
  sa.symbol,
  c.name,
  c.rating,
  c.note,
  c.sector,
  c.industry,
  sa.years_of_data,

  -- Returns
  sa.median_roa,
  sa.median_roe,
  sa.median_roic,

  -- Profitability
  sa.profit_pct,

  -- Margins
  sa.median_gross_margin,
  sa.median_operating_margin,
  sa.median_net_margin,
  sa.median_fcf_margin,

  -- Median YoY growth
  sa.median_revenue_growth,
  sa.median_ni_growth,
  sa.median_eps_growth,
  sa.median_ocf_growth,
  sa.median_fcf_growth,
  eyp.pct_eps_yoy_positive,

  -- CAGR  =  (end/start)^(1/years) - 1  * 100
  CASE WHEN rl.yr - rf.yr > 0
    THEN ROUND((POWER(rl.val::numeric / rf.val, 1.0 / (rl.yr - rf.yr)) - 1) * 100, 2)
  END AS revenue_cagr,

  CASE WHEN el.yr - ef.yr > 0
    THEN ROUND((POWER(el.val::numeric / ef.val, 1.0 / (el.yr - ef.yr)) - 1) * 100, 2)
  END AS eps_cagr,

  CASE WHEN ol.yr - oof.yr > 0
    THEN ROUND((POWER(ol.val::numeric / oof.val, 1.0 / (ol.yr - oof.yr)) - 1) * 100, 2)
  END AS ocf_cagr,

  CASE WHEN fl.yr - ff.yr > 0
    THEN ROUND((POWER(fl.val::numeric / ff.val, 1.0 / (fl.yr - ff.yr)) - 1) * 100, 2)
  END AS fcf_cagr,

  -- Debt
  lbs.latest_long_term_debt,
  sa.median_debt_to_equity,

  -- Liquidity
  lbs.current_ratio AS latest_current_ratio

FROM symbol_agg sa
LEFT JOIN companies  c   ON sa.symbol = c.symbol
LEFT JOIN eps_yoy_positive eyp ON sa.symbol = eyp.symbol
LEFT JOIN rev_first  rf  ON sa.symbol = rf.symbol
LEFT JOIN rev_last   rl  ON sa.symbol = rl.symbol
LEFT JOIN eps_first  ef  ON sa.symbol = ef.symbol
LEFT JOIN eps_last   el  ON sa.symbol = el.symbol
LEFT JOIN ocf_first  oof ON sa.symbol = oof.symbol
LEFT JOIN ocf_last   ol  ON sa.symbol = ol.symbol
LEFT JOIN fcf_first  ff  ON sa.symbol = ff.symbol
LEFT JOIN fcf_last   fl  ON sa.symbol = fl.symbol
LEFT JOIN latest_bs  lbs ON sa.symbol = lbs.symbol
ORDER BY COALESCE(c.name, sa.symbol), LENGTH(sa.symbol), sa.symbol;

-- Unique index required for REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS idx_screener_metrics_symbol
  ON screener_metrics(symbol);

-- Indexes for common filter / sort columns
CREATE INDEX IF NOT EXISTS idx_screener_sector    ON screener_metrics(sector);
CREATE INDEX IF NOT EXISTS idx_screener_industry  ON screener_metrics(industry);
CREATE INDEX IF NOT EXISTS idx_screener_rating    ON screener_metrics(rating);
CREATE INDEX IF NOT EXISTS idx_screener_roic      ON screener_metrics(median_roic);
CREATE INDEX IF NOT EXISTS idx_screener_profit    ON screener_metrics(profit_pct);
CREATE INDEX IF NOT EXISTS idx_screener_eps_yoy_pos ON screener_metrics(pct_eps_yoy_positive);
