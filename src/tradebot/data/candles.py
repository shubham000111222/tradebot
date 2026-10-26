"""Build time bars from accepted trade ticks."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal

from tradebot.core.clock import require_utc
from tradebot.core.models import Candle
from tradebot.data.models import TradeTick

_TIMEFRAME = re.compile(r"^(?P<count>[1-9][0-9]*)(?P<unit>[mhd])$")


def timeframe_duration(timeframe: str) -> timedelta:
    match = _TIMEFRAME.fullmatch(timeframe)
    if not match:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    count = int(match.group("count"))
    seconds = count * {"m": 60, "h": 3600, "d": 86400}[match.group("unit")]
    return timedelta(seconds=seconds)


class CandleBuilder:
    """Incrementally aggregate one symbol/timeframe without inventing missing bars."""

    def __init__(self, symbol: str, timeframe: str) -> None:
        self.symbol = symbol.upper()
        self.timeframe = timeframe
        self._duration = timeframe_duration(timeframe)
        self._start: datetime | None = None
        self._last_timestamp: datetime | None = None
        self._open = self._high = self._low = self._close = Decimal("0")
        self._volume = Decimal("0")

    def add(self, tick: TradeTick) -> list[Candle]:
        if tick.symbol != self.symbol:
            raise ValueError(f"expected {self.symbol}, received {tick.symbol}")
        timestamp = require_utc(tick.timestamp)
        if self._last_timestamp is not None and timestamp <= self._last_timestamp:
            raise ValueError("ticks must be ordered before candle building")
        self._last_timestamp = timestamp
        start = self._bucket_start(timestamp)
        if self._start is None:
            self._start = start
            self._start_bar(tick)
            return []
        if start < self._start:
            raise ValueError("ticks must be ordered before candle building")
        if start == self._start:
            self._update(tick)
            return []

        closed = self._close_current()
        self._start = start
        self._start_bar(tick)
        return [closed]

    def flush(self, at: datetime) -> list[Candle]:
        if self._start is None:
            return []
        if require_utc(at) < self._start + self._duration:
            return []
        return [self._close_current()]

    def _bucket_start(self, timestamp: datetime) -> datetime:
        epoch_seconds = int(timestamp.timestamp())
        duration_seconds = int(self._duration.total_seconds())
        return datetime.fromtimestamp(
            epoch_seconds - epoch_seconds % duration_seconds, tz=timestamp.tzinfo
        )

    def _start_bar(self, tick: TradeTick) -> None:
        self._open = self._high = self._low = self._close = tick.price
        self._volume = tick.quantity

    def _update(self, tick: TradeTick) -> None:
        self._high = max(self._high, tick.price)
        self._low = min(self._low, tick.price)
        self._close = tick.price
        self._volume += tick.quantity

    def _close_current(self) -> Candle:
        assert self._start is not None
        candle = Candle(
            symbol=self.symbol,
            timeframe=self.timeframe,
            open_time=self._start,
            close_time=self._start + self._duration,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._volume,
        )
        self._start = None
        return candle
