from decimal import Decimal

import pytest

from tradebot.core.money import decimal, money, percentage_change, quantize_step


def test_decimal_does_not_inherit_float_binary_artifacts() -> None:
    assert decimal(0.1) == Decimal("0.1")


def test_money_and_exchange_step_rounding() -> None:
    assert money("12.345") == Decimal("12.35")
    assert quantize_step(Decimal("1.239"), Decimal("0.01")) == Decimal("1.23")


def test_percentage_change_rejects_zero_start() -> None:
    with pytest.raises(ValueError, match="positive"):
        percentage_change(Decimal("0"), Decimal("1"))
