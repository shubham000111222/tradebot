"""Acceptance gates and simple cost-stress helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tradebot.backtest.engine import BacktestEngine, BacktestResult
from tradebot.backtest.metrics import PerformanceMetrics, calculate_metrics
from tradebot.strategies.base import Strategy
from tradebot.core.models import Candle


@dataclass(frozen=True)
class AcceptanceGates:
    minimum_profit_factor: Decimal = Decimal("1.3")
    minimum_sharpe: Decimal = Decimal("1.0")
    maximum_drawdown: Decimal = Decimal("0.15")
    minimum_trades: int = 200
    maximum_monte_carlo_drawdown: Decimal = Decimal("0.20")


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failures: tuple[str, ...]


def evaluate_gates(
    metrics: PerformanceMetrics, gates: AcceptanceGates | None = None
) -> GateResult:
    active_gates = gates or AcceptanceGates()
    failures: list[str] = []
    if metrics.profit_factor <= active_gates.minimum_profit_factor:
        failures.append("profit_factor")
    if metrics.sharpe <= active_gates.minimum_sharpe:
        failures.append("sharpe")
    if metrics.max_drawdown >= active_gates.maximum_drawdown:
        failures.append("max_drawdown")
    if metrics.trade_count < active_gates.minimum_trades:
        failures.append("trade_count")
    return GateResult(not failures, tuple(failures))


def run_cost_stress(
    strategy: Strategy,
    candles: list[Candle],
    *,
    starting_cash: Decimal = Decimal("1000"),
    fee_rate: Decimal = Decimal("0.001"),
    quantity: Decimal = Decimal("0.1"),
) -> tuple[BacktestResult, BacktestResult, PerformanceMetrics, PerformanceMetrics]:
    normal = BacktestEngine(
        strategy,
        starting_cash=starting_cash,
        fee_rate=fee_rate,
        quantity=quantity,
    ).run(candles)
    stressed = BacktestEngine(
        strategy,
        starting_cash=starting_cash,
        fee_rate=fee_rate * Decimal("2"),
        quantity=quantity,
    ).run(candles)
    return normal, stressed, calculate_metrics(normal), calculate_metrics(stressed)
