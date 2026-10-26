"""Validated application configuration and guarded mode selection."""

from __future__ import annotations

import os
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TradingMode(StrEnum):
    PAPER = "paper"
    TESTNET = "testnet"
    LIVE = "live"


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: TradingMode = TradingMode.PAPER
    initial_cash_usdt: Decimal = Field(default=Decimal("1000.00"), gt=Decimal("0"))
    symbols: tuple[str, ...] = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT")
    base_timeframe: str = "1m"
    signal_timeframes: tuple[str, ...] = ("15m", "1h")
    data_dir: Path = Path("data")
    state_dir: Path = Path("state")
    log_dir: Path = Path("logs")
    timezone: str = "UTC"
    live_trading_enabled_env: str = "LIVE_TRADING_ENABLED"

    @field_validator("symbols")
    @classmethod
    def symbols_are_valid(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("at least one symbol is required")
        normalized = tuple(symbol.upper() for symbol in values)
        if any(symbol.count("/") != 1 for symbol in normalized):
            raise ValueError("symbols must use BASE/QUOTE format")
        if len(set(normalized)) != len(normalized):
            raise ValueError("symbols must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_mode_guard(self) -> Settings:
        if self.mode is TradingMode.LIVE:
            enabled = os.getenv(self.live_trading_enabled_env, "false").lower() == "true"
            if not enabled:
                raise ValueError(
                    f"live mode requires {self.live_trading_enabled_env}=true; "
                    "live trading is disabled by default"
                )
        return self


def load_settings(path: str | Path = "config/settings.yaml") -> Settings:
    """Load YAML settings and apply the small set of documented env overrides."""
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"configuration file does not exist: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}

    overrides: dict[str, Any] = {}
    if os.getenv("TRADEBOT_MODE"):
        overrides["mode"] = os.environ["TRADEBOT_MODE"]
    for key, env_name in (("data_dir", "TRADEBOT_DATA_DIR"), ("state_dir", "TRADEBOT_STATE_DIR")):
        if os.getenv(env_name):
            overrides[key] = os.environ[env_name]
    raw.update(overrides)
    return Settings.model_validate(raw)
