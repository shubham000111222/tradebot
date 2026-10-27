"""Counterparty and venue-health monitors."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


class MonitorLevel(StrEnum):
    OK = "ok"
    WARN = "warn"
    PAUSE = "pause"


class MonitorResult(BaseModel):
    name: str
    level: MonitorLevel
    detail: str
    checked_at: datetime


class StablecoinMonitor:
    def __init__(
        self,
        *,
        warning_deviation: Decimal = Decimal("0.005"),
        pause_deviation: Decimal = Decimal("0.01"),
    ) -> None:
        if not (Decimal("0") < warning_deviation < pause_deviation):
            raise ValueError("stablecoin thresholds must be positive and ordered")
        self.warning_deviation = warning_deviation
        self.pause_deviation = pause_deviation

    def evaluate(self, *, pair: str, price: Decimal, checked_at: datetime) -> MonitorResult:
        deviation = abs(price - Decimal("1"))
        if deviation >= self.pause_deviation:
            level = MonitorLevel.PAUSE
        elif deviation >= self.warning_deviation:
            level = MonitorLevel.WARN
        else:
            level = MonitorLevel.OK
        return MonitorResult(
            name=f"stablecoin:{pair}",
            level=level,
            detail=f"price={price} deviation={deviation}",
            checked_at=checked_at,
        )


class ExchangeStatus(StrEnum):
    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"


class ExchangeStatusMonitor:
    def evaluate(
        self, *, exchange: str, status: ExchangeStatus, checked_at: datetime, detail: str = ""
    ) -> MonitorResult:
        level = MonitorLevel.OK if status is ExchangeStatus.OPERATIONAL else MonitorLevel.PAUSE
        return MonitorResult(
            name=f"exchange:{exchange}",
            level=level,
            detail=detail or status.value,
            checked_at=checked_at,
        )
