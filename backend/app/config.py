"""Application configuration from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """Application settings loaded from environment."""

    fmp_api_key: str = os.getenv("FMP_API_KEY", "")
    fmp_base_url: str = os.getenv("FMP_BASE_URL", "https://financialmodelingprep.com")
    fmp_rate_limit: int = int(os.getenv("FMP_RATE_LIMIT", "300"))  # requests per minute

    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://localhost:5432/stocks"
    )

    # For asyncpg (no driver prefix)
    @property
    def asyncpg_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql://")
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql://")
        return url

    cors_origins: list[str] = None  # type: ignore

    def __post_init__(self):
        origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
        self.cors_origins = [o.strip() for o in origins.split(",")]


settings = Settings()
