"""Deterministic Monte Carlo stress of trade order and outcome paths."""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal

from tradebot.backtest.engine import BacktestTrade


@dataclass(frozen=True)
class MonteCarloSummary:
    iterations: int
    return_percentile_05: Decimal
    return_percentile_50: Decimal
    return_percentile_95: Decimal
    drawdown_percentile_95: Decimal


def simulate_trades(
    trades: tuple[BacktestTrade, ...],
    *,
    starting_cash: Decimal,
    iterations: int = 1000,
    seed: int = 42,
) -> MonteCarloSummary:
    if not trades or iterations <= 0:
        raise ValueError("Monte Carlo requires trades and a positive iteration count")
    generator = random.Random(seed)
    returns: list[Decimal] = []
    drawdowns: list[Decimal] = []
    for _ in range(iterations):
        outcomes = list(trades)
        generator.shuffle(outcomes)
        equity = starting_cash
        peak = equity
        maximum_drawdown = Decimal("0")
        for trade in outcomes:
            equity += trade.pnl
            peak = max(peak, equity)
            maximum_drawdown = max(maximum_drawdown, (peak - equity) / peak)
        returns.append((equity - starting_cash) / starting_cash)
        drawdowns.append(maximum_drawdown)
    return MonteCarloSummary(
        iterations=iterations,
        return_percentile_05=_percentile(returns, Decimal("0.05")),
        return_percentile_50=_percentile(returns, Decimal("0.50")),
        return_percentile_95=_percentile(returns, Decimal("0.95")),
        drawdown_percentile_95=_percentile(drawdowns, Decimal("0.95")),
    )


def _percentile(values: list[Decimal], percentile: Decimal) -> Decimal:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * percentile))
    return ordered[index]
