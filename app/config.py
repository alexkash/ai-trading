from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
EXPORTS_DIR = DATA_DIR / "exports"
BOTS_DIR = ROOT_DIR / "bots"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(default=f"sqlite+aiosqlite:///{DATA_DIR}/app.sqlite")
    sync_database_url: str = Field(default=f"sqlite:///{DATA_DIR}/app.sqlite")

    bybit_testnet: bool = False
    bybit_rest_url: str = "https://api.bybit.com"
    bybit_ws_public_url: str = "wss://stream.bybit.com/v5/public/linear"

    # Bybit API credentials (optional in v1 — paper trading uses public market data only).
    # Used for higher REST rate limits and, eventually, private endpoints.
    bybit_api_key: str = ""
    bybit_api_secret: str = ""

    default_taker_fee_bps: float = 5.5
    default_maker_fee_bps: float = 2.0
    default_slippage_bps: float = 1.0

    history_concurrency: int = 4
    history_page_limit: int = 1000

    bot_hot_reload: bool = True


settings = Settings()

DATA_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
