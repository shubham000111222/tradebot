"""Async market-data boundary with replay and reconnect behavior."""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from tradebot.core.models import Candle
from tradebot.data.candles import CandleBuilder
from tradebot.data.models import OrderBookSnapshot, TradeTick
from tradebot.data.quality import DataQualityGuard
from tradebot.data.store import MarketDataStore


MarketEvent = TradeTick | OrderBookSnapshot


class MarketFeed(Protocol):
    def __aiter__(self) -> AsyncIterator[MarketEvent]: ...


class ReplayMarketFeed:
    """Deterministic async feed for tests, backtests and paper demos."""

    def __init__(self, events: Iterable[MarketEvent], *, delay_seconds: float = 0) -> None:
        self.events = tuple(events)
        self.delay_seconds = delay_seconds

    def __aiter__(self) -> AsyncIterator[MarketEvent]:
        return self._events()

    async def _events(self) -> AsyncIterator[MarketEvent]:
        for event in self.events:
            if self.delay_seconds > 0:
                await asyncio.sleep(self.delay_seconds)
            yield event


@dataclass(frozen=True)
class ReconnectPolicy:
    initial_seconds: float = 1.0
    maximum_seconds: float = 60.0
    multiplier: float = 2.0
    jitter_fraction: float = 0.2

    def delay(self, attempt: int, *, random_value: float | None = None) -> float:
        if attempt < 0:
            raise ValueError("attempt cannot be negative")
        base = min(self.maximum_seconds, self.initial_seconds * self.multiplier**attempt)
        if self.jitter_fraction == 0:
            return base
        value = random.random() if random_value is None else random_value
        return max(0.0, base * (1 + self.jitter_fraction * (2 * value - 1)))


@dataclass(frozen=True)
class StreamStats:
    events_seen: int
    accepted_ticks: int
    rejected_ticks: int
    order_books_seen: int
    candles_closed: int
    symbols_stale: tuple[str, ...]


class MarketDataService:
    """Apply quality guards and build candles without knowing exchange details."""

    def __init__(
        self,
        feed: MarketFeed,
        *,
        timeframe: str = "1m",
        store: MarketDataStore | None = None,
    ) -> None:
        self.feed = feed
        self.timeframe = timeframe
        self.store = store
        self.quality = DataQualityGuard()
        self.builders: dict[str, CandleBuilder] = {}
        self.closed_candles: list[Candle] = []

    async def consume(self, *, max_events: int | None = None) -> StreamStats:
        events_seen = accepted_ticks = rejected_ticks = order_books_seen = 0
        async for event in self.feed:
            events_seen += 1
            if max_events is not None and events_seen > max_events:
                break
            if isinstance(event, TradeTick):
                accepted, _reason = self.quality.accept(event)
                if not accepted:
                    rejected_ticks += 1
                    continue
                accepted_ticks += 1
                if self.store is not None:
                    self.store.append_ticks([event])
                builder = self.builders.setdefault(
                    event.symbol, CandleBuilder(event.symbol, self.timeframe)
                )
                self.closed_candles.extend(builder.add(event))
            else:
                order_books_seen += 1
                if self.store is not None:
                    self.store.append_order_books([event])
        stale = tuple(
            symbol
            for symbol in self.builders
            if self.quality.is_stale(symbol, max_age=timedelta(seconds=15))
        )
        return StreamStats(
            events_seen=events_seen,
            accepted_ticks=accepted_ticks,
            rejected_ticks=rejected_ticks,
            order_books_seen=order_books_seen,
            candles_closed=len(self.closed_candles),
            symbols_stale=stale,
        )


class OrderBookRecorder:
    """Record snapshots at a bounded cadence while preserving the latest book."""

    def __init__(self, *, interval_seconds: int = 1, store: MarketDataStore | None = None) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.interval_seconds = interval_seconds
        self.store = store
        self.latest: dict[str, OrderBookSnapshot] = {}
        self.recorded: list[OrderBookSnapshot] = []

    def accept(self, snapshot: OrderBookSnapshot) -> bool:
        previous = self.latest.get(snapshot.symbol)
        self.latest[snapshot.symbol] = snapshot
        if previous is not None:
            elapsed = (snapshot.timestamp - previous.timestamp).total_seconds()
            if elapsed < self.interval_seconds:
                return False
        self.recorded.append(snapshot)
        if self.store is not None:
            self.store.append_order_books([snapshot])
        return True
