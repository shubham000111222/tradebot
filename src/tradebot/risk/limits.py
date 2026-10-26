"""Hard-bounded risk configuration."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class RiskLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_per_trade: Decimal = Field(gt=Decimal("0"), le=Decimal("0.02"))
    max_symbol_exposure: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    max_total_exposure: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    max_correlated_bucket_exposure: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    max_open_positions: int = Field(gt=0, le=100)
    daily_loss_limit: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    daily_flatten_limit: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    weekly_loss_limit: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    max_drawdown: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    max_capital_usdt: Decimal = Field(gt=Decimal("0"))


def load_risk_limits(path: str | Path = "config/risk.yaml") -> RiskLimits:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"risk configuration file does not exist: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        values: dict[str, Any] = yaml.safe_load(handle) or {}
    return RiskLimits.model_validate(values)
