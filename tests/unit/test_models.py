from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tradebot.core.models import Candle, Order, OrderSide, OrderStatus, OrderType, Signal


def test_order_defaults_to_new_with_decimal_values() -> None:
    order = Order(
        symbol="btc/usdt",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity="0.01",
        price="60000",
    )

    assert order.status is OrderStatus.NEW
    assert order.symbol == "BTC/USDT"
    assert isinstance(order.quantity, Decimal)
    assert order.created_at.tzinfo is not None
    assert order.created_at.utcoffset() == UTC.utcoffset(order.created_at)


def test_order_rejects_overfilled_quantity() -> None:
    with pytest.raises(ValidationError, match="filled quantity"):
        Order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity="1",
            filled_quantity="2",
        )


def test_signal_requires_reason_and_valid_confidence() -> None:
    with pytest.raises(ValidationError):
        Signal(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            stop_price="90",
            target_price="110",
            confidence="1.1",
            reason="",
            strategy="test",
        )


def test_candle_rejects_inverted_range() -> None:
    with pytest.raises(ValidationError, match="low cannot be above high"):
        Candle(
            symbol="BTC/USDT",
            timeframe="1m",
            open_time=datetime(2026, 1, 1, tzinfo=UTC),
            close_time=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
            open="100",
            high="90",
            low="95",
            close="98",
            volume="1",
        )
