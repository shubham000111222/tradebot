"""Candle and order-book features available at bar close."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import field_validator

from tradebot.core.models import Candle, DomainModel
from tradebot.data.models import OrderBookSnapshot
from tradebot.strategies.indicators import atr, closes, ema, rsi


class FeatureVector(DomainModel):
    timestamp: datetime
    values: dict[str, Decimal]

    @field_validator("values")
    @classmethod
    def values_are_finite(cls, values: dict[str, Decimal]) -> dict[str, Decimal]:
        if any(not value.is_finite() for value in values.values()):
            raise ValueError("feature vector contains a non-finite value")
        return values


def build_features(
    candles: list[Candle],
    *,
    order_book: OrderBookSnapshot | None = None,
    sentiment: Decimal = Decimal("0"),
) -> FeatureVector | None:
    """Build only from data known at the latest candle close."""
    if len(candles) < 21:
        return None
    latest = candles[-1]
    values = closes(candles)
    previous = values[-2]
    current = values[-1]
    current_atr = atr(candles)
    current_rsi = rsi(values)
    fast = ema(values, 20)
    slow = ema(values, 50)
    features = {
        "return_1": current / previous - Decimal("1"),
        "return_5": current / values[-6] - Decimal("1"),
        "volume": latest.volume,
        "sentiment": sentiment,
    }
    if current_atr is not None:
        features["atr_ratio"] = current_atr / current
    if current_rsi is not None:
        features["rsi"] = current_rsi / Decimal("100")
    if fast and slow:
        features["ema_distance"] = fast[-1] / slow[-1] - Decimal("1")
    if order_book is not None:
        bid_depth = sum((level.quantity for level in order_book.bids), Decimal("0"))
        ask_depth = sum((level.quantity for level in order_book.asks), Decimal("0"))
        total_depth = bid_depth + ask_depth
        features["spread"] = order_book.spread_fraction
        features["book_imbalance"] = (
            (bid_depth - ask_depth) / total_depth if total_depth else Decimal("0")
        )
    return FeatureVector(timestamp=latest.close_time, values=features)


def features_are_fresh(features: FeatureVector, *, now: datetime, max_age: timedelta) -> bool:
    return now - features.timestamp <= max_age
