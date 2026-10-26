from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradebot.backtest.engine import BacktestEngine
from tradebot.core.models import Candle, OrderSide, Signal, SignalEntryType
from tradebot.strategies.base import StrategyContext
from tradebot.strategies.breakout import BreakoutStrategy
from tradebot.strategies.indicators import atr, ema, rsi
from tradebot.strategies.registry import default_strategies


def candle(
    index: int,
    close: str,
    *,
    high: str | None = None,
    low: str | None = None,
    volume: str = "1",
) -> Candle:
    start = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index)
    value = Decimal(close)
    return Candle(
        symbol="BTC/USDT",
        timeframe="1m",
        open_time=start,
        close_time=start + timedelta(minutes=1),
        open=value,
        high=Decimal(high or close),
        low=Decimal(low or close),
        close=value,
        volume=volume,
    )


def test_decimal_indicators_have_expected_basic_values() -> None:
    assert ema([Decimal("1"), Decimal("2"), Decimal("3")], 2) == [Decimal("1.5"), Decimal("2.5")]
    assert rsi([Decimal(str(value)) for value in range(1, 16)]) == Decimal("100")
    assert atr(
        [candle(0, "100", high="102", low="99"), candle(1, "101", high="103", low="100")],
        2,
    ) == Decimal("3")


def test_breakout_strategy_only_signals_after_warmup() -> None:
    strategy = BreakoutStrategy()
    history = tuple(candle(index, "100", volume="1") for index in range(20))
    assert strategy.on_candle(StrategyContext("BTC/USDT", "1m", history)) == []
    signal_candle = candle(20, "101", high="102", volume="3")
    signals = strategy.on_candle(StrategyContext("BTC/USDT", "1m", history + (signal_candle,)))
    assert len(signals) == 1
    assert signals[0].side is OrderSide.BUY
    assert signals[0].entry_type is SignalEntryType.MARKET


def test_default_strategy_registry_contains_first_three_strategies() -> None:
    assert set(default_strategies()) == {"trend_ema", "mean_reversion", "breakout"}


class OneShotStrategy:
    name = "test_strategy"

    def on_candle(self, context: StrategyContext) -> list[Signal]:
        if len(context.candles) != 1:
            return []
        current = context.latest
        return [
            Signal(
                symbol=context.symbol,
                side=OrderSide.BUY,
                entry_type=SignalEntryType.MARKET,
                entry_price=current.close,
                stop_price=Decimal("95"),
                target_price=Decimal("105"),
                confidence=Decimal("1"),
                reason="test signal",
                strategy=self.name,
                timestamp=current.close_time,
            )
        ]


def test_backtest_replays_signal_with_fees_and_target_exit() -> None:
    candles = [candle(0, "100"), candle(1, "104", high="106"), candle(2, "104")]
    result = BacktestEngine(
        OneShotStrategy(),
        starting_cash=Decimal("1000"),
        fee_rate=Decimal("0.001"),
        quantity=Decimal("1"),
    ).run(candles)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "target"
    assert result.trades[0].pnl == Decimal("4.795")
    assert result.ending_cash == Decimal("1004.795")
    assert result.total_return == Decimal("0.004795")
    assert result.max_drawdown >= Decimal("0")
