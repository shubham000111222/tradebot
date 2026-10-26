"""Decimal-only helpers for financial calculations."""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation

ZERO = Decimal("0")
ONE = Decimal("1")


def decimal(value: Decimal | int | str | float) -> Decimal:
    """Convert a value to Decimal without inheriting binary float artifacts."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def quantize_step(value: Decimal, step: Decimal, *, rounding: str = ROUND_DOWN) -> Decimal:
    """Round a quantity or price down/up to an exchange-defined step."""
    if step <= ZERO:
        raise ValueError("step must be positive")
    units = (value / step).to_integral_value(rounding=rounding)
    return units * step


def money(value: Decimal | int | str | float) -> Decimal:
    """Normalize monetary input to two decimal places."""
    return decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def percentage_change(start: Decimal, end: Decimal) -> Decimal:
    """Return a fractional change, e.g. 0.05 for a 5% increase."""
    if start <= ZERO:
        raise ValueError("start must be positive")
    return (end - start) / start
