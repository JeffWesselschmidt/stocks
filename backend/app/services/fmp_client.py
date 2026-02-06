"""
Async FMP (Financial Modeling Prep) API client.

Uses the /stable/ endpoint family.  Includes a token-bucket rate limiter
and automatic retry with exponential backoff.
"""

import asyncio
import logging
import time
from typing import Any

import httpx

from backend.app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token-bucket rate limiter
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Simple token-bucket rate limiter (per-minute)."""

    def __init__(self, requests_per_minute: int):
        self.rpm = requests_per_minute
        self.tokens = float(requests_per_minute)
        self.max_tokens = float(requests_per_minute)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.max_tokens, self.tokens + elapsed * (self.rpm / 60.0))
            self.last_refill = now

            if self.tokens < 1.0:
                wait = (1.0 - self.tokens) / (self.rpm / 60.0)
                logger.debug("Rate limiter: waiting %.2fs", wait)
                await asyncio.sleep(wait)
                self.tokens = 0.0
                self.last_refill = time.monotonic()
            else:
                self.tokens -= 1.0


# ---------------------------------------------------------------------------
# Synchronous wrapper for CLI usage
# ---------------------------------------------------------------------------

class _SyncRateLimiter:
    """Simple synchronous token-bucket rate limiter."""

    def __init__(self, requests_per_minute: int):
        self.rpm = requests_per_minute
        self.tokens = float(requests_per_minute)
        self.max_tokens = float(requests_per_minute)
        self.last_refill = time.monotonic()

    def acquire(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * (self.rpm / 60.0))
        self.last_refill = now

        if self.tokens < 1.0:
            wait = (1.0 - self.tokens) / (self.rpm / 60.0)
            logger.debug("Rate limiter (sync): waiting %.2fs", wait)
            time.sleep(wait)
            self.tokens = 0.0
            self.last_refill = time.monotonic()
        else:
            self.tokens -= 1.0


# ---------------------------------------------------------------------------
# Async FMP Client
# ---------------------------------------------------------------------------

class FMPClient:
    """Async HTTP client for the FMP stable API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        rate_limit: int | None = None,
    ):
        self.api_key = api_key or settings.fmp_api_key
        self.base_url = (base_url or settings.fmp_base_url).rstrip("/")
        self._limiter = _RateLimiter(rate_limit or settings.fmp_rate_limit)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Make an authenticated GET request with rate limiting and retry."""
        params = dict(params or {})
        params["apikey"] = self.api_key
        url = f"{self.base_url}/stable/{endpoint}"

        client = await self._get_client()

        for attempt in range(4):
            await self._limiter.acquire()
            try:
                resp = await client.get(url, params=params)
                if resp.status_code == 429:
                    wait = 2 ** attempt * 2
                    logger.warning("429 rate limited, backing off %ds", wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError:
                raise
            except httpx.HTTPError as e:
                if attempt == 3:
                    raise
                wait = 2 ** attempt
                logger.warning("HTTP error (attempt %d): %s – retrying in %ds", attempt + 1, e, wait)
                await asyncio.sleep(wait)

    # ----- Symbol universe -----

    async def get_stock_list(self) -> list[dict]:
        """Get all available stock symbols."""
        return await self._request("stock-list")

    # ----- Company info -----

    async def get_profile(self, symbol: str) -> dict | None:
        """Get company profile data."""
        data = await self._request("profile", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else None

    async def get_quote(self, symbol: str) -> dict | None:
        """Get real-time quote (price, market cap, etc.)."""
        data = await self._request("quote", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else None

    # ----- Financial statements -----

    async def get_income_statement(
        self, symbol: str, period: str = "quarter", limit: int = 60
    ) -> list[dict]:
        """Get income statements (quarterly or annual)."""
        return await self._request(
            "income-statement", {"symbol": symbol, "period": period, "limit": limit}
        )

    async def get_balance_sheet(
        self, symbol: str, period: str = "quarter", limit: int = 60
    ) -> list[dict]:
        """Get balance sheet statements."""
        return await self._request(
            "balance-sheet-statement", {"symbol": symbol, "period": period, "limit": limit}
        )

    async def get_cash_flow(
        self, symbol: str, period: str = "quarter", limit: int = 60
    ) -> list[dict]:
        """Get cash flow statements."""
        return await self._request(
            "cash-flow-statement", {"symbol": symbol, "period": period, "limit": limit}
        )

    # ----- Enterprise value -----

    async def get_enterprise_values(
        self, symbol: str, period: str = "quarter", limit: int = 60
    ) -> list[dict]:
        """Get historical enterprise values."""
        return await self._request(
            "enterprise-values", {"symbol": symbol, "period": period, "limit": limit}
        )

    # ----- Search -----

    async def search_symbol(self, query: str, limit: int = 10) -> list[dict]:
        """Search for symbols by ticker prefix."""
        return await self._request(
            "search-symbol", {"query": query, "limit": limit}
        )

    async def search_name(self, query: str, limit: int = 10) -> list[dict]:
        """Search for symbols by company name."""
        return await self._request(
            "search-name", {"query": query, "limit": limit}
        )


# ---------------------------------------------------------------------------
# Synchronous FMP Client (for CLI)
# ---------------------------------------------------------------------------

class FMPClientSync:
    """Synchronous HTTP client for FMP API, used by CLI commands."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        rate_limit: int | None = None,
    ):
        self.api_key = api_key or settings.fmp_api_key
        self.base_url = (base_url or settings.fmp_base_url).rstrip("/")
        self._limiter = _SyncRateLimiter(rate_limit or settings.fmp_rate_limit)

    def _request(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        params = dict(params or {})
        params["apikey"] = self.api_key
        url = f"{self.base_url}/stable/{endpoint}"

        for attempt in range(4):
            self._limiter.acquire()
            try:
                resp = httpx.get(url, params=params, timeout=30.0)
                if resp.status_code == 429:
                    wait = 2 ** attempt * 2
                    logger.warning("429 rate limited, backing off %ds", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError:
                raise
            except httpx.HTTPError as e:
                if attempt == 3:
                    raise
                wait = 2 ** attempt
                logger.warning("HTTP error (attempt %d): %s – retrying in %ds", attempt + 1, e, wait)
                time.sleep(wait)

    def get_stock_list(self) -> list[dict]:
        return self._request("stock-list")

    def get_profile(self, symbol: str) -> dict | None:
        data = self._request("profile", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else None

    def get_quote(self, symbol: str) -> dict | None:
        data = self._request("quote", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else None

    def get_income_statement(self, symbol: str, period: str = "quarter", limit: int = 60) -> list[dict]:
        return self._request("income-statement", {"symbol": symbol, "period": period, "limit": limit})

    def get_balance_sheet(self, symbol: str, period: str = "quarter", limit: int = 60) -> list[dict]:
        return self._request("balance-sheet-statement", {"symbol": symbol, "period": period, "limit": limit})

    def get_cash_flow(self, symbol: str, period: str = "quarter", limit: int = 60) -> list[dict]:
        return self._request("cash-flow-statement", {"symbol": symbol, "period": period, "limit": limit})

    def get_enterprise_values(self, symbol: str, period: str = "quarter", limit: int = 60) -> list[dict]:
        return self._request("enterprise-values", {"symbol": symbol, "period": period, "limit": limit})

    def search_symbol(self, query: str, limit: int = 10) -> list[dict]:
        return self._request("search-symbol", {"query": query, "limit": limit})
