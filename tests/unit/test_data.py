from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tradebot.data.candles import CandleBuilder, timeframe_duration
from tradebot.data.models import OrderBookLevel, OrderBookSnapshot, TradeTick
from tradebot.data.quality import DataQualityGuard
from tradebot.data.store import MarketDataStore

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def tick(trade_id: str, seconds: int, price: str, quantity: str = "1") -> TradeTick:
    return TradeTick(
        symbol="BTC/USDT",
        trade_id=trade_id,
        timestamp=BASE + timedelta(seconds=seconds),
        price=price,
        quantity=quantity,
    )


def test_candle_builder_closes_on_next_bucket() -> None:
    builder = CandleBuilder("BTC/USDT", "1m")
    assert builder.add(tick("1", 1, "100")) == []
    assert builder.add(tick("2", 30, "105", "2")) == []

    closed = builder.add(tick("3", 61, "103"))

    assert len(closed) == 1
    candle = closed[0]
    assert candle.open == Decimal("100")
    assert candle.high == Decimal("105")
    assert candle.low == Decimal("100")
    assert candle.close == Decimal("105")
    assert candle.volume == Decimal("3")


def test_candle_builder_rejects_out_of_order_ticks() -> None:
    builder = CandleBuilder("BTC/USDT", "1m")
    builder.add(tick("1", 10, "100"))
    with pytest.raises(ValueError, match="ordered"):
        builder.add(tick("2", 9, "101"))


def test_quality_guard_drops_duplicates_order_errors_and_unconfirmed_spikes() -> None:
    guard = DataQualityGuard()
    first = tick("1", 1, "100")
    assert guard.accept(first) == (True, "accepted")
    assert guard.accept(first) == (False, "duplicate_trade")
    assert guard.accept(tick("2", 0, "100")) == (False, "out_of_order_trade")
    assert guard.accept(tick("3", 2, "106", "1")) == (False, "unconfirmed_price_spike")
    assert guard.accept(tick("4", 3, "106", "2")) == (True, "accepted")


def test_order_book_computes_best_prices_and_spread() -> None:
    book = OrderBookSnapshot(
        symbol="BTC/USDT",
        timestamp=BASE,
        bids=(OrderBookLevel(price="99", quantity="2"),),
        asks=(OrderBookLevel(price="101", quantity="3"),),
    )

    assert book.best_bid == Decimal("99")
    assert book.best_ask == Decimal("101")
    assert book.spread_fraction == Decimal("2") / Decimal("99")


def test_store_writes_partitioned_parquet_and_queries_with_duckdb(tmp_path) -> None:
    pytest.importorskip("pyarrow")
    pytest.importorskip("duckdb")
    store = MarketDataStore(tmp_path)
    path = store.append_ticks([tick("1", 1, "100"), tick("2", 2, "101")])

    assert path.exists()
    assert "symbol=BTC_USDT" in str(path)
    assert store.query(f"SELECT count(*) FROM read_parquet('{path.as_posix()}')")[0][0] == 2


def test_timeframe_parser() -> None:
    assert timeframe_duration("5m") == timedelta(minutes=5)
    with pytest.raises(ValueError):
        timeframe_duration("90x")
