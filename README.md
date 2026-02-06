# Stocks - Symbol Page

A web app for viewing fundamental financial data for US equities, powered by [Financial Modeling Prep](https://financialmodelingprep.com/) (FMP) and PostgreSQL.

## Features

- **Symbol Page**: Header strip (price, market cap, EV, industry), Key Statistics panel (valuation ratios, 10-year median returns/margins, CAGR, capital structure), ROIC chart, and multi-year annual table.
- **Quarterly Data Storage**: Ingests and stores quarterly financial statements (income, balance sheet, cash flow) in PostgreSQL.
- **Computed Metrics**: TTM and annual values computed from quarterly data. All formulas documented in code.
- **Bulk Ingestion CLI**: Fetch fundamentals for the entire NYSE/NASDAQ universe (~8,000+ stocks). Resumable.
- **On-Demand Ingestion**: First visit to a symbol triggers automatic data fetch.

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- FMP API key ([get one here](https://financialmodelingprep.com/developer/docs/pricing))

## Quick Start

### 1. Create the database

```bash
createdb stocks
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your FMP_API_KEY and DATABASE_URL
```

### 3. Install dependencies

```bash
make setup
```

### 4. Start the backend

```bash
make backend
# Runs on http://localhost:8000
# Auto-creates tables on first startup
```

### 5. Start the frontend

```bash
make frontend
# Runs on http://localhost:5173
# Proxies /api requests to the backend
```

### 6. Visit a symbol

Open http://localhost:5173 and search for a symbol (e.g., COST, AAPL, MSFT).

## Bulk Ingestion (for screener prep)

```bash
# Step 1: Fetch the symbol universe
make ingest-universe

# Step 2: Ingest fundamentals for all symbols (takes ~2-3 hours)
make ingest-all

# Check progress
make status

# Ingest a single symbol
make ingest-symbol SYM=COST
```

## Project Structure

```
backend/
  app/
    main.py           # FastAPI app
    config.py         # Settings from .env
    cli.py            # CLI for bulk ingestion
    api/routes.py     # API endpoints
    db/
      schema.sql      # PostgreSQL schema
      connection.py   # DB connection management
      migrations.py   # Auto-create tables
    services/
      fmp_client.py   # FMP API client (async + sync)
      ingestion.py    # Data ingestion logic
      metrics.py      # Metric computation engine
    models/
      schemas.py      # Pydantic response models

frontend/
  src/
    App.tsx           # Main app with search
    pages/SymbolPage  # Symbol page orchestrator
    components/       # HeaderStrip, KeyStatistics, ROICChart, AnnualTable
    api/client.ts     # API client
    types/index.ts    # TypeScript interfaces
```

## Metric Definitions

All metrics are computed from quarterly data stored locally. Key formulas:

| Metric | Formula |
|--------|---------|
| P/E | market_cap / TTM net_income |
| P/B | market_cap / total_equity |
| ROIC | NOPAT / invested_capital |
| NOPAT | operating_income * (1 - effective_tax_rate) |
| Invested Capital | total_equity + total_debt - cash |
| 10-Yr CAGR | (latest / earliest)^(1/years) - 1 |

See `backend/app/services/metrics.py` for complete documentation.
