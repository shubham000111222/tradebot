"""S2: Bollinger/RSI mean reversion in low directional-strength regimes."""

from __future__ import annotations

from decimal import Decimal

from tradebot.core.models import OrderSide, Signal, SignalEntryType
from tradebot.strategies.base import StrategyContext
from tradebot.strategies.indicators import atr, bollinger, closes, rsi, trend_strength


class MeanReversionStrategy:
    name = "mean_reversion"

    def on_candle(self, context: StrategyContext) -> list[Signal]:
        candles = list(context.candles)
        values = closes(candles)
        bands = bollinger(values)
        current_rsi = rsi(values)
        volatility = atr(candles)
        strength = trend_strength(candles)
        if bands is None or current_rsi is None or volatility is None or strength is None:
            return []
        lower, _middle, _upper = bands
        entry = candles[-1].close
        if not (entry <= lower and current_rsi <= Decimal("30") and strength < Decimal("20")):
            return []
        return [
            Signal(
                symbol=context.symbol,
                side=OrderSide.BUY,
                entry_type=SignalEntryType.LIMIT,
                entry_price=entry,
                stop_price=entry - Decimal("1.5") * volatility,
                target_price=entry + Decimal("1.5") * volatility,
                confidence=(Decimal("30") - current_rsi) / Decimal("30"),
                reason=f"close below lower Bollinger band; RSI={current_rsi:.2f}",
                strategy=self.name,
                timestamp=candles[-1].close_time,
            )
        ]
