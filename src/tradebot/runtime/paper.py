"""Small end-to-end paper runner for local demos and replay smoke tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from tradebot.core.models import Candle, Fill, Order, OrderType, Signal
from tradebot.data.models import OrderBookLevel, OrderBookSnapshot
from tradebot.execution.order_manager import OrderManager
from tradebot.execution.paper import PaperExchange
from tradebot.portfolio.ledger import Ledger
from tradebot.risk.engine import RiskContext, RiskDecision, RiskEngine
from tradebot.risk.killswitch import KillSwitch
from tradebot.strategies.base import Strategy, StrategyContext


@dataclass(frozen=True)
class PaperRunResult:
    signals: tuple[Signal, ...]
    fills: tuple[Fill, ...]
    rejections: tuple[RiskDecision, ...]
    ending_equity: Decimal


class PaperRuntime:
    """Connect strategy, risk, paper execution and ledger through one path."""

    def __init__(self, state_path: str | Path = "state/demo.sqlite3") -> None:
        self.kill_switch = KillSwitch(state_path)
        self.exchange = PaperExchange()
        self.orders = OrderManager(self.exchange)
        self.ledger = Ledger(state_path)
        from tradebot.risk.limits import load_risk_limits

        self.risk = RiskEngine(load_risk_limits(), self.kill_switch)

    @staticmethod
    def reset_state(state_path: str | Path) -> None:
        """Remove a runtime's SQLite files; intended for isolated demos only."""
        path = Path(state_path)
        for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
            if candidate.exists():
                candidate.unlink()

    def close(self) -> None:
        self.ledger.close()
        self.kill_switch.close()

    def run(
        self,
        candles: list[Candle],
        strategy: Strategy,
        *,
        quantity: Decimal = Decimal("0.1"),
    ) -> PaperRunResult:
        if not candles:
            raise ValueError("paper runtime requires candles")
        signals: list[Signal] = []
        fills: list[Fill] = []
        rejections: list[RiskDecision] = []
        history: list[Candle] = []
        for candle in candles:
            history.append(candle)
            if self.orders.open_orders():
                continue
            candidates = strategy.on_candle(
                StrategyContext(candle.symbol, candle.timeframe, tuple(history))
            )
            if not candidates:
                continue
            signal = candidates[0]
            signals.append(signal)
            order = Order(
                symbol=signal.symbol,
                side=signal.side,
                type=(
                    OrderType.MARKET
                    if signal.entry_type.value == "market"
                    else OrderType.LIMIT
                ),
                quantity=quantity,
                price=signal.entry_price,
                stop_price=signal.stop_price,
            )
            decision = self.risk.evaluate(
                order,
                RiskContext(
                    equity=self.ledger.equity({candle.symbol: candle.close}),
                    data_timestamp=candle.close_time,
                    spread_fraction=Decimal("0.0005"),
                    price=candle.close,
                    mid_price=candle.close,
                    stop_price=signal.stop_price,
                    top_book_depth=quantity * Decimal("20"),
                    open_positions=len(self.ledger.positions()),
                ),
                now=candle.close_time,
            )
            if not decision.approved:
                rejections.append(decision)
                continue
            submitted = self.orders.submit(order)
            snapshot = OrderBookSnapshot(
                symbol=candle.symbol,
                timestamp=candle.close_time,
                bids=(OrderBookLevel(price=candle.close, quantity=quantity * 10),),
                asks=(OrderBookLevel(price=candle.close, quantity=quantity * 10),),
            )
            new_fills = self.orders.process_market(snapshot)
            for fill in new_fills:
                self.ledger.record_fill(fill)
            fills.extend(new_fills)
            del submitted
        ending_equity = self.ledger.equity({candles[-1].symbol: candles[-1].close})
        return PaperRunResult(tuple(signals), tuple(fills), tuple(rejections), ending_equity)


def synthetic_demo_candles() -> list[Candle]:
    """Produce a deterministic breakout fixture for the one-command demo."""
    candles: list[Candle] = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(21):
        timestamp = start + timedelta(minutes=index)
        candles.append(
            Candle(
                symbol="BTC/USDT",
                timeframe="1m",
                open_time=timestamp,
                close_time=timestamp + timedelta(minutes=1),
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=Decimal("1"),
            )
        )
    timestamp = start + timedelta(minutes=21)
    candles.append(
        Candle(
            symbol="BTC/USDT",
            timeframe="1m",
            open_time=timestamp,
            close_time=timestamp + timedelta(minutes=1),
            open=Decimal("110"),
            high=Decimal("111"),
            low=Decimal("109"),
            close=Decimal("110"),
            volume=Decimal("3"),
        )
    )
    return candles
