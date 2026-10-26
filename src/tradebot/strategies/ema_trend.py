"""S1: EMA crossover with directional-strength and ATR protection."""

from __future__ import annotations

from decimal import Decimal

from tradebot.core.models import OrderSide, Signal, SignalEntryType
from tradebot.strategies.base import StrategyContext
from tradebot.strategies.indicators import atr, closes, ema, trend_strength


class EmaTrendStrategy:
    name = "trend_ema"

    def __init__(
        self,
        fast_period: int = 20,
        slow_period: int = 50,
        min_strength: Decimal = Decimal("20"),
    ) -> None:
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.min_strength = min_strength

    def on_candle(self, context: StrategyContext) -> list[Signal]:
        candles = list(context.candles)
        values = closes(candles)
        fast = ema(values, self.fast_period)
        slow = ema(values, self.slow_period)
        volatility = atr(candles)
        strength = trend_strength(candles)
        if len(values) < self.slow_period + 1 or volatility is None or strength is None:
            return []
        previous_fast = ema(values[:-1], self.fast_period)[-1]
        previous_slow = ema(values[:-1], self.slow_period)[-1]
        if not (
            previous_fast <= previous_slow
            and fast[-1] > slow[-1]
            and strength >= self.min_strength
        ):
            return []
        entry = candles[-1].close
        return [
            Signal(
                symbol=context.symbol,
                side=OrderSide.BUY,
                entry_type=SignalEntryType.LIMIT,
                entry_price=entry,
                stop_price=entry - Decimal("1.5") * volatility,
                target_price=entry + Decimal("3") * volatility,
                confidence=min(Decimal("1"), strength / Decimal("100")),
                reason=(
                    f"EMA {self.fast_period}/{self.slow_period} bullish crossover; "
                    f"strength={strength:.2f}"
                ),
                strategy=self.name,
                timestamp=candles[-1].close_time,
            )
        ]
