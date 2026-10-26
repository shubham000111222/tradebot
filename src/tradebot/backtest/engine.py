"""Deterministic candle replay with fees and stop/target exits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from tradebot.core.models import Candle, Signal
from tradebot.strategies.base import Strategy, StrategyContext


@dataclass(frozen=True)
class BacktestTrade:
    strategy: str
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    fees: Decimal
    pnl: Decimal
    exit_reason: str


@dataclass(frozen=True)
class BacktestResult:
    starting_cash: Decimal
    ending_cash: Decimal
    equity_curve: tuple[Decimal, ...]
    trades: tuple[BacktestTrade, ...]

    @property
    def total_return(self) -> Decimal:
        return (self.ending_cash - self.starting_cash) / self.starting_cash

    @property
    def win_rate(self) -> Decimal:
        if not self.trades:
            return Decimal("0")
        return Decimal(sum(trade.pnl > 0 for trade in self.trades)) / len(self.trades)

    @property
    def profit_factor(self) -> Decimal:
        gross_wins = sum((trade.pnl for trade in self.trades if trade.pnl > 0), Decimal("0"))
        gross_losses = sum((-trade.pnl for trade in self.trades if trade.pnl < 0), Decimal("0"))
        return gross_wins / gross_losses if gross_losses else Decimal("Infinity")

    @property
    def max_drawdown(self) -> Decimal:
        peak = self.starting_cash
        maximum = Decimal("0")
        for equity in self.equity_curve:
            peak = max(peak, equity)
            maximum = max(maximum, (peak - equity) / peak)
        return maximum


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        *,
        starting_cash: Decimal = Decimal("1000"),
        fee_rate: Decimal = Decimal("0.001"),
        quantity: Decimal = Decimal("0.1"),
    ) -> None:
        self.strategy = strategy
        self.starting_cash = starting_cash
        self.fee_rate = fee_rate
        self.quantity = quantity

    def run(self, candles: list[Candle]) -> BacktestResult:
        if not candles:
            raise ValueError("backtest requires at least one candle")
        cash = self.starting_cash
        equity_curve: list[Decimal] = []
        trades: list[BacktestTrade] = []
        open_trade: dict[str, object] | None = None
        history: list[Candle] = []
        for candle in candles:
            history.append(candle)
            if open_trade is not None:
                signal = open_trade["signal"]
                assert isinstance(signal, Signal)
                exit_price: Decimal | None = None
                reason = ""
                if candle.low <= signal.stop_price:
                    exit_price, reason = signal.stop_price, "stop"
                elif candle.high >= signal.target_price:
                    exit_price, reason = signal.target_price, "target"
                if exit_price is not None:
                    entry_price = open_trade["entry_price"]
                    entry_fee = open_trade["entry_fee"]
                    assert isinstance(entry_price, Decimal)
                    assert isinstance(entry_fee, Decimal)
                    exit_fee = exit_price * self.quantity * self.fee_rate
                    pnl = (exit_price - entry_price) * self.quantity - entry_fee - exit_fee
                    cash += (exit_price * self.quantity) - exit_fee
                    trades.append(
                        BacktestTrade(
                            strategy=self.strategy.name,
                            entry_time=signal.timestamp,
                            exit_time=candle.close_time,
                            entry_price=entry_price,
                            exit_price=exit_price,
                            quantity=self.quantity,
                            fees=entry_fee + exit_fee,
                            pnl=pnl,
                            exit_reason=reason,
                        )
                    )
                    open_trade = None
            if open_trade is None:
                signals = self.strategy.on_candle(
                    StrategyContext(
                        symbol=candle.symbol,
                        timeframe=candle.timeframe,
                        candles=tuple(history),
                    )
                )
                if signals:
                    signal = signals[0]
                    entry_price = signal.entry_price or candle.close
                    entry_fee = entry_price * self.quantity * self.fee_rate
                    cash -= entry_price * self.quantity + entry_fee
                    open_trade = {
                        "signal": signal,
                        "entry_price": entry_price,
                        "entry_fee": entry_fee,
                    }
            mark = candle.close
            if open_trade is None:
                equity_curve.append(cash)
            else:
                entry_price = open_trade["entry_price"]
                assert isinstance(entry_price, Decimal)
                equity_curve.append(cash + self.quantity * mark)
        if open_trade is not None:
            signal = open_trade["signal"]
            entry_price = open_trade["entry_price"]
            entry_fee = open_trade["entry_fee"]
            assert isinstance(signal, Signal)
            assert isinstance(entry_price, Decimal)
            assert isinstance(entry_fee, Decimal)
            exit_price = candles[-1].close
            exit_fee = exit_price * self.quantity * self.fee_rate
            pnl = (exit_price - entry_price) * self.quantity - entry_fee - exit_fee
            cash += exit_price * self.quantity - exit_fee
            trades.append(
                BacktestTrade(
                    strategy=self.strategy.name,
                    entry_time=signal.timestamp,
                    exit_time=candles[-1].close_time,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    quantity=self.quantity,
                    fees=entry_fee + exit_fee,
                    pnl=pnl,
                    exit_reason="end_of_test",
                )
            )
        return BacktestResult(self.starting_cash, cash, tuple(equity_curve), tuple(trades))
