"""Instrument, cost and trading-session abstractions."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import Field

from tradebot.core.models import DomainModel


class ProductType(StrEnum):
    SPOT = "spot"
    INTRADAY = "intraday"
    DELIVERY = "delivery"


class Instrument(DomainModel):
    symbol: str
    venue: str
    quote_currency: str
    tick_size: Decimal = Field(gt=Decimal("0"))
    quantity_step: Decimal = Field(gt=Decimal("0"))
    min_quantity: Decimal = Field(gt=Decimal("0"))
    min_notional: Decimal = Field(gt=Decimal("0"))
    product_type: ProductType = ProductType.SPOT


class CostModel(Protocol):
    def estimate(self, *, notional: Decimal, side: str, maker: bool = False) -> Decimal: ...


class PercentageCostModel:
    def __init__(self, maker_rate: Decimal, taker_rate: Decimal) -> None:
        self.maker_rate = maker_rate
        self.taker_rate = taker_rate

    def estimate(self, *, notional: Decimal, side: str, maker: bool = False) -> Decimal:
        del side
        return notional * (self.maker_rate if maker else self.taker_rate)


class MarketCalendar(Protocol):
    def is_open(self, timestamp: datetime) -> bool: ...

    def next_close(self, timestamp: datetime) -> datetime | None: ...


class SessionManager(Protocol):
    def authenticate(self) -> None: ...

    def is_authenticated(self) -> bool: ...


class CryptoCalendar:
    """Crypto trades continuously; the interface leaves room for session venues."""

    def is_open(self, timestamp: datetime) -> bool:
        del timestamp
        return True

    def next_close(self, timestamp: datetime) -> datetime | None:
        del timestamp
        return None


class SessionHours:
    """NSE-style daily session helper, with timezone conversion owned by callers."""

    def __init__(self, open_time: time = time(9, 15), close_time: time = time(15, 30)) -> None:
        self.open_time = open_time
        self.close_time = close_time

    def is_open(self, timestamp: datetime) -> bool:
        return self.open_time <= timestamp.timetz().replace(tzinfo=None) < self.close_time
