"""S3: Donchian breakout with volume confirmation."""

from __future__ import annotations

from decimal import Decimal

from tradebot.core.models import OrderSide, Signal, SignalEntryType
from tradebot.strategies.base import StrategyContext
from tradebot.strategies.indicators import atr, average_volume, donchian_high


class BreakoutStrategy:
    name = "breakout"

    def on_candle(self, context: StrategyContext) -> list[Signal]:
        candles = list(context.candles)
        channel_high = donchian_high(candles)
        volume_average = average_volume(candles[:-1])
        volatility = atr(candles)
        if channel_high is None or volume_average is None or volatility is None:
            return []
        current = candles[-1]
        if not (current.close > channel_high and current.volume > volume_average):
            return []
        return [
            Signal(
                symbol=context.symbol,
                side=OrderSide.BUY,
                entry_type=SignalEntryType.MARKET,
                entry_price=current.close,
                stop_price=current.close - Decimal("2") * volatility,
                target_price=current.close + Decimal("4") * volatility,
                confidence=min(Decimal("1"), current.volume / volume_average / Decimal("2")),
                reason=(
                    "Donchian 20-bar breakout with volume "
                    f"{current.volume / volume_average:.2f}x average"
                ),
                strategy=self.name,
                timestamp=current.close_time,
            )
        ]
