"""Cheap, deterministic guards applied before market data reaches strategies."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from tradebot.core.clock import utc_now
from tradebot.data.models import TradeTick


class DataQualityGuard:
    """Track per-symbol feed state and reject unsafe tick records."""

    def __init__(self, *, max_tick_move: Decimal = Decimal("0.05")) -> None:
        self.max_tick_move = max_tick_move
        self._trade_ids: set[tuple[str, str]] = set()
        self._last_tick: dict[str, TradeTick] = {}

    def accept(self, tick: TradeTick) -> tuple[bool, str]:
        key = (tick.symbol, tick.trade_id)
        if key in self._trade_ids:
            return False, "duplicate_trade"

        previous = self._last_tick.get(tick.symbol)
        if previous is not None:
            if tick.timestamp <= previous.timestamp:
                return False, "out_of_order_trade"
            move = abs(tick.price - previous.price) / previous.price
            volume_support = tick.quantity >= previous.quantity * Decimal("2")
            if move > self.max_tick_move and not volume_support:
                return False, "unconfirmed_price_spike"

        self._trade_ids.add(key)
        self._last_tick[tick.symbol] = tick
        return True, "accepted"

    def last_timestamp(self, symbol: str) -> datetime | None:
        tick = self._last_tick.get(symbol)
        return tick.timestamp if tick else None

    def is_stale(self, symbol: str, *, max_age: timedelta = timedelta(seconds=15)) -> bool:
        timestamp = self.last_timestamp(symbol)
        return timestamp is None or utc_now() - timestamp > max_age
