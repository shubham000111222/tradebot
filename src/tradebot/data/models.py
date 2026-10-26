"""Validated market-data records."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_validator

from tradebot.core.clock import require_utc, utc_now
from tradebot.core.models import DomainModel
from tradebot.core.money import ZERO


class TradeTick(DomainModel):
    symbol: str
    trade_id: str = Field(min_length=1)
    timestamp: datetime
    price: Decimal = Field(gt=ZERO)
    quantity: Decimal = Field(gt=ZERO)
    is_buyer_maker: bool = False

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value)

    @field_validator("symbol")
    @classmethod
    def symbol_is_normalized(cls, value: str) -> str:
        if value.count("/") != 1:
            raise ValueError("symbol must use BASE/QUOTE format")
        return value.upper()


class OrderBookLevel(DomainModel):
    price: Decimal = Field(gt=ZERO)
    quantity: Decimal = Field(gt=ZERO)


class OrderBookSnapshot(DomainModel):
    symbol: str
    timestamp: datetime = Field(default_factory=utc_now)
    bids: tuple[OrderBookLevel, ...] = Field(min_length=1, max_length=20)
    asks: tuple[OrderBookLevel, ...] = Field(min_length=1, max_length=20)

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value)

    @field_validator("symbol")
    @classmethod
    def symbol_is_normalized(cls, value: str) -> str:
        if value.count("/") != 1:
            raise ValueError("symbol must use BASE/QUOTE format")
        return value.upper()

    @property
    def best_bid(self) -> Decimal:
        return max(level.price for level in self.bids)

    @property
    def best_ask(self) -> Decimal:
        return min(level.price for level in self.asks)

    @property
    def spread_fraction(self) -> Decimal:
        return (self.best_ask - self.best_bid) / self.best_bid
