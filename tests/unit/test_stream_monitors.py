import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradebot.data.models import OrderBookLevel, OrderBookSnapshot, TradeTick
from tradebot.data.stream import (
    MarketDataService,
    OrderBookRecorder,
    ReconnectPolicy,
    ReplayMarketFeed,
)
from tradebot.risk.monitors import (
    ExchangeStatus,
    ExchangeStatusMonitor,
    MonitorLevel,
    StablecoinMonitor,
)


BASE = datetime(2026, 1, 1, tzinfo=UTC)


def tick(trade_id: str, seconds: int, price: str = "100") -> TradeTick:
    return TradeTick(
        symbol="BTC/USDT",
        trade_id=trade_id,
        timestamp=BASE + timedelta(seconds=seconds),
        price=price,
        quantity="1",
    )


def snapshot(seconds: int) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="BTC/USDT",
        timestamp=BASE + timedelta(seconds=seconds),
        bids=(OrderBookLevel(price="99", quantity="1"),),
        asks=(OrderBookLevel(price="101", quantity="1"),),
    )


def test_replay_market_feed_processes_quality_and_candles() -> None:
    feed = ReplayMarketFeed([tick("1", 1), tick("1", 2), tick("2", 61), snapshot(61)])
    service = MarketDataService(feed)
    stats = asyncio.run(service.consume())

    assert stats.events_seen == 4
    assert stats.accepted_ticks == 2
    assert stats.rejected_ticks == 1
    assert stats.order_books_seen == 1
    assert stats.candles_closed == 1


def test_reconnect_policy_is_bounded_and_reproducible() -> None:
    policy = ReconnectPolicy(jitter_fraction=0)
    assert [policy.delay(attempt) for attempt in range(5)] == [1, 2, 4, 8, 16]
    assert policy.delay(20) == 60


def test_order_book_recorder_enforces_one_second_cadence() -> None:
    recorder = OrderBookRecorder()
    assert recorder.accept(snapshot(0))
    assert not recorder.accept(snapshot(0))
    assert recorder.accept(snapshot(1))
    assert len(recorder.recorded) == 2


def test_stablecoin_and_exchange_monitors_escalate() -> None:
    checked_at = BASE
    stablecoin = StablecoinMonitor()
    assert (
        stablecoin.evaluate(
            pair="USDC/USDT", price=Decimal("1.002"), checked_at=checked_at
        ).level
        is MonitorLevel.OK
    )
    assert (
        stablecoin.evaluate(
            pair="USDC/USDT", price=Decimal("0.994"), checked_at=checked_at
        ).level
        is MonitorLevel.WARN
    )
    assert (
        stablecoin.evaluate(
            pair="USDC/USDT", price=Decimal("0.985"), checked_at=checked_at
        ).level
        is MonitorLevel.PAUSE
    )
    status = ExchangeStatusMonitor().evaluate(
        exchange="demo", status=ExchangeStatus.MAINTENANCE, checked_at=checked_at
    )
    assert status.level is MonitorLevel.PAUSE
