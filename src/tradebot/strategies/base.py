"""Strategy contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from tradebot.core.models import Candle, Signal


@dataclass(frozen=True)
class StrategyContext:
    symbol: str
    timeframe: str
    candles: tuple[Candle, ...]

    @property
    def latest(self) -> Candle:
        if not self.candles:
            raise ValueError("strategy context has no candles")
        return self.candles[-1]


class Strategy(Protocol):
    name: str

    def on_candle(self, context: StrategyContext) -> list[Signal]: ...
