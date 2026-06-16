"""Central configuration, loaded from environment / .env."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---
    DATABASE_URL: str = "sqlite:///./tipovi.db"

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL: int = 1800

    # --- Weather ---
    OPENWEATHER_API_KEY: str = ""

    # --- Optional reliable football data backbone (free key) ---
    FOOTBALL_DATA_API_KEY: str = ""

    # --- Scraping ---
    SCRAPER_RATE_LIMIT_MIN: float = 1.0
    SCRAPER_RATE_LIMIT_MAX: float = 2.0
    SCRAPER_MAX_RETRIES: int = 3
    SCRAPER_HEADLESS: bool = True

    # --- Worker ---
    SCRAPE_INTERVAL_HOURS: int = 6
    REFRESH_INTERVAL_HOURS: int = 1
    SETTLE_INTERVAL_HOURS: int = 2
    LOOKAHEAD_DAYS: int = 3
    RUN_SCRAPE_ON_STARTUP: bool = True

    # --- Monte Carlo ---
    MC_SIMULATIONS: int = 10000
    MC_SEED: int | None = None

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def mc_seed(self) -> int | None:
        raw = os.getenv("MC_SEED", "")
        return int(raw) if raw.strip().isdigit() else None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
