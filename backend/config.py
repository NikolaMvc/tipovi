"""Central configuration, loaded from environment / .env.

Local-only workflow: no database, no server. The pipeline scrapes, predicts and
writes static JSON into frontend/public/data/."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent          # backend/
ROOT_DIR = BASE_DIR.parent                          # repo root
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Where the static JSON snapshots live (served verbatim by Vercel).
DATA_DIR = ROOT_DIR / "frontend" / "public" / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Data sources ---
    FOOTBALL_DATA_API_KEY: str = ""
    OPENWEATHER_API_KEY: str = ""

    # --- Scraping ---
    SCRAPER_RATE_LIMIT_MIN: float = 1.0
    SCRAPER_RATE_LIMIT_MAX: float = 2.0
    SCRAPER_MAX_RETRIES: int = 3
    SCRAPER_HEADLESS: bool = True

    # --- Run window / storage ---
    LOOKAHEAD_DAYS: int = 3          # today + next 2 days
    ROLLING_DAYS: int = 3            # keep the last N days of predictions/results/tips
    TIP_COUNT: int = 20             # auto top-N tips per day
    # Drop matches with no betting market on any source. True = only bettable
    # matches (empties the app out of season); False = keep all matches.
    REQUIRE_ODDS: bool = True

    # --- Monte Carlo ---
    MC_SIMULATIONS: int = 10000
    MC_SEED: int | None = None

    @property
    def mc_seed(self) -> int | None:
        raw = os.getenv("MC_SEED", "")
        return int(raw) if raw.strip().lstrip("-").isdigit() else None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
