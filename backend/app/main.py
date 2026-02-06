"""
FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings
from backend.app.db.connection import get_pool, close_pool
from backend.app.db.migrations import run_migrations
from backend.app.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create DB pool and run migrations. Shutdown: close pool."""
    pool = await get_pool()
    await run_migrations(pool)
    logging.getLogger(__name__).info("Backend started.")
    yield
    await close_pool()
    logging.getLogger(__name__).info("Backend stopped.")


app = FastAPI(
    title="Stocks Symbol Page",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
