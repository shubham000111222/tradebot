"""Core events shared by data, strategies, risk and execution."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from tradebot.core.clock import require_utc, utc_now
from tradebot.core.money import ZERO


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    LIMIT = "limit"
    MARKET = "market"
    STOP_LIMIT = "stop_limit"


class OrderStatus(StrEnum):
    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class SignalEntryType(StrEnum):
    LIMIT = "limit"
    MARKET = "market"


class Signal(DomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    side: OrderSide
    entry_type: SignalEntryType = SignalEntryType.LIMIT
    entry_price: Decimal | None = Field(default=None, gt=ZERO)
    stop_price: Decimal = Field(gt=ZERO)
    target_price: Decimal = Field(gt=ZERO)
    confidence: Decimal = Field(ge=ZERO, le=Decimal("1"))
    reason: str = Field(min_length=1, max_length=1000)
    strategy: str = Field(min_length=1, max_length=100)
    timestamp: datetime = Field(default_factory=utc_now)

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value)

    @field_validator("symbol")
    @classmethod
    def symbol_has_quote(cls, value: str) -> str:
        if "/" not in value or value.count("/") != 1:
            raise ValueError("symbol must use BASE/QUOTE format")
        return value.upper()


class Order(DomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    client_order_id: str = Field(default_factory=lambda: f"tb-{uuid4().hex}", min_length=1)
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: Decimal = Field(gt=ZERO)
    price: Decimal | None = Field(default=None, gt=ZERO)
    stop_price: Decimal | None = Field(default=None, gt=ZERO)
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: Decimal = Field(default=ZERO, ge=ZERO)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("symbol")
    @classmethod
    def symbol_has_quote(cls, value: str) -> str:
        if "/" not in value or value.count("/") != 1:
            raise ValueError("symbol must use BASE/QUOTE format")
        return value.upper()

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return require_utc(value)

    @field_validator("filled_quantity")
    @classmethod
    def filled_does_not_exceed_order(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        quantity = info.data.get("quantity")
        if quantity is not None and value > quantity:
            raise ValueError("filled quantity cannot exceed order quantity")
        return value


class Fill(DomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order_id: str = Field(min_length=1)
    symbol: str
    side: OrderSide
    quantity: Decimal = Field(gt=ZERO)
    price: Decimal = Field(gt=ZERO)
    fee: Decimal = Field(default=ZERO, ge=ZERO)
    fee_currency: str = "USDT"
    timestamp: datetime = Field(default_factory=utc_now)

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value)


class Position(DomainModel):
    symbol: str
    quantity: Decimal = Field(default=ZERO, ge=ZERO)
    average_entry_price: Decimal | None = Field(default=None, gt=ZERO)
    realized_pnl: Decimal = ZERO
    unrealized_pnl: Decimal = ZERO
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("updated_at")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value)


class Candle(DomainModel):
    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Decimal = Field(gt=ZERO)
    high: Decimal = Field(gt=ZERO)
    low: Decimal = Field(gt=ZERO)
    close: Decimal = Field(gt=ZERO)
    volume: Decimal = Field(ge=ZERO)

    @field_validator("open_time", "close_time")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return require_utc(value)

    @field_validator("high")
    @classmethod
    def high_covers_ohlc(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        low = info.data.get("low")
        if low is not None and value < low:
            raise ValueError("high cannot be below low")
        return value

    @field_validator("low")
    @classmethod
    def low_covers_ohlc(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        high = info.data.get("high")
        if high is not None and value > high:
            raise ValueError("low cannot be above high")
        return value


def normalize_decimal_fields(model: DomainModel) -> DomainModel:
    """Validate that a model contains Decimal values, never floats."""
    for value in model.model_dump().values():
        if isinstance(value, float):
            raise TypeError("financial models must not contain float values")
    return model
