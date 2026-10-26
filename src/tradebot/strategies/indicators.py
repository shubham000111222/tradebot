"""Small Decimal indicators with no exchange or portfolio dependencies."""

from __future__ import annotations

from decimal import Decimal
from tradebot.core.models import Candle


def closes(candles: list[Candle] | tuple[Candle, ...]) -> list[Decimal]:
    return [candle.close for candle in candles]


def ema(values: list[Decimal], period: int) -> list[Decimal]:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        return []
    result = [sum(values[:period], Decimal("0")) / period]
    multiplier = Decimal("2") / Decimal(period + 1)
    for value in values[period:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def true_ranges(candles: list[Candle]) -> list[Decimal]:
    ranges: list[Decimal] = []
    previous_close: Decimal | None = None
    for candle in candles:
        if previous_close is None:
            ranges.append(candle.high - candle.low)
        else:
            ranges.append(
                max(
                    candle.high - candle.low,
                    abs(candle.high - previous_close),
                    abs(candle.low - previous_close),
                )
            )
        previous_close = candle.close
    return ranges


def atr(candles: list[Candle], period: int = 14) -> Decimal | None:
    ranges = true_ranges(candles)
    if len(ranges) < period:
        return None
    return sum(ranges[-period:], Decimal("0")) / period


def rsi(values: list[Decimal], period: int = 14) -> Decimal | None:
    if len(values) < period + 1:
        return None
    changes = [
        current - previous for previous, current in zip(values, values[1:], strict=False)
    ]
    window = changes[-period:]
    gains = sum((change for change in window if change > 0), Decimal("0")) / period
    losses = sum((-change for change in window if change < 0), Decimal("0")) / period
    if losses == 0:
        return Decimal("100")
    return Decimal("100") - Decimal("100") / (Decimal("1") + gains / losses)


def bollinger(
    values: list[Decimal], period: int = 20, deviations: Decimal = Decimal("2")
) -> tuple[Decimal, Decimal, Decimal] | None:
    if len(values) < period:
        return None
    window = values[-period:]
    mean = sum(window, Decimal("0")) / period
    variance = sum(
        ((value - mean) * (value - mean) for value in window), Decimal("0")
    ) / period
    standard_deviation = variance.sqrt()
    return mean - deviations * standard_deviation, mean, mean + deviations * standard_deviation


def donchian_high(candles: list[Candle], period: int = 20) -> Decimal | None:
    if len(candles) <= period:
        return None
    return max(candle.high for candle in candles[-period - 1 : -1])


def average_volume(candles: list[Candle], period: int = 20) -> Decimal | None:
    if len(candles) < period:
        return None
    return sum((candle.volume for candle in candles[-period:]), Decimal("0")) / period


def trend_strength(candles: list[Candle], period: int = 14) -> Decimal | None:
    """A bounded directional-strength proxy used until a full ADX is added."""
    if len(candles) < period + 1:
        return None
    movement = abs(candles[-1].close - candles[-period - 1].close)
    volatility = sum(true_ranges(candles[-period:]), Decimal("0"))
    if volatility == 0:
        return Decimal("0")
    return min(Decimal("100"), Decimal("100") * movement / volatility)
