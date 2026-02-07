VENV := .venv/bin
PYTHON := $(VENV)/python
PIP := $(VENV)/pip

.PHONY: setup backend frontend dev ingest-universe ingest-all ingest-symbol status refresh-screener

# ---- Setup ----

venv:
	python3 -m venv .venv

setup: venv
	$(PIP) install -r backend/requirements.txt
	cd frontend && npm install

# ---- Development ----

backend:
	$(VENV)/uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

dev:
	@echo "Run 'make backend' and 'make frontend' in separate terminals."

# ---- Ingestion CLI ----

ingest-universe:
	$(PYTHON) -m backend.app.cli ingest-universe

ingest-all:
	$(PYTHON) -m backend.app.cli ingest-fundamentals

ingest-symbol:
	@test -n "$(SYM)" || (echo "Usage: make ingest-symbol SYM=COST" && exit 1)
	$(PYTHON) -m backend.app.cli ingest-symbol $(SYM)

status:
	$(PYTHON) -m backend.app.cli status

refresh-screener:
	$(PYTHON) -m backend.app.cli refresh-screener
