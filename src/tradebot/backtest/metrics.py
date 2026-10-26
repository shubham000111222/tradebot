"""Cost-aware performance metrics for replay results."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from tradebot.backtest.engine import BacktestResult


@dataclass(frozen=True)
class PerformanceMetrics:
    total_return: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    expectancy: Decimal
    sharpe: Decimal
    sortino: Decimal
    max_drawdown: Decimal
    max_drawdown_duration: int
    trade_count: int
    fees_paid: Decimal


def calculate_metrics(result: BacktestResult) -> PerformanceMetrics:
    returns = _returns(result.equity_curve)
    mean = sum(returns, Decimal("0")) / len(returns) if returns else Decimal("0")
    variance = (
        sum(((value - mean) * (value - mean) for value in returns), Decimal("0")) / len(returns)
        if returns
        else Decimal("0")
    )
    downside = [value for value in returns if value < 0]
    downside_variance = (
        sum((value * value for value in downside), Decimal("0")) / len(downside)
        if downside
        else Decimal("0")
    )
    expectancy = (
        sum((trade.pnl for trade in result.trades), Decimal("0")) / len(result.trades)
        if result.trades
        else Decimal("0")
    )
    sharpe = mean / variance.sqrt() if variance else Decimal("0")
    sortino = mean / downside_variance.sqrt() if downside_variance else Decimal("0")
    return PerformanceMetrics(
        total_return=result.total_return,
        win_rate=result.win_rate,
        profit_factor=result.profit_factor,
        expectancy=expectancy,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=result.max_drawdown,
        max_drawdown_duration=_drawdown_duration(result.equity_curve),
        trade_count=len(result.trades),
        fees_paid=sum((trade.fees for trade in result.trades), Decimal("0")),
    )


def _returns(equity_curve: tuple[Decimal, ...]) -> list[Decimal]:
    return [
        (current - previous) / previous
        for previous, current in zip(equity_curve, equity_curve[1:], strict=False)
        if previous > 0
    ]


def _drawdown_duration(equity_curve: tuple[Decimal, ...]) -> int:
    peak = Decimal("0")
    current_duration = 0
    maximum_duration = 0
    for equity in equity_curve:
        if equity >= peak:
            peak = equity
            current_duration = 0
        else:
            current_duration += 1
            maximum_duration = max(maximum_duration, current_duration)
    return maximum_duration
